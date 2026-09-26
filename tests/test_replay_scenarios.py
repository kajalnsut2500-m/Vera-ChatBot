from __future__ import annotations

import pytest
from httpx import AsyncClient

PUSH = "/v1/context"
TICK = "/v1/tick"
REPLY = "/v1/reply"
_NOW = "2026-09-26T10:00:00Z"
_MID = "m_001_drmeera_dentist_delhi"


def _ctx(scope, cid, payload, v=1):
    return {"scope": scope, "context_id": cid, "version": v,
            "payload": payload, "delivered_at": _NOW}


def _reply(conv_id, msg, turn, mid=_MID):
    return {"conversation_id": conv_id, "merchant_id": mid,
            "from_role": "merchant", "message": msg,
            "received_at": _NOW, "turn_number": turn}


# ── Scenario 1: auto-reply hell ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_reply_ends_after_two_repeats(client):
    auto = "Thank you for contacting us! Our team will respond shortly."
    conv = "conv_replay_ar"
    r1 = await client.post(REPLY, json=_reply(conv, auto, 2))
    assert r1.json()["action"] in ("wait", "end")
    r2 = await client.post(REPLY, json=_reply(conv, auto, 3))
    assert r2.json()["action"] == "end"


# ── Scenario 2: explicit acceptance ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_explicit_accept_triggers_action_mode(client, category_dentists, merchant_drmeera, trigger_research_active):
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", _MID, merchant_drmeera))
    await client.post(PUSH, json=_ctx("trigger", trigger_research_active["id"], trigger_research_active))

    tick_resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    actions = tick_resp.json()["actions"]
    assert actions, "Need at least one action to continue"

    conv_id = actions[0]["conversation_id"]
    reply_resp = await client.post(REPLY, json=_reply(conv_id, "Ok, let's do it!", 2))
    body = reply_resp.json()

    assert body["action"] == "send"
    # Must not ask more qualifying questions — should be in action mode
    qualifying = ["would you", "do you want", "can you tell me"]
    assert not any(q in body.get("body", "").lower() for q in qualifying)


# ── Scenario 3: hard refusal ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hard_refusal_ends_conversation(client):
    conv = "conv_replay_refuse"
    resp = await client.post(REPLY, json=_reply(conv, "Not interested. Stop messaging me.", 2))
    assert resp.json()["action"] == "end"


# ── Scenario 4: hostile / off-topic ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_hostile_message_ends_politely(client):
    conv = "conv_replay_hostile"
    resp = await client.post(REPLY, json=_reply(conv, "This is spam, stop bothering me.", 2))
    assert resp.json()["action"] == "end"


# ── Scenario 5: new context injection ────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_context_injection_reflected_in_tick(client, category_dentists, merchant_drmeera):
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", _MID, merchant_drmeera))

    new_trg = {
        "id": "trg_new_inject", "scope": "merchant", "kind": "perf_dip",
        "merchant_id": _MID, "customer_id": None,
        "payload": {"metric": "views", "delta_pct": -0.35, "window": "7d"},
        "urgency": 4, "suppression_key": "inject:new:unique_test",
        "expires_at": "2030-01-01T00:00:00Z",
    }
    # Inject new trigger mid-test
    await client.post(PUSH, json=_ctx("trigger", new_trg["id"], new_trg))

    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [new_trg["id"]]})
    actions = resp.json()["actions"]
    assert len(actions) == 1
    # Verify the body references actual numbers from the trigger payload
    body = actions[0]["body"]
    assert "35" in body or "views" in body
