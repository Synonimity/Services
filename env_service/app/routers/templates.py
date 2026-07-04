import secrets as secrets_module

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app import templates_catalog
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.dependencies import hash_key
from app.models import ProjectApiKey

settings = get_settings()
router = APIRouter(prefix="/templates", tags=["templates"])


async def _require_any_valid_key(x_api_key: str = Header(...)) -> None:
    """
    Templates are reference data, not a secret - but this is still meant
    to be a private tool, not a public API, so any valid key (admin or
    any project's) is enough rather than opening this up entirely.
    """
    if secrets_module.compare_digest(x_api_key, settings.service_admin_key):
        return
    # Any project key also works - cheapest correct check is just "is this
    # hash present at all", without needing to know which project.
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ProjectApiKey).where(ProjectApiKey.key_hash == hash_key(x_api_key)))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")


@router.get("", dependencies=[Depends(_require_any_valid_key)])
async def list_templates():
    return [
        {
            "key": t.key,
            "display_name": t.display_name,
            "description": t.description,
            "vars": [
                {"name": v.name, "required": v.required, "sensitive": v.sensitive, "description": v.description, "example": v.example}
                for v in t.vars
            ],
        }
        for t in templates_catalog.list_templates()
    ]


@router.get("/{key}", dependencies=[Depends(_require_any_valid_key)])
async def get_template(key: str):
    template = templates_catalog.get_template(key)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown template.")
    return {
        "key": template.key,
        "display_name": template.display_name,
        "description": template.description,
        "vars": [
            {"name": v.name, "required": v.required, "sensitive": v.sensitive, "description": v.description, "example": v.example}
            for v in template.vars
        ],
    }
