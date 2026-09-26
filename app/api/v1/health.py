from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.database import get_db, uptime_seconds

router = APIRouter()


class ContextCounts(BaseModel):
    category: int = 0
    merchant: int = 0
    customer: int = 0
    trigger: int = 0


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: int
    contexts_loaded: ContextCounts


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    db = get_db()
    counts: dict[str, int] = {}
    async with db.execute(
        "SELECT scope, COUNT(*) as n FROM contexts GROUP BY scope"
    ) as cur:
        async for row in cur:
            counts[row["scope"]] = row["n"]

    return HealthResponse(
        status="ok",
        uptime_seconds=uptime_seconds(),
        contexts_loaded=ContextCounts(
            category=counts.get("category", 0),
            merchant=counts.get("merchant", 0),
            customer=counts.get("customer", 0),
            trigger=counts.get("trigger", 0),
        ),
    )
