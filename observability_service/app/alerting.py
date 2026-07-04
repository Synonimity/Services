"""
Calls the notifications service's /notifications/alert endpoint when a new
error issue appears or a resolved one regresses. Deliberately best-effort:
a failure here is logged and swallowed, never raised - error reporting
itself must never break because Slack/Discord/the notifications service
is having a bad day.
"""
import logging

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("observability.alerting")


async def notify_issue(*, title: str, message: str, service_name: str, environment: str, is_regression: bool) -> None:
    if not settings.alerting_enabled:
        return

    severity = "error"
    alert_title = f"{'Regression' if is_regression else 'New error'}: {title}"

    body = {
        "channel": settings.notifications_alert_channel,
        "title": alert_title,
        "message": message[:500],
        "severity": severity,
        "fields": {"service": service_name, "environment": environment},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.notifications_base_url}/notifications/alert",
                json=body,
                headers={"X-API-Key": settings.notifications_api_key},
            )
        if resp.status_code >= 300:
            logger.warning("Alert dispatch failed (%s): %s", resp.status_code, resp.text)
    except httpx.TransportError as exc:
        logger.warning("Alert dispatch failed: %s", exc)
