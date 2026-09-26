from __future__ import annotations

import re
from datetime import datetime, timezone

from app.db.database import get_db
from app.models.common import ActionKind, CTAKind
from app.models.reply_io import ReplyResponse

# ── intent patterns ───────────────────────────────────────────────────────────

_AUTO_REPLY = re.compile(
    r"(thank you for contacting|our team will respond|this is an automated|"
    r"aapki jaankari ke liye|automated (assistant|response)|"
    r"main ek automated|we will get back|hum jald se jald|"
    r"i am an automated|auto.?reply)",
    re.I,
)

_ACCEPT = re.compile(
    r"\b(yes|ok|okay|proceed|go ahead|let'?s do it|confirm|done|sure|"
    r"haan|theek hai|chalega|chal|judrna|join karna|send it|go on|start)\b",
    re.I,
)

_REFUSE = re.compile(
    r"\b(no|nahi|stop|not interested|leave me|band karo|"
    r"don'?t (message|contact|send)|unsubscribe|opt.?out|remove me)\b",
    re.I,
)

_DELAY = re.compile(
    r"\b(later|busy|call back|baad mein|abhi nahi|not now|"
    r"in a (while|bit)|some other time|will check later)\b",
    re.I,
)

_ABUSE = re.compile(
    r"\b(spam|useless|idiot|shut up|bakwaas|bekar|"
    r"fraud|scam|why (are you|keep)|stop bothering)\b",
    re.I,
)


def _classify(message: str) -> str:
    if _AUTO_REPLY.search(message):
        return "auto_reply"
    if _REFUSE.search(message):
        return "refuse"
    if _DELAY.search(message):
        return "delay"
    if _ABUSE.search(message):
        return "abuse"
    if _ACCEPT.search(message):
        return "accept"
    return "normal"


# ── action-next-step responses keyed by trigger kind ─────────────────────────

_ACTION_BODY: dict[str, str] = {
    "research_digest": "Pulling the abstract now — I'll also draft a patient-ed WhatsApp you can share. Give me 2 minutes.",
    "regulation_change": "Reviewing your current setup against the new limits and will flag the specific items that need attention.",
    "perf_dip": "Pulling your performance breakdown — three things usually cause this and I'll check which applies to you.",
    "perf_spike": "Drafting a follow-up offer to capture this momentum. Will share a draft for your review shortly.",
    "renewal_due": "Initiating renewal for your plan. You'll receive confirmation once processed.",
    "recall_due": "Confirming the slot and sending the booking details now.",
    "festival_upcoming": "Drafting a seasonal offer based on your existing listing. Will share a draft in 2 minutes.",
    "dormant_with_vera": "Starting a quick profile audit — will report the top 3 changes to improve your CTR.",
    "milestone_reached": "Drafting a Google post to mark this milestone. Will share for your review.",
    "curious_ask_due": "Thanks — that helps me send more relevant suggestions.",
    "review_theme_emerged": "Drafting a response strategy based on this theme. Will share shortly.",
}

_DEFAULT_ACTION_BODY = "On it — I'll share the next step shortly. Give me 2 minutes."


async def _get_meta(conversation_id: str) -> dict | None:
    db = get_db()
    async with db.execute(
        "SELECT * FROM conversation_meta WHERE conversation_id = ?", (conversation_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return dict(row)


async def _upsert_meta(conversation_id: str, merchant_id: str | None, updates: dict) -> None:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    existing = await _get_meta(conversation_id)
    if existing is None:
        await db.execute(
            "INSERT INTO conversation_meta "
            "(conversation_id, merchant_id, auto_reply_count, last_bot_body, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (conversation_id, merchant_id,
             updates.get("auto_reply_count", 0),
             updates.get("last_bot_body", ""),
             now, now),
        )
    else:
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [now, conversation_id]
        await db.execute(
            f"UPDATE conversation_meta SET {sets}, updated_at = ? WHERE conversation_id = ?",
            vals,
        )
    await db.commit()


async def _record_turn(conversation_id: str, role: str, body: str, turn: int) -> None:
    db = get_db()
    ts = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO conversations (conversation_id, turn_number, role, body, ts) VALUES (?,?,?,?,?)",
        (conversation_id, turn, role, body, ts),
    )
    await db.commit()


async def route(
    conversation_id: str,
    merchant_id: str | None,
    message: str,
    turn_number: int,
) -> ReplyResponse:
    meta = await _get_meta(conversation_id)
    if meta is None:
        meta = {"auto_reply_count": 0, "trigger_id": None, "last_bot_body": ""}
        await _upsert_meta(conversation_id, merchant_id, {"auto_reply_count": 0, "last_bot_body": ""})

    intent = _classify(message)

    # Record inbound turn
    await _record_turn(conversation_id, "merchant", message, turn_number)

    if intent == "auto_reply":
        count = meta.get("auto_reply_count", 0) + 1
        await _upsert_meta(conversation_id, merchant_id, {"auto_reply_count": count})
        if count >= 2:
            return ReplyResponse(
                action=ActionKind.end,
                rationale="Auto-reply detected twice in a row — closing conversation.",
            )
        return ReplyResponse(
            action=ActionKind.wait,
            wait_seconds=14400,
            rationale="Auto-reply detected; backing off 4 hours to wait for the owner.",
        )

    if intent == "refuse":
        return ReplyResponse(
            action=ActionKind.end,
            rationale="Merchant opted out — closing conversation and suppressing future outreach.",
        )

    if intent in ("abuse",):
        return ReplyResponse(
            action=ActionKind.end,
            rationale="Off-mission message — closing politely without further engagement.",
        )

    if intent == "delay":
        return ReplyResponse(
            action=ActionKind.wait,
            wait_seconds=3600,
            rationale="Merchant asked for time — backing off 1 hour.",
        )

    # accept or normal — build grounded follow-up
    trigger_id = meta.get("trigger_id") or ""
    trigger_kind = trigger_id.rsplit("_", 1)[0] if trigger_id else ""

    # Look up the trigger to get its kind
    from app.core.context_store import get_context as _gc
    trg = await _gc("trigger", trigger_id) if trigger_id else None
    kind = trg.get("kind", "") if trg else ""

    if intent == "accept":
        body = _ACTION_BODY.get(kind, _DEFAULT_ACTION_BODY)
        reply_action = ActionKind.send
        cta = CTAKind.none
        rationale = f"Merchant accepted — switching to action mode for trigger kind={kind}."
    else:
        # normal follow-up: restate the CTA once, then back off
        last = meta.get("last_bot_body", "")
        body = "When you're ready, just reply YES to proceed — or STOP to skip this one."
        reply_action = ActionKind.send
        cta = CTAKind.binary_yes_stop
        rationale = "Normal reply — restating CTA once before backing off."

    await _record_turn(conversation_id, "vera", body, turn_number + 1)
    await _upsert_meta(conversation_id, merchant_id, {"last_bot_body": body, "auto_reply_count": 0})

    return ReplyResponse(action=reply_action, body=body, cta=cta, rationale=rationale)
