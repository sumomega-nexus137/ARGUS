#!/bin/sh
# ARGUS FloodOps API entrypoint.
# Keep this file ASCII-only and LF-only: it is executed by /bin/sh inside Linux containers.
set -e

if [ "${ARGUS_INSTALL_REALDATA:-true}" = "true" ]; then
  python -m app.cli install-realdata || echo "argus: real-data packs not installed; profile '${ARGUS_DATA_PROFILE:-auto}' decides the fallback"
fi

case "${ARGUS_DATABASE_URL:-}" in
  postgresql*) alembic upgrade head ;;
esac

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
