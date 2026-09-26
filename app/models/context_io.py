from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.common import Scope


class ContextPushRequest(BaseModel):
    scope: Scope
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class ContextPushOK(BaseModel):
    accepted: bool = True
    ack_id: str
    stored_at: str


class ContextPushStale(BaseModel):
    accepted: bool = False
    reason: str = "stale_version"
    current_version: int


class ContextPushError(BaseModel):
    accepted: bool = False
    reason: str
    details: str = ""
