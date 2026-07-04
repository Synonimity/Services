import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Project, ProjectApiKey

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def require_admin_key(x_api_key: str = Header(...)) -> None:
    if not secrets.compare_digest(x_api_key, settings.service_admin_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key.")


@dataclass
class ProjectAuth:
    project: Project
    actor_label: str
    can_write: bool


async def get_project_auth(
    project_slug: str,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> ProjectAuth:
    result = await db.execute(select(Project).where(Project.slug == project_slug))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    # The admin key has full access to every project.
    if secrets.compare_digest(x_api_key, settings.service_admin_key):
        return ProjectAuth(project=project, actor_label="admin", can_write=True)

    key_hash = hash_key(x_api_key)
    result = await db.execute(
        select(ProjectApiKey).where(
            ProjectApiKey.project_id == project.id,
            ProjectApiKey.key_hash == key_hash,
        )
    )
    api_key = result.scalar_one_or_none()

    if api_key is None or api_key.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key.")

    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return ProjectAuth(project=project, actor_label=api_key.label, can_write=api_key.can_write)


def require_write(auth: ProjectAuth) -> None:
    if not auth.can_write:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This API key is read-only.")
