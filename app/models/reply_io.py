from __future__ import annotations

from pydantic import BaseModel

from app.models.common import ActionKind, CTAKind


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str = "merchant"
    message: str
    received_at: str
    turn_number: int


class ReplyResponse(BaseModel):
    action: ActionKind
    body: str | None = None
    cta: CTAKind | None = None
    rationale: str
    wait_seconds: int | None = None
