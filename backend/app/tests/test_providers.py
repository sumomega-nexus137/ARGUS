"""Open-Meteo live context: honest modes (LIVE / CACHED / STALE / OFFLINE / NOT_CONFIGURED) with a mocked network."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.providers import open_meteo as om

GLOFAS = {"latitude": 51.825, "longitude": 68.375,
          "daily": {"time": ["2026-10-01", "2026-10-02"], "river_discharge": [1.2, 1.4], "river_discharge_p75": [1.5, 1.9]}}


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(om, "cache_dir", lambda: tmp_path)
    return tmp_path


def test_live_then_cached_then_stale_then_offline(isolated_cache, monkeypatch):
    calls = {"n": 0}

    def ok(url, timeout):
        calls["n"] += 1
        assert "flood-api.open-meteo.com" in url and "latitude=51.8" in url
        return GLOFAS

    monkeypatch.setattr(om, "_http_get_json", ok)
    r = om.live_context("t1", 51.8, 68.35, "glofas", refresh=True)
    assert r["mode"] == "LIVE" and r["data"]["rows"][1]["river_discharge"] == 1.4
    assert r["authority"] == "GLOBAL_MODEL" and r["returned_coordinate"]["lat"] == 51.825
    # within TTL → served from cache, still LIVE, no network
    r2 = om.live_context("t1", 51.8, 68.35, "glofas")
    assert r2["mode"] == "LIVE" and calls["n"] == 1

    def fail(url, timeout):
        raise OSError("network down")

    monkeypatch.setattr(om, "_http_get_json", fail)
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    r3 = om.live_context("t1", 51.8, 68.35, "glofas", refresh=True)
    assert r3["mode"] == "CACHED" and r3["data"] is not None and "network down" in r3["message"]
    # age the cache beyond the stale threshold → STALE (never LIVE)
    p = isolated_cache / "t1_glofas.json"
    entry = json.loads(p.read_text())
    entry["fetched_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    p.write_text(json.dumps(entry))
    r4 = om.live_context("t1", 51.8, 68.35, "glofas", refresh=True)
    assert r4["mode"] == "STALE"
    # no cache at all → OFFLINE
    r5 = om.live_context("other", 51.8, 68.35, "glofas", refresh=True)
    assert r5["mode"] == "OFFLINE" and r5["data"] is None


def test_offline_flag_and_disabled(isolated_cache, monkeypatch):
    monkeypatch.setattr(om, "_http_get_json", lambda url, timeout: (_ for _ in ()).throw(AssertionError("no network")))
    r = om.live_context("t2", 53.28, 69.40, "weather", offline=True)
    assert r["mode"] == "OFFLINE"
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "open_meteo_enabled", False)
    assert om.live_context("t2", 53.28, 69.40, "weather")["mode"] == "NOT_CONFIGURED"


def test_closed_official_providers_not_configured(monkeypatch):
    from app.providers.registry import REGISTRY, ProviderNotConfigured

    monkeypatch.delenv("ARGUS_TASQYN_URL", raising=False)
    monkeypatch.delenv("ARGUS_KAZHYDROMET_URL", raising=False)
    for key in ("tasqyn", "kazhydromet"):
        assert not REGISTRY[key].configured()
        with pytest.raises(ProviderNotConfigured):
            REGISTRY[key].fetch({"id": "x", "center": [0, 0], "stations": []})


def test_live_context_endpoint_degrades_without_network(client, auth, monkeypatch, tmp_path):
    monkeypatch.setattr(om, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(om, "_http_get_json", lambda url, timeout: (_ for _ in ()).throw(OSError("blocked")))
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    r = client.get("/api/areas/atbasar/context/live?refresh=true", headers=auth("viewer"))
    assert r.status_code == 200
    body = r.json()
    assert body["glofas"]["mode"] == "OFFLINE" and body["weather"]["mode"] == "OFFLINE"
    assert body["authority"] == "GLOBAL_MODEL"
