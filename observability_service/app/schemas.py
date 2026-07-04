import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LogLevel = Literal["debug", "info", "warning", "error", "critical"]
IssueStatus = Literal["open", "resolved", "ignored"]


class LogEntryIn(BaseModel):
    service_name: str
    environment: str = "production"
    level: LogLevel = "info"
    message: str
    context: dict = Field(default_factory=dict)
    external_user_id: str | None = None
    request_id: str | None = None


class LogIngestRequest(BaseModel):
    entries: list[LogEntryIn] = Field(min_length=1, max_length=500)


class LogEntryOut(BaseModel):
    id: uuid.UUID
    service_name: str
    environment: str
    level: str
    message: str
    context: dict
    external_user_id: str | None
    request_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorReportRequest(BaseModel):
    service_name: str
    environment: str = "production"
    exception_type: str
    message: str
    stack_trace: str | None = None
    context: dict = Field(default_factory=dict)
    external_user_id: str | None = None
    request_id: str | None = None
    # Override automatic grouping when you know better than the default
    # heuristic (e.g. you want to group by a specific error code instead).
    fingerprint_override: str | None = None


class ErrorReportResponse(BaseModel):
    issue_id: uuid.UUID
    occurrence_id: uuid.UUID
    is_new_issue: bool
    is_regression: bool
    occurrence_count: int


class ErrorIssueOut(BaseModel):
    id: uuid.UUID
    service_name: str
    environment: str
    exception_type: str
    title: str
    status: str
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime

    model_config = {"from_attributes": True}


class ErrorOccurrenceOut(BaseModel):
    id: uuid.UUID
    message: str
    stack_trace: str | None
    context: dict
    external_user_id: str | None
    request_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorIssueDetailOut(ErrorIssueOut):
    recent_occurrences: list[ErrorOccurrenceOut]
