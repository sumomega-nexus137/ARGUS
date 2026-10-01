from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="argus-test-"))
os.environ["ARGUS_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ARGUS_DEMO_MODE"] = "true"
os.environ.setdefault("ARGUS_DATA_PROFILE", "demo")
os.environ["ARGUS_OPTIMIZER_TIME_LIMIT_S"] = "2.0"


@pytest.fixture(scope="session")
def app():
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


def _token(client, username: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": "argus2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def auth(client):
    cache: dict[str, dict] = {}

    def get(username: str = "planner") -> dict:
        if username not in cache:
            cache[username] = _token(client, username)
        return cache[username]

    return get


@pytest.fixture()
def db(app):
    from app.db.session import session_factory

    s = session_factory()()
    try:
        yield s
    finally:
        s.rollback()
        s.close()
