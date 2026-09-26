from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Set env vars before any app module is imported so pydantic-settings picks them up.
os.environ.setdefault("VERA_DB_PATH", ":memory:")
os.environ.setdefault("VERA_ANTHROPIC_API_KEY", "sk-ant-test-key")

DATASET = Path(__file__).parent.parent / "dataset"


@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Yields an AsyncClient wired to a fresh in-memory SQLite database.

    ASGITransport does not trigger FastAPI's lifespan events, so we call
    init_db / close_db explicitly around the client instead of relying on
    the app's startup/shutdown hooks.  No production code is modified.
    """
    from app.db.database import close_db, init_db
    from app.main import create_app

    await init_db(":memory:")
    test_app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac

    await close_db()


# ── Dataset fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def category_dentists() -> dict:
    return json.loads((DATASET / "categories" / "dentists.json").read_text())


@pytest.fixture(scope="session")
def category_salons() -> dict:
    return json.loads((DATASET / "categories" / "salons.json").read_text())


@pytest.fixture(scope="session")
def merchants_seed() -> list[dict]:
    data = json.loads((DATASET / "merchants_seed.json").read_text())
    return data["merchants"]


@pytest.fixture(scope="session")
def merchant_drmeera(merchants_seed) -> dict:
    return next(m for m in merchants_seed if m["merchant_id"] == "m_001_drmeera_dentist_delhi")


@pytest.fixture(scope="session")
def merchant_bharat(merchants_seed) -> dict:
    return next(m for m in merchants_seed if m["merchant_id"] == "m_002_bharat_dentist_mumbai")


@pytest.fixture(scope="session")
def customers_seed() -> list[dict]:
    data = json.loads((DATASET / "customers_seed.json").read_text())
    return data["customers"]


@pytest.fixture(scope="session")
def customer_priya(customers_seed) -> dict:
    return next(c for c in customers_seed if c["customer_id"] == "c_001_priya_for_m001")


@pytest.fixture(scope="session")
def triggers_seed() -> list[dict]:
    data = json.loads((DATASET / "triggers_seed.json").read_text())
    return data["triggers"]


@pytest.fixture(scope="session")
def trigger_research(triggers_seed) -> dict:
    return next(t for t in triggers_seed if t["id"] == "trg_001_research_digest_dentists")


@pytest.fixture(scope="session")
def trigger_recall_priya(triggers_seed) -> dict:
    return next(t for t in triggers_seed if t["id"] == "trg_003_recall_due_priya")


@pytest.fixture(scope="session")
def trigger_perf_dip(triggers_seed) -> dict:
    return next(t for t in triggers_seed if t["id"] == "trg_004_perf_dip_bharat")
