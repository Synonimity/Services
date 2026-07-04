import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,49}$")
    name: str
    description: str = ""
    template_keys: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    template_keys: list[str] | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    template_keys: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreate(BaseModel):
    label: str
    can_write: bool = False


class ApiKeyCreatedOut(BaseModel):
    id: uuid.UUID
    label: str
    can_write: bool
    raw_key: str  # shown exactly once, at creation


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    label: str
    can_write: bool
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class SecretSetRequest(BaseModel):
    entries: dict[str, str] = Field(min_length=1)


class SecretKeyOut(BaseModel):
    key: str
    updated_at: datetime
    is_sensitive: bool


class SecretRevealOut(BaseModel):
    key: str
    value: str
    updated_at: datetime


class ValidationResult(BaseModel):
    missing_required: list[str]
    present: list[str]
    unrecognized: list[str]


class AuditLogOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    actor: str
    action: str
    environment: str | None
    key_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
