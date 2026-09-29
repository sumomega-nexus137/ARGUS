"""Database initialisation.

* SQLite (demo/dev): tables are created directly from the ORM metadata.
* PostgreSQL/PostGIS (production): run ``alembic upgrade head`` (see README). ``init_db`` also
  ensures the PostGIS extension exists and creates missing tables when explicitly allowed.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import get_engine, session_scope

log = get_logger("argus.db")


def init_db(create_tables: bool = True) -> None:
    import app.models  # noqa: F401  (register tables)

    engine = get_engine()
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    if create_tables:
        Base.metadata.create_all(engine)


def init_and_seed() -> bool:
    init_db()
    if not get_settings().demo_mode:
        return False
    from app.demo.seed import seed_if_empty

    with session_scope() as db:
        return seed_if_empty(db)


def reset_demo() -> bool:
    """Drop every ARGUS table and re-seed the DEMO dataset (demo mode only). Returns True when re-seeded."""
    if not get_settings().demo_mode:
        return False
    import app.models  # noqa: F401
    from app.repositories.context import invalidate_static
    from app.services.routing import access

    engine = get_engine()
    Base.metadata.drop_all(engine)
    for area_id in ("atbasar", "kokshetau"):
        invalidate_static(area_id)
    access._series_cache.clear()
    log.info("demo database dropped; re-seeding")
    return init_and_seed()
