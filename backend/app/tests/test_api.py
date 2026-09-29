"""API, RBAC, rendering, imports, data authority and failure handling."""

from __future__ import annotations

import io


def test_health_and_auth(client):
    assert client.get("/api/system/health").json()["database"] == "ok"
    assert client.get("/api/areas").status_code == 401
    r = client.post("/api/auth/login", json={"username": "planner", "password": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert client.get("/api/auth/demo-users").json()["demo"] is True


def test_rbac(client, auth):
    body = {"road_id": "R1", "state": "CLOSED", "verification": "VERIFIED"}
    r = client.post("/api/areas/atbasar/road-events", json=body, headers=auth("viewer"))
    assert r.status_code == 403
    r = client.post("/api/plan-versions/plan-a-v1/alternatives", json={"policy": "BALANCED"}, headers=auth("operator"))
    assert r.status_code == 403


def test_overview_and_layers(client, auth):
    areas = client.get("/api/areas", headers=auth()).json()
    assert [a["id"] for a in areas] == ["atbasar", "kokshetau"]
    atb = areas[0]
    assert atb["status"] in ("WATCH", "WARNING", "CRITICAL")
    assert atb["plan"]["status"] == "PLAN_AT_RISK"
    for layer in ("roads", "buildings", "facilities", "sectors", "bridges", "bottlenecks", "task_sites", "river"):
        r = client.get(f"/api/areas/atbasar/layers/{layer}", headers=auth())
        assert r.status_code == 200 and r.json()["type"] == "FeatureCollection", layer
    assert client.get("/api/areas/atbasar/layers/nope", headers=auth()).status_code == 400
    assert client.get("/api/areas/nowhere", headers=auth()).status_code == 404


def test_scenario_rendering(client, auth):
    sc = client.get("/api/areas/atbasar/scenario", headers=auth()).json()
    assert sc["mode"] == "SIMULATION" and len(sc["image_corners"]) == 4
    png = client.get(f"/api/scenarios/{sc['id']}/frames/300/depth.png", headers=auth())
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    ext = client.get(f"/api/scenarios/{sc['id']}/frames/300/extent", headers=auth()).json()
    assert ext["features"]
    tile = client.get("/api/tiles/terrain/atbasar/12/2824/1340.png")
    assert tile.status_code == 200 and tile.content[:4] == b"\x89PNG"
    hydro = client.get("/api/areas/atbasar/hydrograph", headers=auth()).json()
    obs = hydro["stations"][0]["observations"]
    assert any(o["conflict"] for o in obs)
    assert any(o["excluded"] for o in obs)


def test_impact_and_access(client, auth):
    imp = client.get("/api/areas/atbasar/impact?t=480&include_calculation=true", headers=auth()).json()
    assert imp["buildings"]["affected"] > 0
    ec = imp["economic"]["asset_exposure"]
    assert ec["low"] <= ec["high"] and imp["calculation"]["assumptions"]["methodology"]["status"] == "DEMO"
    tl = client.get("/api/areas/atbasar/impact/timeline", headers=auth()).json()
    assert len(tl["frames"]) == 25 and len(tl["buildings"]["ids"]) == len(tl["buildings"]["depth_cm"])
    acc = client.get("/api/areas/atbasar/access", headers=auth()).json()
    r7 = next(r for r in acc["roads"] if r["road_id"] == "R7")
    assert r7["state"] == "CLOSES_IN" and r7["closes_in_min"] > 0
    assert acc["next_critical_decision"] is not None
    t8 = next(t for t in acc["tasks"] if t["code"] == "T8")
    assert t8["latest_departure"] is not None
    assert client.get("/api/areas/atbasar/impact?t=99999", headers=auth()).status_code == 400
    tl2 = client.get("/api/areas/atbasar/access/timeline", headers=auth()).json()
    assert "R7" in tl2["road_closures"]


def test_observation_conflict_resolution(client, auth):
    conflicts = client.get("/api/areas/atbasar/conflicts", headers=auth()).json()
    assert conflicts and conflicts[0]["status"] == "OPEN"
    # operators may not resolve conflicts
    c = conflicts[0]
    hp = next(o for o in c["observations"] if o["source_type"] == "HYDROPOST")
    r = client.post(f"/api/conflicts/{c['id']}/resolve", json={"selected_observation_id": hp["id"]}, headers=auth("operator"))
    assert r.status_code == 403
    dup = {"station_id": "HP-ZHABAI-ATB", "water_level_cm": 613, "source": "Field team gauge reading, Crew C5 (DEMO)",
           "source_type": "FIELD", "verification": "VERIFIED", "observed_at": "2026-04-12T09:50:00+05:00"}
    assert client.post("/api/areas/atbasar/observations", json=dup, headers=auth("operator")).status_code == 409
    bad = {**dup, "observed_at": "2026-04-12T09:50:00"}
    assert client.post("/api/areas/atbasar/observations", json=bad, headers=auth("operator")).status_code == 422


def test_import_workflow_rejects_invalid_rows(client, auth):
    csv_data = ("id,resource_type,subtype,capacity,base_id,status\n"
                "C9,CREW,RESCUE,5,BASE-A,AVAILABLE\n"
                "X1,SPACESHIP,,abc,NOWHERE,AVAILABLE\n"
                "C9,CREW,RESCUE,5,BASE-A,AVAILABLE\n")
    r = client.post("/api/areas/atbasar/imports?import_type=resources", headers=auth("operator"),
                    files={"file": ("res.csv", io.BytesIO(csv_data.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["rows_total"] == 3 and job["rows_valid"] == 1 and job["rows_invalid"] == 2
    bad = job["preview"]["rows"][1]
    assert "invalid:resource_type" in bad["errors"] and "unknown:base_id" in bad["errors"]
    conf = client.post(f"/api/imports/{job['id']}/confirm", headers=auth("operator")).json()
    assert conf["applied_count"] == 1
    assert client.post(f"/api/imports/{job['id']}/confirm", headers=auth("operator")).status_code == 409
    res = client.get("/api/areas/atbasar/resources", headers=auth()).json()
    assert any(x["id"] == "C9" for x in res)
    empty = client.post("/api/areas/atbasar/imports?import_type=resources", headers=auth("operator"),
                        files={"file": ("e.csv", io.BytesIO(b""), "text/csv")})
    assert empty.status_code == 400
    assert client.get("/api/imports/templates/observations.csv").text.startswith("station_id")


def test_validation_not_loaded_and_synthetic(client, auth):
    v = client.get("/api/areas/atbasar/validation", headers=auth()).json()
    ds = v["datasets"][0]
    assert ds["id"] == "atbasar-2024" and ds["status"] == "NOT_LOADED"
    r = client.post("/api/areas/atbasar/validation/run", json={"dataset_id": "atbasar-2024"}, headers=auth())
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_data_not_loaded"
    s = client.post("/api/areas/atbasar/validation/synthetic", headers=auth()).json()
    assert s["kind"] == "SYNTHETIC_SELF_TEST" and 0 <= s["metrics"]["iou"] <= 1
    png = client.get(f"/api/validation-runs/{s['id']}/layers/difference.png", headers=auth())
    assert png.status_code == 200


def test_reports_in_three_languages(client, auth):
    rep = client.get("/api/areas/atbasar/report", headers=auth()).json()
    assert rep["plan"]["health"] == "PLAN_AT_RISK"
    for lang, word in (("kk", "Жедел брифинг"), ("ru", "Оперативный брифинг"), ("en", "Operational briefing")):
        html = client.get(f"/api/areas/atbasar/report.html?lang={lang}", headers=auth()).text
        assert word in html


def test_outage_simulation(client, auth):
    r = client.post("/api/admin/providers/outage", json={"enabled": True}, headers=auth("admin")).json()
    assert r["external_offline"] is True
    fr = client.get("/api/areas/atbasar/freshness", headers=auth()).json()
    assert fr["external_offline"] is True
    # core functions keep working
    assert client.get("/api/areas/atbasar/access", headers=auth()).status_code == 200
    client.post("/api/admin/providers/outage", json={"enabled": False}, headers=auth("admin"))
