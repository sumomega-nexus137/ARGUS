"""Real-data (HISTORICAL profile) tests. Run separately: ``pytest app/tests_realdata``.

They use the installed real-data packs (``python -m app.cli install-realdata``) and are skipped when the packs are
not installed. A guard makes every outbound network call fail, proving the historical demo runs offline."""

from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="argus-realdata-test-"))
os.environ["ARGUS_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ARGUS_DEMO_MODE"] = "true"
os.environ["ARGUS_DATA_PROFILE"] = "historical"
os.environ["ARGUS_OPTIMIZER_TIME_LIMIT_S"] = "2.0"


def _packs_installed() -> bool:
    from app.realdata.install import installed_areas

    return set(installed_areas()) == {"atbasar", "kokshetau"}


@pytest.fixture(scope="session", autouse=True)
def no_network():
    """Historical operation must not depend on the internet (DEM/OSM/satellite/WorldPop are pre-installed)."""
    real = socket.socket.connect

    def guarded(self, addr):  # type: ignore[no-untyped-def]
        host = addr[0] if isinstance(addr, tuple) else addr
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError(f"network access blocked in real-data tests: {addr}")
        return real(self, addr)

    socket.socket.connect = guarded
    yield
    socket.socket.connect = real


@pytest.fixture(scope="session")
def app():
    if not _packs_installed():
        pytest.skip("real-data packs not installed (python -m app.cli install-realdata)")
    from app.core.config import get_settings
    from app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()
    from app.db.init import init_and_seed
    from app.main import create_app

    init_and_seed()
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    cache: dict[str, dict] = {}

    def get(username: str = "planner") -> dict:
        if username not in cache:
            r = client.post("/api/auth/login", json={"username": username, "password": "argus2026"})
            assert r.status_code == 200, r.text
            cache[username] = {"Authorization": f"Bearer {r.json()['token']}"}
        return cache[username]

    return get
