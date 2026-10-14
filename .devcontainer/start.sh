#!/usr/bin/env bash
# Starts the ARGUS API (port 8000) and console (port 3000) in the background; logs in /tmp/argus-*.log.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x backend/.venv/bin/uvicorn ] || [ ! -d frontend/.next ]; then
  echo "ARGUS is not installed yet — run: bash .devcontainer/setup.sh"
  exit 0
fi
if ! curl -fsS http://127.0.0.1:8000/api/system/health >/dev/null 2>&1; then
  (cd backend && setsid nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75 \
    > /tmp/argus-backend.log 2>&1 &)
fi
if ! curl -fsS http://127.0.0.1:3000/login >/dev/null 2>&1; then
  (cd frontend && setsid nohup npx next start -p 3000 > /tmp/argus-frontend.log 2>&1 &)
fi
for i in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8000/api/system/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:3000/login >/dev/null 2>&1; then
    echo "ARGUS is running → open the PORTS tab, port 3000 (login planner / argus2026)"
    exit 0
  fi
  sleep 2
done
echo "ARGUS is still starting — see /tmp/argus-backend.log and /tmp/argus-frontend.log"
