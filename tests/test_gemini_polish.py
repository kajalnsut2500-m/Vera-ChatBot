"""Focused tests for the optional Gemini copy-polish layer."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import patch, MagicMock

import pytest

from app.core.gemini_polish import polish

_DRAFT = "Dr. Meera, new finding: fluoride study. Reply YES / STOP."
_CTA = "binary_yes_stop"
_PARAMS = ["Dr. Meera", "fluoride study", "Reply YES / STOP"]
_VOICE = ["professional", "concise"]


def _gemini_response(body: str, cta: str, used: list[str]) -> dict:
    """Build a minimal Gemini REST response envelope."""
    text = json.dumps({"body": body, "cta": cta, "used_fact_ids": used})
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@pytest.mark.asyncio
async def test_valid_gemini_rewrite_replaces_draft(monkeypatch):
    """A valid Gemini response with correct CTA + subset facts is accepted."""
    polished = "Dr. Meera, exciting fluoride study just dropped — Reply YES to read it, STOP to skip."
    response = _gemini_response(polished, _CTA, ["f0", "f1"])

    monkeypatch.setenv("VERA_GEMINI_API_KEY", "test-key-abc")

    with patch("app.core.gemini_polish._call_gemini_sync", return_value=response):
        result = await polish(_DRAFT, _CTA, _PARAMS, _VOICE)

    assert result == polished
    assert result != _DRAFT


@pytest.mark.asyncio
async def test_missing_key_returns_draft(monkeypatch):
    """No API call is made and the original draft is returned when key is absent."""
    monkeypatch.delenv("VERA_GEMINI_API_KEY", raising=False)

    with patch("app.core.gemini_polish._call_gemini_sync") as mock_call:
        result = await polish(_DRAFT, _CTA, _PARAMS, _VOICE)

    mock_call.assert_not_called()
    assert result == _DRAFT


@pytest.mark.asyncio
async def test_timeout_and_error_return_draft(monkeypatch):
    """Network error or asyncio.TimeoutError causes fallback to deterministic draft."""
    monkeypatch.setenv("VERA_GEMINI_API_KEY", "test-key-xyz")

    with patch("app.core.gemini_polish._call_gemini_sync", side_effect=TimeoutError("network timeout")):
        result = await polish(_DRAFT, _CTA, _PARAMS, _VOICE)

    assert result == _DRAFT


@pytest.mark.asyncio
async def test_invalid_cta_in_response_returns_draft(monkeypatch):
    """Gemini returning a different CTA is rejected; draft is used."""
    polished = "Some rewritten text."
    response = _gemini_response(polished, "open_ended", ["f0"])  # wrong CTA

    monkeypatch.setenv("VERA_GEMINI_API_KEY", "test-key-abc")

    with patch("app.core.gemini_polish._call_gemini_sync", return_value=response):
        result = await polish(_DRAFT, _CTA, _PARAMS, _VOICE)

    assert result == _DRAFT


@pytest.mark.asyncio
async def test_out_of_scope_fact_ids_rejected(monkeypatch):
    """Gemini claiming a fact_id outside the supplied set is rejected."""
    polished = "Some rewritten text."
    response = _gemini_response(polished, _CTA, ["f0", "f99"])  # f99 not in facts

    monkeypatch.setenv("VERA_GEMINI_API_KEY", "test-key-abc")

    with patch("app.core.gemini_polish._call_gemini_sync", return_value=response):
        result = await polish(_DRAFT, _CTA, _PARAMS, _VOICE)

    assert result == _DRAFT
