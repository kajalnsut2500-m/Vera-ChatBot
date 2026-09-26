from __future__ import annotations

import pytest
from httpx import AsyncClient

PUSH = "/v1/context"
TICK = "/v1/tick"

_NOW = "2026-09-26T10:00:00Z"


def _ctx(scope, cid, payload, v=1):
    return {"scope": scope, "context_id": cid, "version": v,
            "payload": payload, "delivered_at": _NOW}


@pytest.mark.asyncio
async def test_dentist_taboos_not_in_output(client, category_dentists, merchant_drmeera):
    taboos = category_dentists.get("voice", {}).get("vocab_taboo", [])
    assert taboos, "Expected taboos in dentists category fixture"

    trg = {
        "id": "trg_taboo_test", "scope": "merchant", "kind": "research_digest",
        "merchant_id": merchant_drmeera["merchant_id"], "customer_id": None,
        "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
        "urgency": 2, "suppression_key": "taboo:test:unique",
        "expires_at": "2030-01-01T00:00:00Z",
    }
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", merchant_drmeera["merchant_id"], merchant_drmeera))
    await client.post(PUSH, json=_ctx("trigger", trg["id"], trg))

    resp = await client.post(TICK, json={"now": _NOW, "available_triggers": [trg["id"]]})
    actions = resp.json()["actions"]
    assert actions, "Expected at least one action"
    body_lower = actions[0]["body"].lower()
    for taboo in taboos:
        assert taboo.lower() not in body_lower, f"Taboo word '{taboo}' found in body"
