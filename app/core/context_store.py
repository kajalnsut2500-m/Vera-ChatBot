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

    Uses a single atomic SQL upsert so concurrent calls for the same key never
    raise IntegrityError: the highest version always wins regardless of arrival
    order, and no intermediate state is observable.
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Single atomic statement: insert if new; update only when incoming version
    # is strictly higher than what is already stored.  If the WHERE clause is
    # false (same or lower version), the ON CONFLICT branch is a no-op.
    await db.execute(
        """
        INSERT INTO contexts (scope, context_id, version, payload, stored_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(scope, context_id) DO UPDATE SET
            version   = excluded.version,
            payload   = excluded.payload,
            stored_at = excluded.stored_at
        WHERE excluded.version > contexts.version
        """,
        (scope, context_id, version, json.dumps(payload), now),
    )
    await db.commit()

    # Read back to classify: did our version land, or did a concurrent higher
    # version already overwrite us?
    async with db.execute(
        "SELECT version FROM contexts WHERE scope = ? AND context_id = ?",
        (scope, context_id),
    ) as cur:
        row = await cur.fetchone()

    current = row["version"]  # always exists — we just wrote or it was already there
    if version >= current:
        return True, version   # inserted, updated, or idempotent same-version
    return False, current      # a concurrent higher-version write beat us → 409


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
