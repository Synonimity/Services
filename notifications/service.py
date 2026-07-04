"""
The host app's own code calls these methods directly - no HTTP, no API
key, since it's running in the same trusted process now. The only piece
that genuinely needs to be an HTTP endpoint is the Resend webhook (Resend
calls it from outside), exposed via .router().
"""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import alerts, email_provider
from .config import NotificationsConfig
from .models import EmailEvent, NotificationLog
from .schemas import AlertRequest, NotificationOut, SendEmailRequest, SendEmailResponse
from .svix_verify import WebhookVerificationError, verify_svix_signature
from .templating import available_templates, render_email

logger = logging.getLogger("notifications")

_STATUS_EVENTS = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
}


class NotificationsService:
    def __init__(self, config: NotificationsConfig):
        self.config = config

    def list_templates(self) -> list[str]:
        return available_templates()

    async def send(self, db: AsyncSession, payload: SendEmailRequest) -> SendEmailResponse:
        if payload.idempotency_key:
            result = await db.execute(
                select(NotificationLog).where(NotificationLog.idempotency_key == payload.idempotency_key)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                return SendEmailResponse(
                    id=existing.id, status=existing.status, provider_message_id=existing.provider_message_id
                )

        try:
            subject, html, text = render_email(payload.template_name, payload.variables, self.config)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        log = NotificationLog(
            external_user_id=payload.external_user_id,
            recipient_email=payload.to_email,
            template_name=payload.template_name,
            subject=subject,
            status="queued",
            idempotency_key=payload.idempotency_key,
            variables=payload.variables,
        )
        db.add(log)
        await db.flush()

        try:
            message_id = await email_provider.send_email(
                api_key=self.config.resend_api_key,
                from_header=self.config.from_header,
                to_email=payload.to_email,
                to_name=payload.to_name,
                subject=subject,
                html=html,
                text=text,
                idempotency_key=payload.idempotency_key or str(log.id),
            )
            log.status = "sent"
            log.provider_message_id = message_id
        except email_provider.EmailSendError as exc:
            log.status = "failed"
            log.error_message = str(exc)[:500]
            await db.commit()
            raise

        await db.commit()
        return SendEmailResponse(id=log.id, status=log.status, provider_message_id=log.provider_message_id)

    async def get_status(self, db: AsyncSession, notification_id: uuid.UUID) -> NotificationOut | None:
        result = await db.execute(select(NotificationLog).where(NotificationLog.id == notification_id))
        log = result.scalar_one_or_none()
        return NotificationOut.model_validate(log) if log else None

    async def handle_resend_webhook(self, db: AsyncSession, raw_body: bytes, headers: dict, payload: dict) -> dict:
        try:
            verify_svix_signature(
                secret=self.config.resend_webhook_secret,
                raw_body=raw_body,
                svix_id=headers.get("svix-id", ""),
                svix_timestamp=headers.get("svix-timestamp", ""),
                svix_signature=headers.get("svix-signature", ""),
            )
        except WebhookVerificationError as exc:
            logger.warning("Resend webhook signature verification failed: %s", exc)
            raise

        event_type = payload.get("type", "")
        data = payload.get("data", {})
        email_id = data.get("email_id")
        svix_id = headers.get("svix-id", "")

        if not email_id:
            return {"received": True}

        result = await db.execute(select(NotificationLog).where(NotificationLog.provider_message_id == email_id))
        log = result.scalar_one_or_none()
        if log is None:
            return {"received": True}

        db.add(EmailEvent(notification_id=log.id, event_type=event_type, svix_id=svix_id, raw_payload=payload))

        if event_type in _STATUS_EVENTS:
            log.status = _STATUS_EVENTS[event_type]

        await db.commit()
        return {"received": True}

    async def trigger_alert(self, payload: AlertRequest) -> None:
        await alerts.send_alert(
            channel=payload.channel,
            title=payload.title,
            message=payload.message,
            severity=payload.severity,
            fields=payload.fields,
            slack_webhook_url=self.config.slack_webhook_url,
            discord_webhook_url=self.config.discord_webhook_url,
        )
