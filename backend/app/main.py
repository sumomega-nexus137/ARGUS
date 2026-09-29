"""ARGUS FloodOps — FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.routes import (
    analysis,
    areas,
    auth,
    data,
    misc,
    operations,
    plans,
    reports,
    scenarios,
    validation,
)
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger

log = get_logger("argus")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure_logging()
    from app.db.init import init_and_seed

    try:
        seeded = init_and_seed()
        log.info("database ready (seeded=%s)", seeded)
    except Exception:
        log.exception("database initialisation failed — API will report degraded health")
    worker = None
    if os.environ.get("ARGUS_ENABLE_PROVIDER_WORKER", "false").lower() == "true":
        from app.services.ingest.providers import ProviderScheduler

        worker = ProviderScheduler()
        worker.start()
    yield
    if worker:
        worker.stop()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="ARGUS FloodOps API",
        version="0.1.0",
        description="Regional Flood Decision & Response System. Human-in-the-loop decision support: ARGUS does not "
                    "replace emergency expertise — it gives that expertise computational power.",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True, allow_methods=["*"],
                       allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    install_error_handlers(app)
    for r in (auth, areas, scenarios, analysis, plans, operations, data, validation, reports, misc):
        app.include_router(r.router)
    return app


app = create_app()
