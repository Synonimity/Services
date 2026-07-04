import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SendEmailRequest(BaseModel):
    template_name: str
    to_email: EmailStr
    to_name: str | None = None
    external_user_id: str | None = None
    variables: dict = Field(default_factory=dict)
    # If set and already used, the existing send is returned instead of
    # sending a duplicate - safe to retry from your backend on a timeout.
    idempotency_key: str | None = None


class SendEmailResponse(BaseModel):
    id: uuid.UUID
    status: str
    provider_message_id: str | None


class NotificationOut(BaseModel):
    id: uuid.UUID
    recipient_email: str
    template_name: str
    subject: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertRequest(BaseModel):
    channel: Literal["slack", "discord"]
    title: str
    message: str
    severity: Literal["info", "warning", "error"] = "info"
    fields: dict[str, str] = Field(default_factory=dict)
