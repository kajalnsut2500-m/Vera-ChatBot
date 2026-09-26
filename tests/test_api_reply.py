from __future__ import annotations

import pytest
from httpx import AsyncClient

REPLY = "/v1/reply"
_TS = "2026-09-26T10:00:00Z"
_MID = "m_001_drmeera_dentist_delhi"


def _reply(conv_id, message, turn=2, merchant_id=_MID):
    return {"conversation_id": conv_id, "merchant_id": merchant_id,
            "from_role": "merchant", "message": message,
            "received_at": _TS, "turn_number": turn}


@pytest.mark.asyncio
async def test_reply_accept_returns_send(client):
    resp = await client.post(REPLY, json=_reply("conv_accept_1", "Yes, go ahead"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "send"
    assert body["body"]


@pytest.mark.asyncio
async def test_reply_stop_returns_end(client):
    resp = await client.post(REPLY, json=_reply("conv_stop_1", "Not interested. STOP."))
    assert resp.json()["action"] == "end"


@pytest.mark.asyncio
async def test_reply_delay_returns_wait(client):
    resp = await client.post(REPLY, json=_reply("conv_delay_1", "Busy right now, call back later"))
    body = resp.json()
    assert body["action"] == "wait"
    assert body["wait_seconds"] and body["wait_seconds"] > 0


@pytest.mark.asyncio
async def test_reply_auto_reply_first_time_waits(client):
    msg = "Thank you for contacting us! Our team will respond shortly."
    resp = await client.post(REPLY, json=_reply("conv_ar_fresh", msg))
    assert resp.json()["action"] in ("wait", "end")


@pytest.mark.asyncio
async def test_reply_auto_reply_twice_ends(client):
    msg = "Thank you for contacting us! Our team will respond shortly."
    await client.post(REPLY, json=_reply("conv_ar_twice", msg, turn=2))
    resp = await client.post(REPLY, json=_reply("conv_ar_twice", msg, turn=3))
    assert resp.json()["action"] == "end"


@pytest.mark.asyncio
async def test_reply_abuse_returns_end(client):
    resp = await client.post(REPLY, json=_reply("conv_abuse_1", "This is spam, stop bothering me"))
    assert resp.json()["action"] == "end"


@pytest.mark.asyncio
async def test_reply_normal_message_returns_send(client):
    resp = await client.post(REPLY, json=_reply("conv_normal_1", "Can you tell me more?"))
    body = resp.json()
    assert body["action"] == "send"
    assert body["body"]


@pytest.mark.asyncio
async def test_reply_response_has_rationale(client):
    resp = await client.post(REPLY, json=_reply("conv_rat_1", "Yes please"))
    assert resp.json()["rationale"]
