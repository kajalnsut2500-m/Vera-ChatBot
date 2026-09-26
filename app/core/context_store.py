from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db.database import get_db


async def store_context(
    scope: str, context_id: str, version: int, payload: dict[str, Any]
) -> tuple[bool, int]:
    """
    Attempt to store a context version.

    Returns (stored, current_version).
    - stored=True means the payload was written (new or higher version).
    - stored=False, current_version > version → caller should return 409.
    - stored=True, current_version == version (same) → already stored; idempotent.
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    async with db.execute(
        "SELECT version FROM contexts WHERE scope = ? AND context_id = ?",
        (scope, context_id),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        await db.execute(
            "INSERT INTO contexts (scope, context_id, version, payload, stored_at) VALUES (?, ?, ?, ?, ?)",
            (scope, context_id, version, json.dumps(payload), now),
        )
        await db.commit()
        return True, version

    current = row["version"]
    if version == current:
        return True, current   # idempotent no-op — already at this version
    if version < current:
        return False, current  # stale — caller returns 409

    # version > current — replace atomically
    await db.execute(
        "UPDATE contexts SET version = ?, payload = ?, stored_at = ? WHERE scope = ? AND context_id = ?",
        (version, json.dumps(payload), now, scope, context_id),
    )
    await db.commit()
    return True, version


async def get_context(scope: str, context_id: str) -> dict[str, Any] | None:
    db = get_db()
    async with db.execute(
        "SELECT payload FROM contexts WHERE scope = ? AND context_id = ?",
        (scope, context_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return json.loads(row["payload"])


async def count_by_scope() -> dict[str, int]:
    db = get_db()
    counts: dict[str, int] = {}
    async with db.execute(
        "SELECT scope, COUNT(*) AS n FROM contexts GROUP BY scope"
    ) as cur:
        async for row in cur:
            counts[row["scope"]] = row["n"]
    return counts


async def get_all_triggers() -> list[dict[str, Any]]:
    """Return all stored trigger payloads."""
    db = get_db()
    triggers = []
    async with db.execute(
        "SELECT payload FROM contexts WHERE scope = 'trigger'"
    ) as cur:
        async for row in cur:
            triggers.append(json.loads(row["payload"]))
    return triggers
