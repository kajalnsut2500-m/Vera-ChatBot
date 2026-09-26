from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_ok(client: AsyncClient):
    resp = await client.get("/v1/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
    assert body["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_healthz_context_counts_shape(client: AsyncClient):
    resp = await client.get("/v1/healthz")
    counts = resp.json()["contexts_loaded"]
    for key in ("category", "merchant", "customer", "trigger"):
        assert key in counts
        assert isinstance(counts[key], int)


@pytest.mark.asyncio
async def test_healthz_zero_before_push(client: AsyncClient):
    resp = await client.get("/v1/healthz")
    counts = resp.json()["contexts_loaded"]
    # Fresh in-memory DB should have zero counts
    assert all(v == 0 for v in counts.values())


@pytest.mark.asyncio
async def test_metadata_shape(client: AsyncClient):
    resp = await client.get("/v1/metadata")
    assert resp.status_code == 200
    body = resp.json()
    required = {"team_name", "team_members", "model", "approach", "contact_email", "version", "submitted_at"}
    assert required.issubset(body.keys())


@pytest.mark.asyncio
async def test_metadata_team_members_list(client: AsyncClient):
    resp = await client.get("/v1/metadata")
    assert isinstance(resp.json()["team_members"], list)


@pytest.mark.asyncio
async def test_teardown_endpoint(client: AsyncClient):
    resp = await client.post("/v1/teardown")
    assert resp.status_code == 200
    assert resp.json()["wiped"] is True
