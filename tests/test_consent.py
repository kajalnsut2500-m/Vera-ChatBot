from __future__ import annotations

import pytest
from httpx import AsyncClient

PUSH = "/v1/context"
TICK = "/v1/tick"


def _ctx(scope, cid, payload, version=1):
    return {"scope": scope, "context_id": cid, "version": version,
            "payload": payload, "delivered_at": "2026-09-26T00:00:00Z"}


@pytest.mark.asyncio
async def test_customer_trigger_requires_consent(
    client, category_dentists, merchant_drmeera, customer_priya, trigger_recall_priya
):
    # Customer without recall_reminders consent → no action
    customer_no_consent = {**customer_priya, "consent": {"opted_in_at": "2025-11-04", "scope": []}}
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", merchant_drmeera["merchant_id"], merchant_drmeera))
    await client.post(PUSH, json=_ctx("customer", customer_priya["customer_id"], customer_no_consent))
    await client.post(PUSH, json=_ctx("trigger", trigger_recall_priya["id"], trigger_recall_priya))
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z",
                                          "available_triggers": [trigger_recall_priya["id"]]})
    assert resp.json()["actions"] == []


@pytest.mark.asyncio
async def test_customer_trigger_with_consent_produces_action(
    client, category_dentists, merchant_drmeera, customer_priya, trigger_recall_priya
):
    await client.post(PUSH, json=_ctx("category", "dentists", category_dentists))
    await client.post(PUSH, json=_ctx("merchant", merchant_drmeera["merchant_id"], merchant_drmeera))
    await client.post(PUSH, json=_ctx("customer", customer_priya["customer_id"], customer_priya))
    await client.post(PUSH, json=_ctx("trigger", trigger_recall_priya["id"], trigger_recall_priya))
    resp = await client.post(TICK, json={"now": "2026-09-26T10:00:00Z",
                                          "available_triggers": [trigger_recall_priya["id"]]})
    actions = resp.json()["actions"]
    assert len(actions) == 1
    assert actions[0]["send_as"] == "merchant_on_behalf"
