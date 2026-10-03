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


def _warmup() -> None:
    """Pre-compute static caches so the first operator request does not pay for them. Failures are logged only."""
    from sqlalchemy import select

    from app.api.routes.areas import LAYERS, layer_bytes
    from app.db.session import session_scope
    from app.models import OperationalArea
    from app.repositories.context import load_context
    from app.services.routing.bottlenecks import structural_candidates

    try:
        with session_scope() as db:
            for area in db.scalars(select(OperationalArea)).all():
                for layer in LAYERS:
                    layer_bytes(db, area, layer)
                structural_candidates(load_context(db, area.id))
        log.info("static caches warmed")
    except Exception:
        log.exception("cache warm-up failed (requests will compute on demand)")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure_logging()
    from app.db.init import init_and_seed

    try:
        seeded = init_and_seed()
        log.info("database ready (seeded=%s)", seeded)
    except Exception:
        log.exception("database initialisation failed — API will report degraded health")
    if get_settings().warmup:
        import threading

        threading.Thread(target=_warmup, name="argus-warmup", daemon=True).start()
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
