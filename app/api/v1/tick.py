from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.context_store import get_context
from app.core.composer import compose
from app.core.eligibility import is_eligible, rank, record_suppression
from app.core.gemini_polish import polish
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

        # Scope prior bodies to the exact recipient of this trigger:
        # - merchant-facing (customer_id IS NULL): all prior merchant-facing messages
        #   for this merchant, regardless of which trigger sent them.
        # - customer-facing: only messages for this specific merchant+customer pair,
        #   so a message sent to customer A never suppresses a valid send to customer B.
        prior: list[str] = []
        if customer_id:
            prior_query = (
                "SELECT c.body FROM conversations c "
                "JOIN conversation_meta cm ON c.conversation_id = cm.conversation_id "
                "WHERE cm.merchant_id = ? AND cm.customer_id = ? AND c.role = 'vera'"
            )
            prior_params = (merchant_id, customer_id)
        else:
            prior_query = (
                "SELECT c.body FROM conversations c "
                "JOIN conversation_meta cm ON c.conversation_id = cm.conversation_id "
                "WHERE cm.merchant_id = ? AND cm.customer_id IS NULL AND c.role = 'vera'"
            )
            prior_params = (merchant_id,)
        async with db.execute(prior_query, prior_params) as cur:
            async for row in cur:
                prior.append(row["body"])

        action = compose(trg, merchant, category, customer, prior)
        if action is None:
            continue

        # Optional Gemini copy-polish — falls back to deterministic draft on any error
        voice_rules = category.get("voice", {}).get("rules", [])
        polished_body = await polish(
            action.body, action.cta.value, action.template_params, voice_rules
        )
        # Only use polished body if it isn't a repeat of something already sent.
        # compose() already confirmed action.body (deterministic draft D) is not in prior;
        # but a previous tick may have stored a polished variant P that Gemini re-produces.
        if polished_body != action.body and polished_body not in prior:
            action = action.model_copy(update={"body": polished_body})

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
