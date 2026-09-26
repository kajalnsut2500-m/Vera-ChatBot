from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.database import close_db, init_db, wipe_db
from app.logging_config import configure_logging

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db(settings.db_path)
    log.info("vera.started", version=settings.version, model=settings.model)
    yield
    await close_db()
    log.info("vera.stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Vera — magicpin Merchant AI", version="1.0.0", lifespan=lifespan)

    # Routers registered here; later phases add context/tick/reply
    from app.api.v1.health import router as health_router
    from app.api.v1.metadata import router as meta_router

    app.include_router(health_router, prefix="/v1")
    app.include_router(meta_router, prefix="/v1")

    @app.post("/v1/teardown")
    async def teardown():
        await wipe_db()
        return {"wiped": True}

    return app


app = create_app()
