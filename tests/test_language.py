from __future__ import annotations

import pytest
from httpx import AsyncClient

PUSH = "/v1/context"
TICK = "/v1/tick"


def _ctx(scope, cid, payload, v=1):
    return {"scope": scope, "context_id": cid, "version": v,
            "payload": payload, "delivered_at": "2026-09-26T00:00:00Z"}


def _perf_dip_trigger(merchant_id, key):
    return {
        "id": f"trg_lang_{key}", "scope": "merchant", "kind": "perf_dip",
        "merchant_id": merchant_id, "customer_id": None,
        "payload": {"metric": "calls", "delta_pct": -0.4, "window": "7d"},
        "urgency": 3, "suppression_key": f"lang:{key}:test",
        "expires_at": "2030-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_hindi_merchant_body_contains_hindi_markers(client, category_dentists, merchant_drmeera):
    # m_001 has languages: ["en", "hi"] — should use Hindi mix
    trg = _perf_dip_trigger(merchant_drmeera["merchant_id"], "hi1")
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", merchant_drmeera["merchant_id"], merchant_drmeera))
    await client.post(PUSH, json=_ctx("trigger", trg["id"], trg))
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z", "available_triggers": [trg["id"]]})
    body = resp.json()["actions"][0]["body"]
    # Hindi-mix: expect "girar" or "hafte" or "mein"
    assert any(w in body for w in ("girar", "hafte", "mein", "chahenge"))


@pytest.mark.asyncio
async def test_english_merchant_body_is_english(client, category_dentists, merchant_drmeera):
    eng_merchant = {
        **merchant_drmeera,
        "merchant_id": "m_eng_test",
        "identity": {**merchant_drmeera["identity"], "languages": ["en"]},
    }
    trg = _perf_dip_trigger("m_eng_test", "en1")
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", "m_eng_test", eng_merchant))
    await client.post(PUSH, json=_ctx("trigger", trg["id"], trg))
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z", "available_triggers": [trg["id"]]})
    body = resp.json()["actions"][0]["body"]
    assert "dropped" in body
    assert "girar" not in body
