from __future__ import annotations

import time
from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger(__name__)

_db: aiosqlite.Connection | None = None
_start_time: float = time.time()

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db(db_path: str) -> None:
    global _db, _start_time
    _start_time = time.time()
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    schema = SCHEMA_PATH.read_text()
    await _db.executescript(schema)
    await _db.commit()
    log.info("db.init", path=db_path)


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def wipe_db() -> None:
    """Drop all rows — called on /v1/teardown."""
    db = get_db()
    for table in ("contexts", "suppression_keys", "conversations", "closed_conversations"):
        await db.execute(f"DELETE FROM {table}")
    await db.commit()
    log.info("db.wiped")


def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _db


def uptime_seconds() -> int:
    return int(time.time() - _start_time)
