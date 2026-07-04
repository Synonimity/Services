from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import limiter, require_api_key
from app.models import LogEntry
from app.schemas import LogEntryOut, LogIngestRequest

settings = get_settings()
router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
async def ingest_logs(request: Request, payload: LogIngestRequest, db: AsyncSession = Depends(get_db)):
    rows = [
        LogEntry(
            service_name=e.service_name,
            environment=e.environment,
            level=e.level,
            message=e.message,
            context=e.context,
            external_user_id=e.external_user_id,
            request_id=e.request_id,
        )
        for e in payload.entries
    ]
    db.add_all(rows)
    await db.commit()
    return {"ingested": len(rows)}


@router.get("", response_model=list[LogEntryOut], dependencies=[Depends(require_api_key)])
async def query_logs(
    service_name: str | None = None,
    environment: str | None = None,
    level: str | None = None,
    external_user_id: str | None = None,
    request_id: str | None = None,
    search: str | None = Query(None, description="Substring match on message"),
    since: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LogEntry)
    if service_name:
        stmt = stmt.where(LogEntry.service_name == service_name)
    if environment:
        stmt = stmt.where(LogEntry.environment == environment)
    if level:
        stmt = stmt.where(LogEntry.level == level)
    if external_user_id:
        stmt = stmt.where(LogEntry.external_user_id == external_user_id)
    if request_id:
        stmt = stmt.where(LogEntry.request_id == request_id)
    if search:
        stmt = stmt.where(LogEntry.message.ilike(f"%{search}%"))
    if since:
        stmt = stmt.where(LogEntry.created_at >= since)

    stmt = stmt.order_by(LogEntry.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/cleanup", dependencies=[Depends(require_api_key)])
async def cleanup_old_logs(db: AsyncSession = Depends(get_db)):
    """
    Deletes log entries older than LOG_RETENTION_DAYS. Not run
    automatically - wire this up to a daily cron (e.g. Supabase's
    pg_cron, or any external scheduler hitting this endpoint) since this
    service has no built-in scheduler. See README.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.log_retention_days)
    result = await db.execute(delete(LogEntry).where(LogEntry.created_at < cutoff))
    await db.commit()
    return {"deleted": result.rowcount}
