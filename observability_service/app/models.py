import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LogEntry(Base):
    """
    A single structured log line from any app. Append-only, no grouping -
    for grouped exception tracking see ErrorIssue/ErrorOccurrence below.
    """

    __tablename__ = "log_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(String(30), nullable=False, default="production")
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # debug|info|warning|error|critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ErrorIssue(Base):
    """
    A 'bucket' that occurrences of the same underlying error get grouped
    into, the way Sentry-style trackers work - so 10,000 occurrences of
    the same bug show up as one issue with a count, not 10,000 rows to
    scroll through.
    """

    __tablename__ = "error_issues"
    __table_args__ = (UniqueConstraint("service_name", "environment", "fingerprint", name="uq_issue_fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(String(30), nullable=False, default="production")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex digest

    exception_type: Mapped[str] = mapped_column(String(150), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")  # open|resolved|ignored
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    occurrences: Mapped[list["ErrorOccurrence"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )


class ErrorOccurrence(Base):
    """Every individual time an issue's error happened, with full context."""

    __tablename__ = "error_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("error_issues.id", ondelete="CASCADE"))

    message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issue: Mapped["ErrorIssue"] = relationship(back_populates="occurrences")
