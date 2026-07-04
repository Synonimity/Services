"""
The only piece that genuinely needs to be an HTTP endpoint is the Resend
webhook — Resend has to call something from outside your app. Mount this
in the host app alongside your own routes:

    from notifications import make_router
    app.include_router(make_router(notifications_service))

Everything else (send, get_status, trigger_alert) is called directly as
Python — no HTTP, no extra auth layer needed.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import AlertRequest, NotificationOut, SendEmailRequest, SendEmailResponse
from .service import NotificationsService
from .svix_verify import WebhookVerificationError


def make_router(service: NotificationsService, db_dep, prefix: str = "/notifications") -> APIRouter:
    """
    Args:
        service:  your NotificationsService instance
        db_dep:   the host app's get_db dependency (FastAPI Depends-compatible)
        prefix:   URL prefix, default /notifications

    Returns an APIRouter ready to pass to app.include_router().
    """
    router = APIRouter(prefix=prefix, tags=["notifications"])

    @router.post("/send", response_model=SendEmailResponse)
    async def send_notification(payload: SendEmailRequest, db: AsyncSession = Depends(db_dep)):
        try:
            return await service.send(db, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @router.get("/templates")
    async def list_templates():
        return {"templates": service.list_templates()}

    @router.post("/webhooks/resend", status_code=status.HTTP_200_OK)
    async def resend_webhook(request: Request, db: AsyncSession = Depends(db_dep)):
        raw_body = await request.body()
        payload = await request.json()
        headers = dict(request.headers)
        try:
            return await service.handle_resend_webhook(db, raw_body, headers, payload)
        except WebhookVerificationError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    @router.post("/alert")
    async def trigger_alert(payload: AlertRequest):
        try:
            await service.trigger_alert(payload)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        return {"sent": True}

    return router
