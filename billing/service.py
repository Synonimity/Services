import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import payfast
from .config import BillingConfig
from .models import Customer, Payment, Plan, Subscription
from .schemas import CheckoutRequest, CheckoutResponse, SubscriptionOut

logger = logging.getLogger("billing")


class BillingService:
    def __init__(self, config: BillingConfig):
        self.config = config

    async def list_plans(self, db: AsyncSession) -> list[Plan]:
        result = await db.execute(select(Plan).where(Plan.is_active.is_(True)))
        return result.scalars().all()

    async def create_checkout(self, db: AsyncSession, payload: CheckoutRequest) -> CheckoutResponse:
        result = await db.execute(select(Plan).where(Plan.code == payload.plan_code, Plan.is_active.is_(True)))
        plan = result.scalar_one_or_none()
        if plan is None:
            raise ValueError(f"Unknown or inactive plan: {payload.plan_code}")

        result = await db.execute(select(Customer).where(Customer.external_user_id == payload.external_user_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            customer = Customer(
                external_user_id=payload.external_user_id,
                email=payload.email,
                name_first=payload.name_first,
                name_last=payload.name_last,
            )
            db.add(customer)
            await db.flush()

        m_payment_id = f"sub_{uuid.uuid4().hex}"
        subscription = Subscription(
            customer_id=customer.id,
            plan_id=plan.id,
            m_payment_id=m_payment_id,
            status="pending",
        )
        db.add(subscription)
        await db.commit()

        pf_payload = payfast.build_checkout_payload(
            config=self.config,
            m_payment_id=m_payment_id,
            amount=float(plan.amount),
            item_name=plan.name,
            email=payload.email,
            name_first=payload.name_first,
            name_last=payload.name_last,
            frequency=plan.frequency,
            cycles=plan.cycles,
        )
        return CheckoutResponse(
            redirect_url=payfast.checkout_redirect_url(self.config, pf_payload),
            m_payment_id=m_payment_id,
        )

    async def handle_itn(self, db: AsyncSession, data: dict[str, str], client_ip: str) -> dict:
        """
        Call this from the host app's ITN endpoint. Returns {"received": True}
        on success; raises ValueError for invalid/tampered notifications.
        """
        if not payfast.verify_itn_signature(data, self.config.payfast_passphrase):
            raise ValueError("ITN signature mismatch.")

        host_ok = payfast.verify_source_host(client_ip)
        revalidated = await payfast.verify_with_payfast(self.config, data)
        if not host_ok and not revalidated:
            raise ValueError("Could not verify ITN source.")

        m_payment_id = data.get("m_payment_id", "")
        result = await db.execute(select(Subscription).where(Subscription.m_payment_id == m_payment_id))
        subscription = result.scalar_one_or_none()
        if subscription is None:
            logger.warning("ITN for unknown m_payment_id: %s", m_payment_id)
            return {"received": True}

        result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
        plan = result.scalar_one()

        amount_gross = float(data.get("amount_gross", 0) or 0)
        if abs(amount_gross - float(plan.amount)) > 0.01:
            logger.error("ITN amount mismatch for %s: got %s expected %s", m_payment_id, amount_gross, plan.amount)
            raise ValueError("Amount mismatch.")

        payment_status = data.get("payment_status", "")

        db.add(Payment(
            subscription_id=subscription.id,
            customer_id=subscription.customer_id,
            pf_payment_id=data.get("pf_payment_id", ""),
            m_payment_id=m_payment_id,
            amount_gross=amount_gross,
            amount_fee=float(data.get("amount_fee", 0) or 0),
            amount_net=float(data.get("amount_net", 0) or 0),
            payment_status=payment_status,
            raw_payload=data,
        ))

        if payment_status == "COMPLETE":
            subscription.status = "active"
            if token := data.get("token"):
                subscription.payfast_token = token
        elif payment_status == "FAILED":
            subscription.status = "failed"
        elif payment_status == "CANCELLED":
            subscription.status = "cancelled"

        await db.commit()
        return {"received": True}

    async def get_subscriptions(self, db: AsyncSession, external_user_id: str) -> list[SubscriptionOut]:
        result = await db.execute(select(Customer).where(Customer.external_user_id == external_user_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            return []

        result = await db.execute(select(Subscription).where(Subscription.customer_id == customer.id))
        subs = result.scalars().all()

        out = []
        for s in subs:
            result = await db.execute(select(Plan).where(Plan.id == s.plan_id))
            plan = result.scalar_one()
            out.append(SubscriptionOut(
                id=s.id, plan_code=plan.code, status=s.status,
                next_billing_date=s.next_billing_date, created_at=s.created_at,
            ))
        return out

    async def _get_subscription(self, db: AsyncSession, subscription_id: uuid.UUID) -> Subscription:
        result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
        sub = result.scalar_one_or_none()
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found.")
        if not sub.payfast_token:
            raise ValueError("Subscription has no active PayFast token yet.")
        return sub

    async def cancel(self, db: AsyncSession, subscription_id: uuid.UUID) -> None:
        sub = await self._get_subscription(db, subscription_id)
        await payfast.cancel_subscription(self.config, sub.payfast_token)
        sub.status = "cancelled"
        await db.commit()

    async def pause(self, db: AsyncSession, subscription_id: uuid.UUID, cycles: int = 1) -> None:
        sub = await self._get_subscription(db, subscription_id)
        await payfast.pause_subscription(self.config, sub.payfast_token, cycles=cycles)
        sub.status = "paused"
        await db.commit()

    async def unpause(self, db: AsyncSession, subscription_id: uuid.UUID) -> None:
        sub = await self._get_subscription(db, subscription_id)
        await payfast.unpause_subscription(self.config, sub.payfast_token)
        sub.status = "active"
        await db.commit()
