import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr


class CheckoutRequest(BaseModel):
    external_user_id: str
    email: EmailStr
    name_first: str | None = None
    name_last: str | None = None
    plan_code: str


class CheckoutResponse(BaseModel):
    redirect_url: str
    m_payment_id: str


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    plan_code: str
    status: str
    next_billing_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanOut(BaseModel):
    code: str
    name: str
    amount: float
    frequency: int
    cycles: int

    model_config = {"from_attributes": True}
