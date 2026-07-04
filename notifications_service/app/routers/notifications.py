import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import alerts, email_provider
from app.config import get_settings
from app.database import get_db
from app.dependencies import limiter, require_api_key
from app.models import EmailEvent, NotificationLog
from app.schemas import AlertRequest, NotificationOut, SendEmailRequest, SendEmailResponse
from app.svix_verify import WebhookVerificationError, verify_svix_signature
from app.templating import available_templates, render_email

settings = get_settings()
logger = logging.getLogger("notifications")
router = APIRouter(prefix="/notifications", tags=["notifications"])

# Webhook event types that represent the email's authoritative current
# state. Engagement events (opened/clicked) are logged but don't
# overwrite a more important status like "bounced".
_STATUS_EVENTS = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
}


@router.get("/templates", dependencies=[Depends(require_api_key)])
async def list_templates():
    return {"templates": available_templates()}


@router.post("/send", response_model=SendEmailResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("60/minute")
async def send_notification(request: Request, payload: SendEmailRequest, db: AsyncSession = Depends(get_db)):
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
        subject, html, text = render_email(payload.template_name, payload.variables)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

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
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send email.")

    await db.commit()
    return SendEmailResponse(id=log.id, status=log.status, provider_message_id=log.provider_message_id)


@router.get("/{notification_id}", response_model=NotificationOut, dependencies=[Depends(require_api_key)])
async def get_notification(notification_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(NotificationLog).where(NotificationLog.id == notification_id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return log


@router.post("/webhooks/resend", status_code=status.HTTP_200_OK)
@limiter.limit("300/minute")
async def resend_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw_body = await request.body()

    try:
        verify_svix_signature(
            secret=settings.resend_webhook_secret,
            raw_body=raw_body,
            svix_id=request.headers.get("svix-id", ""),
            svix_timestamp=request.headers.get("svix-timestamp", ""),
            svix_signature=request.headers.get("svix-signature", ""),
        )
    except WebhookVerificationError as exc:
        logger.warning("Resend webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    payload = await request.json()
    event_type = payload.get("type", "")
    data = payload.get("data", {})
    email_id = data.get("email_id")
    svix_id = request.headers.get("svix-id", "")

    if not email_id:
        return {"received": True}

    result = await db.execute(select(NotificationLog).where(NotificationLog.provider_message_id == email_id))
    log = result.scalar_one_or_none()
    if log is None:
        # Could be an email sent before this service tracked it, or via
        # another integration - nothing to update, acknowledge anyway.
        return {"received": True}

    db.add(EmailEvent(notification_id=log.id, event_type=event_type, svix_id=svix_id, raw_payload=payload))

    if event_type in _STATUS_EVENTS:
        log.status = _STATUS_EVENTS[event_type]

    await db.commit()
    return {"received": True}


@router.post("/alert", dependencies=[Depends(require_api_key)])
@limiter.limit("60/minute")
async def trigger_alert(request: Request, payload: AlertRequest):
    try:
        await alerts.send_alert(
            channel=payload.channel,
            title=payload.title,
            message=payload.message,
            severity=payload.severity,
            fields=payload.fields,
        )
    except alerts.AlertError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"sent": True}
