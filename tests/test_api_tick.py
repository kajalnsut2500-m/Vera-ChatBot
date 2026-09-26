from __future__ import annotations

import pytest
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
