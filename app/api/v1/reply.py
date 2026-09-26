from __future__ import annotations

from fastapi import APIRouter

from app.core.reply_router import route
from app.models.reply_io import ReplyRequest, ReplyResponse

router = APIRouter()


@router.post("/reply", response_model=ReplyResponse)
async def reply(body: ReplyRequest) -> ReplyResponse:
    return await route(
        conversation_id=body.conversation_id,
        merchant_id=body.merchant_id,
        message=body.message,
        turn_number=body.turn_number,
    )
