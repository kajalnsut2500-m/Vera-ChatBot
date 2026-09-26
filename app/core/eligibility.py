from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.database import get_db


async def is_eligible(trigger: dict, now: datetime) -> bool:
    expires_raw = trigger.get("expires_at", "")
    if expires_raw:
        try:
            exp = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
            if now > exp:
                return False
        except ValueError:
            pass

    key = trigger.get("suppression_key", "")
    if key:
        db = get_db()
        async with db.execute(
            "SELECT 1 FROM suppression_keys WHERE suppression_key = ?", (key,)
        ) as cur:
            if await cur.fetchone():
                return False
    return True


async def record_suppression(key: str, conversation_id: str) -> None:
    if not key:
        return
    db = get_db()
    fired_at = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR IGNORE INTO suppression_keys (suppression_key, conversation_id, fired_at) VALUES (?,?,?)",
        (key, conversation_id, fired_at),
    )
    await db.commit()


def rank(triggers: list[dict]) -> list[dict]:
    return sorted(triggers, key=lambda t: t.get("urgency", 1), reverse=True)
