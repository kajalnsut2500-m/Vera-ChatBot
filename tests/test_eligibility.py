from __future__ import annotations

import pytest
from httpx import AsyncClient

PUSH = "/v1/context"
TICK = "/v1/tick"


def _ctx(scope, cid, payload, version=1):
    return {"scope": scope, "context_id": cid, "version": version,
            "payload": payload, "delivered_at": "2026-09-26T00:00:00Z"}


async def _setup(client, category, merchant, trigger):
    await client.post(PUSH, json=_ctx("category", category["slug"], category))
    await client.post(PUSH, json=_ctx("merchant", merchant["merchant_id"], merchant))
    await client.post(PUSH, json=_ctx("trigger", trigger["id"], trigger))


@pytest.mark.asyncio
async def test_expired_trigger_not_in_actions(client, category_dentists, merchant_drmeera):
    trg = {
        "id": "trg_expired_test", "scope": "merchant", "kind": "perf_dip",
        "merchant_id": merchant_drmeera["merchant_id"], "customer_id": None,
        "payload": {"metric": "calls", "delta_pct": -0.4, "window": "7d"},
        "urgency": 3, "suppression_key": "test:expired",
        "expires_at": "2020-01-01T00:00:00Z",
    }
    await _setup(client, category_dentists, merchant_drmeera, trg)
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z", "available_triggers": [trg["id"]]})
    assert resp.status_code == 200
    assert resp.json()["actions"] == []


@pytest.mark.asyncio
async def test_suppression_key_deduplication(client, category_dentists, merchant_drmeera):
    trg = {
        "id": "trg_sup_test", "scope": "merchant", "kind": "perf_dip",
        "merchant_id": merchant_drmeera["merchant_id"], "customer_id": None,
        "payload": {"metric": "calls", "delta_pct": -0.5, "window": "7d"},
        "urgency": 3, "suppression_key": "dedup:test:unique_key",
        "expires_at": "2030-01-01T00:00:00Z",
    }
    await _setup(client, category_dentists, merchant_drmeera, trg)
    r1 = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z", "available_triggers": [trg["id"]]})
    r2 = await client.post(TICK, json={"now": "2026-09-26T10:05:00Z", "available_triggers": [trg["id"]]})
    assert len(r1.json()["actions"]) == 1
    assert len(r2.json()["actions"]) == 0


@pytest.mark.asyncio
async def test_empty_triggers_returns_empty(client):
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z", "available_triggers": []})
    assert resp.status_code == 200
    assert resp.json()["actions"] == []


@pytest.mark.asyncio
async def test_unknown_trigger_id_skipped(client):
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z", "available_triggers": ["no_such_trigger"]})
    assert resp.status_code == 200
    assert resp.json()["actions"] == []
