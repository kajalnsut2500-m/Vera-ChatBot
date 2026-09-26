from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _push(client, scope, cid, payload, version):
    return await client.post("/v1/context", json={
        "scope": scope, "context_id": cid, "version": version,
        "payload": payload, "delivered_at": "2026-09-26T00:00:00Z",
    })


@pytest.mark.asyncio
async def test_version_1_then_same_idempotent(client):
    p = {"slug": "dentists", "test": 1}
    r1 = await _push(client, "category", "dentists", p, 1)
    r2 = await _push(client, "category", "dentists", p, 1)
    assert r1.status_code == 200 and r1.json()["accepted"] is True
    assert r2.status_code == 200 and r2.json()["accepted"] is True


@pytest.mark.asyncio
async def test_version_bump_accepted(client):
    p1 = {"slug": "dentists", "v": 1}
    p2 = {"slug": "dentists", "v": 2}
    await _push(client, "category", "dentists", p1, 1)
    r = await _push(client, "category", "dentists", p2, 2)
    assert r.status_code == 200
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_stale_version_409(client):
    await _push(client, "category", "dentists", {"v": 10}, 10)
    r = await _push(client, "category", "dentists", {"v": 5}, 5)
    assert r.status_code == 409
    body = r.json()
    assert body["reason"] == "stale_version"
    assert body["current_version"] == 10


@pytest.mark.asyncio
async def test_stale_version_reports_current(client):
    await _push(client, "merchant", "m_001", {"name": "A"}, 7)
    r = await _push(client, "merchant", "m_001", {"name": "B"}, 3)
    assert r.json()["current_version"] == 7


@pytest.mark.asyncio
async def test_multiple_scopes_independent(client):
    await _push(client, "category", "dentists", {}, 5)
    # Pushing merchant scope version 1 should never conflict with category version 5
    r = await _push(client, "merchant", "dentists", {}, 1)
    assert r.status_code == 200
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_ack_id_contains_context_id_and_version(client):
    r = await _push(client, "category", "salons", {"slug": "salons"}, 3)
    ack = r.json()["ack_id"]
    assert "salons" in ack
    assert "3" in ack
