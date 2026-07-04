import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from .config import NotificationsConfig

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def render_email(template_name: str, variables: dict, config: NotificationsConfig) -> tuple[str, str, str]:
    """Returns (subject, html, text). Raises ValueError for unknown templates."""
    context = {
        "brand_name": config.brand_name,
        "brand_color": config.brand_color,
        "brand_logo_url": config.brand_logo_url,
        "brand_footer_text": config.brand_footer_text,
        **variables,
    }

    try:
        subject_template = _env.get_template(f"{template_name}/subject.txt")
        body_template = _env.get_template(f"{template_name}/body.html")
    except TemplateNotFound as exc:
        raise ValueError(f"Unknown email template: {template_name}") from exc

    subject = subject_template.render(**context).strip()
    context["subject"] = subject
    html = body_template.render(**context)
    text = _html_to_text(html)

    return subject, html, text


def available_templates() -> list[str]:
    return sorted(p.name for p in TEMPLATES_DIR.iterdir() if p.is_dir() and not p.name.startswith("_"))
