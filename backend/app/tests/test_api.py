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


def test_import_parsing_is_robust(client, auth):
    """Excel (ru/kk locale) CSV: cp1251 + ';'; local dd.mm.yyyy times with utc_offset; broken files → 400, never 500."""
    def up(kind, name, data):
        return client.post(f"/api/areas/atbasar/imports?import_type={kind}", headers=auth("operator"),
                           files={"file": (name, io.BytesIO(data), "application/octet-stream")})

    res = up("resources", "excel.csv", "id;resource_type;subtype;capacity;name_ru\nP77;PUMP;MOBILE;12,5;Насос\n;;;;\n".encode("cp1251"))
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["rows_total"] == 1 and job["rows_valid"] == 1
    assert job["preview"]["rows"][0]["data"]["capacity"] == 12.5 and job["preview"]["rows"][0]["data"]["name_ru"] == "Насос"
    assert job["preview"]["missing_columns"] == []
    st = client.get("/api/areas/atbasar/observations", headers=auth()).json()["observations"][0]["station_id"]
    obs = up("observations", "o.csv", (f"station_id,observed_at,utc_offset,water_level_cm,source,source_type\n"
                                       f"{st},12.04.2026 09:30,+05:00,412,Field team 3,FIELD\n"
                                       f"{st},12.04.2026 09:40,,413,Field team 3,FIELD\n").encode())
    rows = obs.json()["preview"]["rows"]
    assert rows[0]["status"] == "VALID" and rows[0]["data"]["observed_at"] == "2026-04-12T09:30:00+05:00"
    assert "timestamp_without_timezone:observed_at" in rows[1]["errors"]
    cols = up("observations", "c.csv", b"station,level\nX,1\n").json()["preview"]
    assert "station_id" in cols["missing_columns"] and "level" in cols["unknown_columns"]
    for name, data in (("b.xlsx", b"not a zip"), ("b.json", b"[1, 2]"), ("b.json", b"{bad json"), ("b.geojson", b'{"type": "FeatureCollection", "features": [{"geometry": {"type": "Point"}}]}')):
        r = up("facilities", name, data)
        assert r.status_code in (200, 400), (name, r.status_code, r.text)
    assert up("facilities", "b.xlsx", b"not a zip").json()["error"]["code"] == "unreadable_file"


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


def test_policies_and_demo_reset(client, auth):
    r = client.get("/api/policies", headers=auth("planner"))
    assert r.status_code == 200 and r.json()["policies"]["LIFE_SAFETY"]["life"] == 70
    # only an administrator may reset
    assert client.post("/api/admin/demo/reset", headers=auth("planner")).status_code == 403
    client.post("/api/areas/atbasar/resources/pool", json={"resource_type": "PUMP", "count": 8}, headers=auth("planner"))
    r = client.post("/api/admin/demo/reset", headers=auth("admin"))
    assert r.status_code == 200 and r.json()["reset"] is True
    res = client.get("/api/areas/atbasar/resources", headers=auth("planner")).json()
    assert sum(1 for x in res if x["resource_type"] == "PUMP" and x["status"] == "AVAILABLE") == 16
    audit = client.get("/api/audit?area_id=atbasar", headers=auth("admin")).json()
    assert audit is not None
