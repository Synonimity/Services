import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import alerting
from app.config import get_settings
from app.database import get_db
from app.dependencies import limiter, require_api_key
from app.fingerprint import compute_fingerprint
from app.models import ErrorIssue, ErrorOccurrence
from app.schemas import (
    ErrorIssueDetailOut,
    ErrorIssueOut,
    ErrorReportRequest,
    ErrorReportResponse,
)

settings = get_settings()
router = APIRouter(prefix="/errors", tags=["errors"])


@router.post("/report", response_model=ErrorReportResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("120/minute")
async def report_error(
    request: Request,
    payload: ErrorReportRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    fingerprint = payload.fingerprint_override or compute_fingerprint(
        service_name=payload.service_name,
        environment=payload.environment,
        exception_type=payload.exception_type,
        message=payload.message,
    )

    result = await db.execute(
        select(ErrorIssue).where(
            ErrorIssue.service_name == payload.service_name,
            ErrorIssue.environment == payload.environment,
            ErrorIssue.fingerprint == fingerprint,
        )
    )
    issue = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    is_new_issue = issue is None
    is_regression = False

    if issue is None:
        issue = ErrorIssue(
            service_name=payload.service_name,
            environment=payload.environment,
            fingerprint=fingerprint,
            exception_type=payload.exception_type,
            title=payload.message[:300],
            status="open",
            occurrence_count=1,
            first_seen=now,
            last_seen=now,
        )
        db.add(issue)
        await db.flush()
    else:
        is_regression = issue.status == "resolved"
        issue.occurrence_count += 1
        issue.last_seen = now
        if is_regression:
            issue.status = "open"

    occurrence = ErrorOccurrence(
        issue_id=issue.id,
        message=payload.message,
        stack_trace=payload.stack_trace,
        context=payload.context,
        external_user_id=payload.external_user_id,
        request_id=payload.request_id,
    )
    db.add(occurrence)
    await db.commit()
    await db.refresh(occurrence)

    if (is_new_issue and settings.alert_on_new_issues) or (is_regression and settings.alert_on_regressions):
        background_tasks.add_task(
            alerting.notify_issue,
            title=issue.title,
            message=payload.message,
            service_name=payload.service_name,
            environment=payload.environment,
            is_regression=is_regression,
        )

    return ErrorReportResponse(
        issue_id=issue.id,
        occurrence_id=occurrence.id,
        is_new_issue=is_new_issue,
        is_regression=is_regression,
        occurrence_count=issue.occurrence_count,
    )


@router.get("", response_model=list[ErrorIssueOut], dependencies=[Depends(require_api_key)])
async def list_issues(
    service_name: str | None = None,
    environment: str | None = None,
    issue_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ErrorIssue)
    if service_name:
        stmt = stmt.where(ErrorIssue.service_name == service_name)
    if environment:
        stmt = stmt.where(ErrorIssue.environment == environment)
    if issue_status:
        stmt = stmt.where(ErrorIssue.status == issue_status)

    stmt = stmt.order_by(ErrorIssue.last_seen.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def _get_issue_or_404(db: AsyncSession, issue_id: uuid.UUID) -> ErrorIssue:
    result = await db.execute(select(ErrorIssue).where(ErrorIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    return issue


@router.get("/{issue_id}", response_model=ErrorIssueDetailOut, dependencies=[Depends(require_api_key)])
async def get_issue(issue_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    issue = await _get_issue_or_404(db, issue_id)
    result = await db.execute(
        select(ErrorOccurrence)
        .where(ErrorOccurrence.issue_id == issue.id)
        .order_by(ErrorOccurrence.created_at.desc())
        .limit(20)
    )
    occurrences = result.scalars().all()
    return ErrorIssueDetailOut(**ErrorIssueOut.model_validate(issue).model_dump(), recent_occurrences=occurrences)


@router.post("/{issue_id}/resolve", dependencies=[Depends(require_api_key)])
async def resolve_issue(issue_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    issue = await _get_issue_or_404(db, issue_id)
    issue.status = "resolved"
    await db.commit()
    return {"status": "resolved"}


@router.post("/{issue_id}/ignore", dependencies=[Depends(require_api_key)])
async def ignore_issue(issue_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    issue = await _get_issue_or_404(db, issue_id)
    issue.status = "ignored"
    await db.commit()
    return {"status": "ignored"}
