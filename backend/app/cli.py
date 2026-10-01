"""ARGUS command-line utilities.

    python -m app.cli generate-demo      # (re)generate DEMO fixtures into data/demo
    python -m app.cli init-db            # create tables (SQLite) / ensure PostGIS
    python -m app.cli seed               # seed DEMO data if the database is empty
    python -m app.cli reset-demo         # drop the SQLite demo DB and re-seed
    python -m app.cli export-scenario <area> <out_dir>   # export precomputed rasters + manifest (raster contract example)
    python -m app.cli install-realdata [--area A] [--archive F.tar.gz] [--offline] [--force]
                                         # download ONCE → verify SHA-256 → install real-data packs
    python -m app.cli realdata-status [--verify]         # show installed packs (re-hash every file with --verify)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging


def main(argv: list[str]) -> int:
    configure_logging()
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    s = get_settings()
    if cmd == "generate-demo":
        from app.demo.generator import generate_all

        print(json.dumps(generate_all(s.demo_dir), indent=2))
        return 0
    if cmd == "init-db":
        from app.db.init import init_db

        init_db()
        return 0
    if cmd == "seed":
        from app.db.init import init_and_seed

        print("seeded" if init_and_seed() else "database already contains data")
        return 0
    if cmd == "reset-demo":
        if not s.is_sqlite:
            print("reset-demo only supports the SQLite demo database; drop the PostgreSQL schema manually")
            return 2
        db_path = Path(s.database_url.replace("sqlite:///", ""))
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        from app.db.init import init_and_seed

        init_and_seed()
        print("demo database reset")
        return 0
    if cmd in ("install-realdata", "realdata-status"):
        from app.realdata import install as rd

        opts = argv[1:]
        areas = [opts[opts.index("--area") + 1]] if "--area" in opts else list(rd.AREAS)
        rc = 0
        for area in areas:
            try:
                if cmd == "install-realdata":
                    archive = Path(opts[opts.index("--archive") + 1]) if "--archive" in opts else None
                    st = rd.install(area, archive=archive, force="--force" in opts, offline="--offline" in opts)
                else:
                    st = rd.verify_installed(area) if "--verify" in opts else rd.status(area)
                print(json.dumps(st.as_dict()))
                rc = rc or (0 if st.installed else 3)
            except rd.PackError as exc:
                print(json.dumps({"area": area, "installed": False, "error": str(exc)}))
                rc = 2
        return rc
    if cmd == "export-scenario":
        from app.db.session import session_scope
        from app.services.scenario.export import export_raster_manifest

        area, out = argv[1], Path(argv[2])
        with session_scope() as db:
            print(export_raster_manifest(db, area, out))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
