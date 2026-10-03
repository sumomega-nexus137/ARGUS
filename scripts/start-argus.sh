#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v docker >/dev/null || { echo "Docker is required."; exit 1; }
docker info >/dev/null || { echo "Docker daemon is not running."; exit 1; }
[ -f .env ] || cp .env.example .env

export ARGUS_DATA_PROFILE=historical
export ARGUS_INSTALL_REALDATA=true
export ARGUS_OPEN_METEO_ENABLED=true

docker compose up -d --build

echo "Waiting for ARGUS API..."
for _ in $(seq 1 200); do
  if curl -fsS http://localhost:8000/api/system/health | grep -q '"status":"ok"'; then break; fi
  sleep 3
done
curl -fsS http://localhost:8000/api/system/health >/dev/null || {
  docker compose logs --tail=120 backend
  exit 1
}

echo "Waiting for console..."
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:3000/login >/dev/null; then
    echo "ARGUS IS READY: http://localhost:3000"
    echo "planner / argus2026"
    exit 0
  fi
  sleep 2
done
docker compose logs --tail=120 frontend
exit 1
