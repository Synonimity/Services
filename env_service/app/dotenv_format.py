"""Renders a dict of env vars as .env file text, quoting values that need it."""
import re

_NEEDS_QUOTING_RE = re.compile(r"[\s#\"'$]")


def _format_value(value: str) -> str:
    if value == "" or _NEEDS_QUOTING_RE.search(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def render_dotenv(entries: dict[str, str]) -> str:
    lines = [f"{key}={_format_value(value)}" for key, value in sorted(entries.items())]
    return "\n".join(lines) + "\n"
