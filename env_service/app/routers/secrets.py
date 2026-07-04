from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import templates_catalog
from app.crypto import DecryptionError, decrypt_value, encrypt_value
from app.database import get_db
from app.dependencies import ProjectAuth, get_project_auth, limiter, require_write
from app.dotenv_format import render_dotenv
from app.models import AuditLogEntry, Secret
from app.schemas import SecretKeyOut, SecretRevealOut, SecretSetRequest, ValidationResult

router = APIRouter(prefix="/projects/{project_slug}/secrets/{environment}", tags=["secrets"])


async def _log(db: AsyncSession, *, project_id, actor: str, action: str, environment: str, key_name: str | None = None):
    db.add(AuditLogEntry(project_id=project_id, actor=actor, action=action, environment=environment, key_name=key_name))


def _is_sensitive(project_template_keys: list[str], key: str) -> bool:
    known = templates_catalog.all_known_vars_for(project_template_keys)
    spec = known.get(key)
    return spec.sensitive if spec else True  # default to treating unknown keys as sensitive


@router.get("", response_model=list[SecretKeyOut])
async def list_secret_keys(
    environment: str,
    auth: ProjectAuth = Depends(get_project_auth),
    db: AsyncSession = Depends(get_db),
):
    """Lists keys and metadata only - never values. Use the single-key GET or /export to reveal values."""
    result = await db.execute(
        select(Secret).where(Secret.project_id == auth.project.id, Secret.environment == environment)
    )
    rows = result.scalars().all()
    return [
        SecretKeyOut(key=r.key, updated_at=r.updated_at, is_sensitive=_is_sensitive(auth.project.template_keys, r.key))
        for r in rows
    ]


@router.get("/{key}", response_model=SecretRevealOut)
@limiter.limit("60/minute")
async def get_secret_value(
    request: Request,
    environment: str,
    key: str,
    auth: ProjectAuth = Depends(get_project_auth),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Secret).where(
            Secret.project_id == auth.project.id, Secret.environment == environment, Secret.key == key
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")

    try:
        value = decrypt_value(row.encrypted_value)
    except DecryptionError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not decrypt this value.")

    await _log(db, project_id=auth.project.id, actor=auth.actor_label, action="secret.read", environment=environment, key_name=key)
    await db.commit()

    return SecretRevealOut(key=row.key, value=value, updated_at=row.updated_at)


@router.put("", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def set_secrets(
    request: Request,
    environment: str,
    payload: SecretSetRequest,
    auth: ProjectAuth = Depends(get_project_auth),
    db: AsyncSession = Depends(get_db),
):
    require_write(auth)

    for key, value in payload.entries.items():
        result = await db.execute(
            select(Secret).where(
                Secret.project_id == auth.project.id, Secret.environment == environment, Secret.key == key
            )
        )
        row = result.scalar_one_or_none()
        encrypted = encrypt_value(value)

        if row is None:
            db.add(Secret(project_id=auth.project.id, environment=environment, key=key, encrypted_value=encrypted))
        else:
            row.encrypted_value = encrypted

        await _log(db, project_id=auth.project.id, actor=auth.actor_label, action="secret.write", environment=environment, key_name=key)

    await db.commit()
    return {"updated": list(payload.entries.keys())}


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    environment: str,
    key: str,
    auth: ProjectAuth = Depends(get_project_auth),
    db: AsyncSession = Depends(get_db),
):
    require_write(auth)
    result = await db.execute(
        select(Secret).where(
            Secret.project_id == auth.project.id, Secret.environment == environment, Secret.key == key
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found.")

    await db.delete(row)
    await _log(db, project_id=auth.project.id, actor=auth.actor_label, action="secret.delete", environment=environment, key_name=key)
    await db.commit()


@router.get("/_/validate", response_model=ValidationResult)
async def validate_secrets(
    environment: str,
    auth: ProjectAuth = Depends(get_project_auth),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Secret.key).where(Secret.project_id == auth.project.id, Secret.environment == environment)
    )
    present_keys = set(result.scalars().all())

    required = templates_catalog.required_vars_for(auth.project.template_keys)
    known = templates_catalog.all_known_vars_for(auth.project.template_keys)

    missing_required = sorted(set(required.keys()) - present_keys)
    unrecognized = sorted(present_keys - set(known.keys()))

    return ValidationResult(missing_required=missing_required, present=sorted(present_keys), unrecognized=unrecognized)


@router.get("/_/export")
@limiter.limit("20/minute")
async def export_dotenv(
    request: Request,
    environment: str,
    auth: ProjectAuth = Depends(get_project_auth),
    db: AsyncSession = Depends(get_db),
):
    """Returns a ready-to-save .env file. Treated as sensitive as a bulk reveal - requires write scope."""
    require_write(auth)

    result = await db.execute(
        select(Secret).where(Secret.project_id == auth.project.id, Secret.environment == environment)
    )
    rows = result.scalars().all()

    entries = {}
    for row in rows:
        try:
            entries[row.key] = decrypt_value(row.encrypted_value)
        except DecryptionError:
            continue  # skip corrupted rows rather than failing the whole export

    await _log(db, project_id=auth.project.id, actor=auth.actor_label, action="secret.export", environment=environment)
    await db.commit()

    body = render_dotenv(entries)
    return Response(content=body, media_type="text/plain")
