"""
Optional Gemini copy-polish layer.

Called AFTER the deterministic composer. If VERA_GEMINI_API_KEY is absent,
the layer is a no-op. Any error, timeout, or invalid JSON falls back to the
deterministic draft unchanged — no exceptions propagate to callers.

Facts sent to Gemini: only the already-selected grounded fact strings from the
deterministic draft (template_params). Raw merchant/customer context is never
forwarded.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

_LOG = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key={key}"
)
_TIMEOUT = 4        # seconds — asyncio outer ceiling
_SOCKET_TIMEOUT = 3  # socket closes before asyncio cancels, preventing zombie threads


def _api_key() -> str:
    return os.environ.get("VERA_GEMINI_API_KEY", "")


def _build_payload(
    draft_body: str,
    cta_str: str,
    facts: dict[str, str],
    voice_rules: list[str],
) -> dict[str, Any]:
    facts_block = "\n".join(f"  {k}: {v}" for k, v in facts.items())
    voice_block = "\n".join(f"  - {r}" for r in voice_rules) if voice_rules else "  - professional, warm, concise"

    prompt = (
        "You are a WhatsApp message editor for a merchant assistant called Vera.\n\n"
        "TASK: Improve the engagement wording of the DRAFT below.\n\n"
        "RULES (strict):\n"
        "- Do NOT change any numbers, dates, percentages, offer amounts, citations, or competitor names.\n"
        "- Do NOT add claims, promises, or facts not in the supplied FACTS.\n"
        "- Keep the same CTA type exactly.\n"
        "- Keep the message under 300 characters.\n"
        "- Match the voice rules.\n\n"
        f"FACTS (only these may appear in the message):\n{facts_block}\n\n"
        f"VOICE RULES:\n{voice_block}\n\n"
        f"CTA TYPE (must stay unchanged): {cta_str}\n\n"
        f"DRAFT:\n{draft_body}\n\n"
        "RESPOND with valid JSON only — no markdown fences:\n"
        '{"body": "<rewritten message>", "cta": "<cta_type unchanged>", '
        '"used_fact_ids": ["<fact id>", ...]}'
    )

    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 200},
    }


def _validate(result: dict, expected_cta: str, allowed_fact_ids: set[str]) -> str | None:
    """Return polished body if valid, else None."""
    body = result.get("body", "")
    if not isinstance(body, str) or not body.strip():
        return None
    if result.get("cta") != expected_cta:
        return None
    used = result.get("used_fact_ids", [])
    if not isinstance(used, list):
        return None
    if not set(used).issubset(allowed_fact_ids):
        return None
    return body.strip()


def _call_gemini_sync(key: str, payload: dict) -> dict:
    """Blocking HTTP call — run via asyncio.wait_for in a thread."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _GEMINI_URL.format(key=key),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_SOCKET_TIMEOUT) as resp:
        return json.loads(resp.read())


async def polish(
    draft_body: str,
    cta_str: str,
    template_params: list[str],
    voice_rules: list[str],
) -> str:
    """
    Return a polished body, or the original draft_body on any failure.

    template_params become the facts sent to Gemini (keyed f0, f1, ...).
    """
    key = _api_key()
    if not key:
        return draft_body

    facts = {f"f{i}": v for i, v in enumerate(template_params) if v}
    allowed_ids = set(facts.keys())
    payload = _build_payload(draft_body, cta_str, facts, voice_rules)

    try:
        loop = asyncio.get_running_loop()
        raw = await asyncio.wait_for(
            loop.run_in_executor(None, _call_gemini_sync, key, payload),
            timeout=_TIMEOUT,
        )
        # Extract text from Gemini response envelope
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip markdown fences if model wraps them anyway
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        polished = _validate(result, cta_str, allowed_ids)
        if polished:
            return polished
        _LOG.debug("gemini_polish: validation failed, using deterministic draft")
    except Exception as exc:  # timeout, network error, parse error — all fallback
        _LOG.debug("gemini_polish: fallback (%s: %s)", type(exc).__name__, exc)

    return draft_body
