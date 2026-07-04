import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import payfast
from app.config import get_settings
from app.database import get_db
from app.dependencies import limiter, require_api_key
from app.models import Customer, Payment, Plan, Subscription
from app.schemas import CheckoutRequest, CheckoutResponse, PlanOut, SubscriptionOut

settings = get_settings()
logger = logging.getLogger("billing")
router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------
@router.get("/plans", response_model=list[PlanOut], dependencies=[Depends(require_api_key)])
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)))
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Checkout - called by your app's backend to start a new subscription
# ---------------------------------------------------------------------------
@router.post("/checkout", response_model=CheckoutResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("20/minute")
async def create_checkout(request: Request, payload: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.code == payload.plan_code, Plan.is_active.is_(True)))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan.")

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

    fields = payfast.build_checkout_payload(
        m_payment_id=m_payment_id,
        amount=float(plan.amount),
        item_name=plan.name,
        email=payload.email,
        name_first=payload.name_first,
        name_last=payload.name_last,
        frequency=plan.frequency,
        cycles=plan.cycles,
    )
    redirect_url = payfast.checkout_redirect_url(fields)

    return CheckoutResponse(redirect_url=redirect_url, m_payment_id=m_payment_id)


# ---------------------------------------------------------------------------
# ITN webhook - called by PayFast, not by your app. No API key: PayFast
# can't send one, so this is authenticated via signature + re-validation.
# ---------------------------------------------------------------------------
@router.post("/itn", status_code=status.HTTP_200_OK)
@limiter.limit("120/minute")
async def payfast_itn(request: Request, db: AsyncSession = Depends(get_db)):
    form = dict((await request.form()))
    data = {k: str(v) for k, v in form.items()}

    if not payfast.verify_itn_signature(data):
        logger.warning("ITN signature mismatch: %s", data.get("m_payment_id"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    client_ip = request.client.host if request.client else ""
    host_ok = payfast.verify_source_host(client_ip)
    revalidated = await payfast.verify_with_payfast(data)
    if not host_ok and not revalidated:
        logger.warning("ITN failed both host check and PayFast re-validation: ip=%s", client_ip)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not verify notification source.")

    m_payment_id = data.get("m_payment_id", "")
    result = await db.execute(select(Subscription).where(Subscription.m_payment_id == m_payment_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        logger.warning("ITN for unknown m_payment_id: %s", m_payment_id)
        # Return 200 anyway - PayFast retries on non-200, and there's
        # nothing more we can do for a payment_id we don't recognise.
        return {"received": True}

    result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
    plan = result.scalar_one()

    # Verify the amount matches what we expect for this plan - never trust
    # the amount in the notification on its own.
    amount_gross = float(data.get("amount_gross", 0) or 0)
    expected = float(plan.amount)
    if abs(amount_gross - expected) > 0.01:
        logger.error("ITN amount mismatch for %s: got %s expected %s", m_payment_id, amount_gross, expected)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount mismatch.")

    payment_status = data.get("payment_status", "")

    db.add(
        Payment(
            subscription_id=subscription.id,
            customer_id=subscription.customer_id,
            pf_payment_id=data.get("pf_payment_id", ""),
            m_payment_id=m_payment_id,
            amount_gross=amount_gross,
            amount_fee=float(data.get("amount_fee", 0) or 0),
            amount_net=float(data.get("amount_net", 0) or 0),
            payment_status=payment_status,
            raw_payload=data,
        )
    )

    if payment_status == "COMPLETE":
        subscription.status = "active"
        token = data.get("token")
        if token:
            subscription.payfast_token = token
    elif payment_status == "FAILED":
        subscription.status = "failed"
    elif payment_status == "CANCELLED":
        subscription.status = "cancelled"

    await db.commit()
    return {"received": True}


# ---------------------------------------------------------------------------
# Subscription lookups + management - called by your app's backend
# ---------------------------------------------------------------------------
@router.get(
    "/customers/{external_user_id}/subscriptions",
    response_model=list[SubscriptionOut],
    dependencies=[Depends(require_api_key)],
)
async def list_customer_subscriptions(external_user_id: str, db: AsyncSession = Depends(get_db)):
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
        out.append(
            SubscriptionOut(
                id=s.id,
                plan_code=plan.code,
                status=s.status,
                next_billing_date=s.next_billing_date,
                created_at=s.created_at,
            )
        )
    return out


async def _get_subscription_or_404(db: AsyncSession, subscription_id: uuid.UUID) -> Subscription:
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    if not sub.payfast_token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscription has no active PayFast token yet.")
    return sub


@router.post("/subscriptions/{subscription_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel_subscription(subscription_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sub = await _get_subscription_or_404(db, subscription_id)
    await payfast.cancel_subscription(sub.payfast_token)
    sub.status = "cancelled"
    await db.commit()
    return {"status": "cancelled"}


@router.post("/subscriptions/{subscription_id}/pause", dependencies=[Depends(require_api_key)])
async def pause_subscription(subscription_id: uuid.UUID, cycles: int = 1, db: AsyncSession = Depends(get_db)):
    sub = await _get_subscription_or_404(db, subscription_id)
    await payfast.pause_subscription(sub.payfast_token, cycles=cycles)
    sub.status = "paused"
    await db.commit()
    return {"status": "paused"}


@router.post("/subscriptions/{subscription_id}/unpause", dependencies=[Depends(require_api_key)])
async def unpause_subscription(subscription_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sub = await _get_subscription_or_404(db, subscription_id)
    await payfast.unpause_subscription(sub.payfast_token)
    sub.status = "active"
    await db.commit()
    return {"status": "active"}
