from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.context_store import get_context
from app.core.composer import compose
from app.core.eligibility import is_eligible, rank, record_suppression
from app.db.database import get_db
from app.models.tick_io import TickRequest, TickResponse

router = APIRouter()

_MAX_ACTIONS = 20


@router.post("/tick", response_model=TickResponse)
async def tick(body: TickRequest) -> TickResponse:
    try:
        now = datetime.fromisoformat(body.now.replace("Z", "+00:00"))
    except ValueError:
        now = datetime.now(timezone.utc)

    # Load all candidate triggers
    candidates: list[dict] = []
    for tid in body.available_triggers:
        trg = await get_context("trigger", tid)
        if trg:
            candidates.append(trg)

    eligible = [t for t in rank(candidates) if await is_eligible(t, now)]

    actions = []
    db = get_db()

    for trg in eligible:
        if len(actions) >= _MAX_ACTIONS:
            break

        merchant_id = trg.get("merchant_id")
        customer_id = trg.get("customer_id")

        if not merchant_id:
            continue

        merchant = await get_context("merchant", merchant_id)
        if not merchant:
            continue

        category_slug = merchant.get("category_slug", "")
        category = await get_context("category", category_slug)
        if not category:
            continue

        customer = await get_context("customer", customer_id) if customer_id else None

        # Collect prior bodies for this merchant to enforce anti-repetition
        prior: list[str] = []
        conv_id_check = f"conv_{merchant_id}_{trg.get('id', '')}"
        async with db.execute(
            "SELECT body FROM conversations WHERE conversation_id = ? AND role = 'vera'",
            (conv_id_check,),
        ) as cur:
            async for row in cur:
                prior.append(row["body"])

        action = compose(trg, merchant, category, customer, prior)
        if action is None:
            continue

        # Record suppression and conversation
        await record_suppression(trg.get("suppression_key", ""), action.conversation_id)
        fired_at = now.isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO conversation_meta "
            "(conversation_id, merchant_id, customer_id, trigger_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (action.conversation_id, merchant_id, customer_id,
             trg.get("id", ""), fired_at, fired_at),
        )
        await db.execute(
            "INSERT OR REPLACE INTO conversations (conversation_id, turn_number, role, body, ts) VALUES (?,?,?,?,?)",
            (action.conversation_id, 1, "vera", action.body, fired_at),
        )
        await db.execute(
            "UPDATE conversation_meta SET last_bot_body = ?, updated_at = ? WHERE conversation_id = ?",
            (action.body, fired_at, action.conversation_id),
        )
        await db.commit()

        actions.append(action)

    return TickResponse(actions=actions)
