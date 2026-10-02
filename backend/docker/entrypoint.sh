#!/bin/sh
# ARGUS FloodOps API entrypoint.
# 1. Real-data packs: install ONCE into the persistent pack volume (pinned release assets, SHA-256 verified).
#    When the packs are already installed this only checks the install marker — nothing is downloaded.
#    Without network access an existing installation is kept; a missing one falls back per ARGUS_DATA_PROFILE.
# 2. PostgreSQL/PostGIS: apply migrations (SQLite creates tables on startup). The database is seeded when empty.
set -e
if [ "${ARGUS_INSTALL_REALDATA:-true}" = "true" ]; then
  python -m app.cli install-realdata || echo "argus: real-data packs not installed (offline?) — profile '${ARGUS_DATA_PROFILE:-auto}' decides the fallback"
fi
case "$ARGUS_DATABASE_URL" in postgresql*) alembic upgrade head ;; esac
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
