from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient


async def _push(client: AsyncClient, scope: str, cid: str, payload: dict, version: int = 1):
    return await client.post("/v1/context", json={
        "scope": scope, "context_id": cid, "version": version,
        "payload": payload, "delivered_at": "2026-09-26T00:00:00Z",
    })


@pytest.mark.asyncio
async def test_push_new_context_accepted(client, category_dentists):
    resp = await _push(client, "category", "dentists", category_dentists)
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is True
    assert "ack_id" in body
    assert "stored_at" in body


@pytest.mark.asyncio
async def test_push_same_version_idempotent(client, category_dentists):
    await _push(client, "category", "dentists", category_dentists, version=1)
    resp = await _push(client, "category", "dentists", category_dentists, version=1)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_push_lower_version_returns_409(client, category_dentists):
    await _push(client, "category", "dentists", category_dentists, version=5)
    resp = await _push(client, "category", "dentists", category_dentists, version=3)
    assert resp.status_code == 409
    body = resp.json()
    assert body["accepted"] is False
    assert body["reason"] == "stale_version"
    assert body["current_version"] == 5


@pytest.mark.asyncio
async def test_push_higher_version_replaces(client, category_dentists):
    await _push(client, "category", "dentists", category_dentists, version=1)
    updated = {**category_dentists, "_test_marker": "v2"}
    resp = await _push(client, "category", "dentists", updated, version=2)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_push_merchant_context(client, merchant_drmeera):
    resp = await _push(client, "merchant", merchant_drmeera["merchant_id"], merchant_drmeera)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_push_trigger_context(client, trigger_research):
    resp = await _push(client, "trigger", trigger_research["id"], trigger_research)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_push_customer_context(client, customer_priya):
    resp = await _push(client, "customer", customer_priya["customer_id"], customer_priya)
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_healthz_counts_after_push(client, category_dentists, merchant_drmeera):
    await _push(client, "category", "dentists", category_dentists)
    await _push(client, "merchant", merchant_drmeera["merchant_id"], merchant_drmeera)
    counts = (await client.get("/v1/healthz")).json()["contexts_loaded"]
    assert counts["category"] == 1
    assert counts["merchant"] == 1


@pytest.mark.asyncio
async def test_push_invalid_scope_rejected(client):
    resp = await client.post("/v1/context", json={
        "scope": "INVALID_SCOPE", "context_id": "x", "version": 1,
        "payload": {}, "delivered_at": "2026-09-26T00:00:00Z",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_same_key_no_integrity_error(client):
    """
    Regression for the SELECT-then-INSERT race: concurrent pushes for the same
    scope+context_id must never raise IntegrityError (HTTP 500).  The highest
    version must win; no write must be silently lost to a constraint violation.
    """
    cid = "concurrent_test_key"
    payloads = [
        {"scope": "merchant", "context_id": cid, "version": v,
         "payload": {"_v": v}, "delivered_at": "2026-09-26T00:00:00Z"}
        for v in (1, 2, 3, 4, 5)
    ]

    # Fire all five versions simultaneously.
    responses = await asyncio.gather(
        *[client.post("/v1/context", json=p) for p in payloads]
    )

    statuses = [r.status_code for r in responses]
    # No 500s — no IntegrityError escaped.
    assert all(s in (200, 409) for s in statuses), (
        f"Unexpected status codes (expected only 200/409): {statuses}"
    )

    # At least one request must have succeeded (the one carrying the highest version).
    assert any(s == 200 for s in statuses)

    # The stored version must be the highest we sent (version=5).
    check = await client.post("/v1/context", json={
        "scope": "merchant", "context_id": cid, "version": 4,
        "payload": {"_v": 4}, "delivered_at": "2026-09-26T00:00:00Z",
    })
    assert check.status_code == 409, "version 4 must be stale after version 5 landed"
    assert check.json()["current_version"] == 5
