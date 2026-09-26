from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.context_store import store_context
from app.models.context_io import (
    ContextPushError,
    ContextPushOK,
    ContextPushRequest,
    ContextPushStale,
)
from app.models.common import Scope

router = APIRouter()

_VALID_SCOPES = {s.value for s in Scope}


@router.post("/context")
async def push_context(body: ContextPushRequest):
    scope_val = body.scope.value

    stored, current_version = await store_context(
        scope_val, body.context_id, body.version, body.payload
    )

    if not stored:
        # current_version > body.version — stale push
        return JSONResponse(
            status_code=409,
            content=ContextPushStale(current_version=current_version).model_dump(),
        )

    now = datetime.now(timezone.utc).isoformat()
    return ContextPushOK(
        ack_id=f"ack_{body.context_id}_v{body.version}",
        stored_at=now,
    )
