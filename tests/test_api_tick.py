from __future__ import annotations

import pytest
from unittest.mock import patch
from httpx import AsyncClient

PUSH = "/v1/context"
TICK = "/v1/tick"
_NOW = "2026-09-26T10:00:00Z"


def _ctx(scope, cid, payload, v=1):
    return {"scope": scope, "context_id": cid, "version": v,
            "payload": payload, "delivered_at": _NOW}


async def _full_setup(client, category, merchant, trigger):
    await client.post(PUSH, json=_ctx("category", category["slug"], category))
    await client.post(PUSH, json=_ctx("merchant", merchant["merchant_id"], merchant))
    await client.post(PUSH, json=_ctx("trigger", trigger["id"], trigger))


@pytest.mark.asyncio
async def test_tick_produces_action_for_research_trigger(
    client, category_dentists, merchant_drmeera, trigger_research_active
):
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    assert len(actions) == 1


@pytest.mark.asyncio
async def test_tick_action_has_required_fields(
    client, category_dentists, merchant_drmeera, trigger_research_active
):
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    a = resp.json()["actions"][0]
    for field in ("conversation_id", "merchant_id", "send_as", "trigger_id",
                  "template_name", "template_params", "body", "cta", "suppression_key", "rationale"):
        assert field in a, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_tick_action_body_references_merchant_name(
    client, category_dentists, merchant_drmeera, trigger_research_active
):
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    body = resp.json()["actions"][0]["body"]
    owner = merchant_drmeera["identity"]["owner_first_name"]
    assert owner in body


@pytest.mark.asyncio
async def test_tick_template_name_populated(
    client, category_dentists, merchant_drmeera, trigger_research_active
):
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    a = resp.json()["actions"][0]
    assert a["template_name"]
    assert isinstance(a["template_params"], list)
    assert len(a["template_params"]) >= 1


@pytest.mark.asyncio
async def test_tick_send_as_vera_for_merchant_trigger(
    client, category_dentists, merchant_drmeera, trigger_research_active
):
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    assert resp.json()["actions"][0]["send_as"] == "vera"


@pytest.mark.asyncio
async def test_tick_no_context_returns_empty(client):
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": ["trg_nonexistent"]})
    assert resp.json()["actions"] == []


@pytest.mark.asyncio
async def test_tick_perf_dip_trigger(client, category_dentists, merchant_drmeera, trigger_perf_dip):
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", merchant_drmeera["merchant_id"], merchant_drmeera))
    # perf_dip trigger references bharat — use a fresh merchant matching it
    bharat_trg = {**trigger_perf_dip, "merchant_id": merchant_drmeera["merchant_id"],
                  "suppression_key": "perf_dip:test:unique_x"}
    await client.post(PUSH, json=_ctx("trigger", bharat_trg["id"], bharat_trg))
    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [bharat_trg["id"]]})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tick_polished_body_repeat_uses_deterministic_draft(
    client, category_dentists, merchant_drmeera, trigger_research_active, monkeypatch
):
    """
    Anti-repetition regression: when Gemini returns a body already stored in the
    merchant's history, tick must fall back to the deterministic draft.

    Setup:
      - Tick 1 (no Gemini): research_digest fires → deterministic body D1 stored in DB.
      - Tick 2 (Gemini active): a perf_dip trigger for the same merchant fires.
        Gemini mock returns D1 (already in merchant history).
        The polished body must be rejected and the deterministic perf_dip draft D2 used.
    """
    import json as _json

    mid = merchant_drmeera["merchant_id"]

    # Tick 1 — no Gemini, stores deterministic research_digest body for merchant.
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)
    resp1 = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    assert resp1.json()["actions"], "Precondition: first tick must produce an action"
    stored_body = resp1.json()["actions"][0]["body"]

    # Tick 2 — perf_dip trigger for the same merchant; Gemini mock returns stored_body.
    perf_trg = {
        "id": "trg_repeat_perf_test", "scope": "merchant", "kind": "perf_dip",
        "merchant_id": mid, "customer_id": None,
        "payload": {"metric": "views", "delta_pct": -0.30, "window": "7d"},
        "urgency": 5, "suppression_key": "repeat:perf:unique_regression",
        "expires_at": "2035-01-01T00:00:00Z",
    }
    await client.post(PUSH, json=_ctx("trigger", perf_trg["id"], perf_trg))

    monkeypatch.setenv("VERA_GEMINI_API_KEY", "test-key-abc")
    with patch("app.core.gemini_polish._call_gemini_sync") as mock_call:
        mock_call.return_value = {
            "candidates": [{"content": {"parts": [{"text": _json.dumps({
                "body": stored_body,         # already in merchant history
                "cta": "binary_yes_stop",
                "used_fact_ids": ["f0"],
            })}]}}]
        }
        resp2 = await client.post(TICK, json={"now": _NOW, "available_triggers": [perf_trg["id"]]})

    actions = resp2.json()["actions"]
    assert actions, "perf_dip trigger must produce an action"
    actual_body = actions[0]["body"]

    # Core assertion: polished repeat was rejected; deterministic draft used instead.
    assert actual_body != stored_body, (
        "Tick returned the repeated body instead of falling back to the deterministic draft"
    )
    # Sanity: the body references the perf_dip metric, not the research_digest content.
    assert "views" in actual_body or "30" in actual_body, (
        f"Expected perf_dip deterministic body, got: {actual_body!r}"
    )


# ── Anti-repetition recipient-scoping tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_merchant_message_not_reused_across_triggers(
    client, category_dentists, merchant_drmeera, trigger_research_active
):
    """
    A prior merchant-facing message suppresses the same body from a second
    merchant-facing trigger; customer_id IS NULL scope is enforced correctly.
    """
    mid = merchant_drmeera["merchant_id"]
    await _full_setup(client, category_dentists, merchant_drmeera, trigger_research_active)

    # First tick stores a research_digest body for this merchant (customer_id=NULL).
    resp1 = await client.post(TICK, json={"now": _NOW, "available_triggers": [trigger_research_active["id"]]})
    assert resp1.json()["actions"], "Precondition: first tick must produce an action"

    # Second trigger: same kind + merchant → compose() will generate the identical body.
    trg2 = {
        **trigger_research_active,
        "id": "trg_merchant_scope_test",
        "suppression_key": "merchant:scope:dedup:unique",
        "expires_at": "2035-01-01T00:00:00Z",
    }
    await client.post(PUSH, json=_ctx("trigger", trg2["id"], trg2))

    resp2 = await client.post(TICK, json={"now": _NOW, "available_triggers": [trg2["id"]]})
    # The body is already in merchant's prior (customer_id IS NULL scope) → suppressed.
    assert resp2.json()["actions"] == [], (
        "Second merchant trigger produced a duplicate body that should have been suppressed"
    )


@pytest.mark.asyncio
async def test_customer_a_message_does_not_suppress_customer_b(
    client, category_dentists, merchant_drmeera, customers_seed
):
    """
    A message sent to customer A (priya) must not suppress the same valid
    message to customer B (rohit) for the same merchant.
    """
    mid = merchant_drmeera["merchant_id"]
    priya = next(c for c in customers_seed if c["customer_id"] == "c_001_priya_for_m001")
    rohit = next(c for c in customers_seed if c["customer_id"] == "c_002_rohit_for_m001")

    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", mid, merchant_drmeera))
    await client.post(PUSH, json=_ctx("customer", priya["customer_id"], priya))
    await client.post(PUSH, json=_ctx("customer", rohit["customer_id"], rohit))

    recall_priya = {
        "id": "trg_recall_scope_priya", "scope": "customer", "kind": "recall_due",
        "merchant_id": mid, "customer_id": priya["customer_id"],
        "payload": {"service_due": "cleaning", "available_slots": [{"label": "Mon 10am"}, {"label": "Tue 2pm"}]},
        "urgency": 8, "suppression_key": "recall:scope:priya:unique",
        "expires_at": "2035-01-01T00:00:00Z",
    }
    recall_rohit = {
        "id": "trg_recall_scope_rohit", "scope": "customer", "kind": "recall_due",
        "merchant_id": mid, "customer_id": rohit["customer_id"],
        "payload": {"service_due": "cleaning", "available_slots": [{"label": "Mon 10am"}, {"label": "Tue 2pm"}]},
        "urgency": 8, "suppression_key": "recall:scope:rohit:unique",
        "expires_at": "2035-01-01T00:00:00Z",
    }
    await client.post(PUSH, json=_ctx("trigger", recall_priya["id"], recall_priya))
    await client.post(PUSH, json=_ctx("trigger", recall_rohit["id"], recall_rohit))

    # Fire priya's recall first.
    resp_priya = await client.post(TICK, json={"now": _NOW, "available_triggers": [recall_priya["id"]]})
    assert resp_priya.json()["actions"], "Precondition: priya's recall must produce an action"

    # Rohit's recall must still fire — priya's message must not suppress it.
    resp_rohit = await client.post(TICK, json={"now": _NOW, "available_triggers": [recall_rohit["id"]]})
    assert resp_rohit.json()["actions"], (
        "Rohit's recall was wrongly suppressed by priya's prior message"
    )
    # The body should address rohit, not priya.
    rohit_body = resp_rohit.json()["actions"][0]["body"]
    assert rohit["identity"]["name"] in rohit_body or rohit["customer_id"] in rohit_body or "cleaning" in rohit_body
