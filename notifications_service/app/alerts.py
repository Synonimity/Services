"""
Lightweight ops alerting - "subscription cancelled", "payment failed",
"signup spike", whatever your app wants to ping a channel about. Separate
from the templated customer-facing emails above.
"""
import httpx

from app.config import get_settings

settings = get_settings()

_SEVERITY_EMOJI = {"info": "\u2139\ufe0f", "warning": "\u26a0\ufe0f", "error": "\U0001f6a8"}
_SEVERITY_COLOR = {"info": 0x3B82F6, "warning": 0xF59E0B, "error": 0xEF4444}


class AlertError(Exception):
    pass


async def send_alert(*, channel: str, title: str, message: str, severity: str, fields: dict[str, str]) -> None:
    if channel == "slack":
        await _send_slack(title, message, severity, fields)
    elif channel == "discord":
        await _send_discord(title, message, severity, fields)
    else:
        raise AlertError(f"Unknown alert channel: {channel}")


async def _send_slack(title: str, message: str, severity: str, fields: dict[str, str]) -> None:
    if not settings.slack_webhook_url:
        raise AlertError("SLACK_WEBHOOK_URL is not configured.")

    emoji = _SEVERITY_EMOJI.get(severity, "")
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} {title}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
    ]
    if fields:
        field_text = "\n".join(f"*{k}:* {v}" for k, v in fields.items())
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": field_text}})

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(settings.slack_webhook_url, json={"blocks": blocks})
    if resp.status_code >= 300:
        raise AlertError(f"Slack webhook returned {resp.status_code}: {resp.text}")


async def _send_discord(title: str, message: str, severity: str, fields: dict[str, str]) -> None:
    if not settings.discord_webhook_url:
        raise AlertError("DISCORD_WEBHOOK_URL is not configured.")

    embed = {
        "title": title,
        "description": message,
        "color": _SEVERITY_COLOR.get(severity, 0x3B82F6),
        "fields": [{"name": k, "value": v, "inline": True} for k, v in fields.items()],
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(settings.discord_webhook_url, json={"embeds": [embed]})
    if resp.status_code >= 300:
        raise AlertError(f"Discord webhook returned {resp.status_code}: {resp.text}")
