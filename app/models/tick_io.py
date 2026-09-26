from __future__ import annotations

from pydantic import BaseModel

from app.models.common import CTAKind, SendAs


class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = []


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: SendAs
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: CTAKind
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction]
