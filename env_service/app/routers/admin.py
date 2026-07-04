import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import hash_key, limiter, require_admin_key
from app.models import AuditLogEntry, Project, ProjectApiKey
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreatedOut,
    ApiKeyOut,
    AuditLogOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_key)])


async def _log(db: AsyncSession, *, project_id, actor: str, action: str, environment: str | None = None, key_name: str | None = None):
    db.add(AuditLogEntry(project_id=project_id, actor=actor, action=action, environment=environment, key_name=key_name))


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        template_keys=payload.template_keys,
    )
    db.add(project)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A project with that slug already exists.")
    await db.refresh(project)
    await _log(db, project_id=project.id, actor="admin", action="project.created")
    await db.commit()
    return project


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.name))
    return result.scalars().all()


async def _get_project_or_404(db: AsyncSession, slug: str) -> Project:
    result = await db.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


@router.get("/projects/{slug}", response_model=ProjectOut)
async def get_project(slug: str, db: AsyncSession = Depends(get_db)):
    return await _get_project_or_404(db, slug)


@router.patch("/projects/{slug}", response_model=ProjectOut)
async def update_project(slug: str, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await _get_project_or_404(db, slug)
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.template_keys is not None:
        project.template_keys = payload.template_keys
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(slug: str, db: AsyncSession = Depends(get_db)):
    project = await _get_project_or_404(db, slug)
    await db.delete(project)
    await db.commit()


@router.post("/projects/{slug}/api-keys", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_api_key(request: Request, slug: str, payload: ApiKeyCreate, db: AsyncSession = Depends(get_db)):
    project = await _get_project_or_404(db, slug)
    raw_key = secrets.token_urlsafe(40)

    api_key = ProjectApiKey(
        project_id=project.id,
        label=payload.label,
        key_hash=hash_key(raw_key),
        can_write=payload.can_write,
    )
    db.add(api_key)
    await db.flush()
    await _log(db, project_id=project.id, actor="admin", action="apikey.created", key_name=payload.label)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreatedOut(id=api_key.id, label=api_key.label, can_write=api_key.can_write, raw_key=raw_key)


@router.get("/projects/{slug}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(slug: str, db: AsyncSession = Depends(get_db)):
    project = await _get_project_or_404(db, slug)
    result = await db.execute(select(ProjectApiKey).where(ProjectApiKey.project_id == project.id))
    return result.scalars().all()


@router.delete("/projects/{slug}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(slug: str, key_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await _get_project_or_404(db, slug)
    result = await db.execute(
        select(ProjectApiKey).where(ProjectApiKey.id == key_id, ProjectApiKey.project_id == project.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")

    api_key.revoked_at = datetime.now(timezone.utc)
    await _log(db, project_id=project.id, actor="admin", action="apikey.revoked", key_name=api_key.label)
    await db.commit()


@router.get("/audit-log", response_model=list[AuditLogOut])
async def get_audit_log(project_slug: str | None = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(AuditLogEntry).order_by(AuditLogEntry.created_at.desc()).limit(min(limit, 500))
    if project_slug:
        project = await _get_project_or_404(db, project_slug)
        stmt = (
            select(AuditLogEntry)
            .where(AuditLogEntry.project_id == project.id)
            .order_by(AuditLogEntry.created_at.desc())
            .limit(min(limit, 500))
        )
    result = await db.execute(stmt)
    return result.scalars().all()
