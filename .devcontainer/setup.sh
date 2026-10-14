#!/usr/bin/env bash
# One-time setup of the full ARGUS stack inside a GitHub Codespace (or any dev container).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== backend =="
python -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip -q
backend/.venv/bin/pip install -r backend/requirements.txt -q
echo "== real-data packs (downloaded once, checksum-verified) =="
(cd backend && .venv/bin/python -m app.cli install-realdata)
echo "== console =="
(cd frontend && npm ci --no-audit --no-fund && npm run build)
echo "ARGUS is installed. It starts automatically; manual start: bash .devcontainer/start.sh"
