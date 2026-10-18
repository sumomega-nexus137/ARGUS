"""End-to-end checks of the HISTORICAL real-data pilots (Atbasar / Zhabai, Kokshetau / Kylshakty)."""

from __future__ import annotations

import json

from app.core.config import get_settings


def test_packs_verified_and_no_redownload(app):
    from app.realdata import install as rd

    for area in rd.AREAS:
        st = rd.verify_installed(area)  # re-hashes every manifest file
        assert st.installed and st.files_verified > 10
        # a second install is a no-op (no network: the socket guard would fail any download)
        assert rd.install(area).installed


def test_areas_are_historical_real_geography(client, auth):
    H = auth("viewer")
    areas = {a["id"]: a for a in client.get("/api/areas", headers=H).json()}
    assert set(areas) == {"atbasar", "kokshetau"}
    for aid in areas:
        a = client.get(f"/api/areas/{aid}", headers=H).json()
        assert a["data_profile"] == "historical" and a["clock_mode"] == "HISTORICAL" and not a["is_demo"]
        roads = client.get(f"/api/areas/{aid}/layers/roads", headers=H).json()["features"]
        blds = client.get(f"/api/areas/{aid}/layers/buildings", headers=H).json()["features"]
        assert len(roads) > 1000 and len(blds) > 5000
        assert all(r["properties"]["names"]["en"] for r in roads[:50])
        assert client.get(f"/api/areas/{aid}/layers/river", headers=H).json()["features"]
        assert client.get(f"/api/areas/{aid}/layers/waterways", headers=H).json()["features"]
        lon, lat = a["center"]
        assert 68 < lon < 70 and 51 < lat < 54  # Akmola region, not synthetic coordinates
    assert areas["atbasar"]["scenario"]["mode"] == "HISTORICAL"
    assert areas["kokshetau"]["scenario"]["mode"] == "SIMULATION"


def test_atbasar_scenario_low_base_high_frames(client, auth):
    H = auth("viewer")
    sc = client.get("/api/areas/atbasar/scenario", headers=H).json()
    assert {m["id"] for m in sc["members"]} == {"LOW", "BASE", "HIGH"}
    assert sc["provider"] == "raster_manifest"
    r = client.get(f"/api/scenarios/{sc['id']}/frames/0/depth.png?member=BASE", headers=H)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and len(r.content) > 500


def test_validation_recomputed_from_masks(client, auth):
    H = auth("planner")
    st = client.get("/api/areas/atbasar/validation", headers=H).json()
    ds = st["datasets"][0]
    assert ds["status"] == "READY" and "Sentinel-2" in ds["observed_source"]
    assert st["historical"]["label"] == "HISTORICAL_SAME_EVENT_SPATIAL_HOLDOUT"
    assert st["historical"]["observed_qc"]["status"] == "AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC"
    run = client.post("/api/areas/atbasar/validation/run", json={"dataset_id": "atbasar-2024"}, headers=H).json()
    pm = run["result"]["protocol_metrics"]
    # compare against the pack's own independently-produced calibration file (not hard-coded numbers)
    from app.core.config import resolve_data_path

    cm = json.loads((resolve_data_path("<realdata>/atbasar/generated") / "scenarios/atbasar/calibration_metrics.json").read_text())
    ref = cm["spatial_holdout_metrics_same_event"]
    for k in ("iou", "precision", "recall", "f1"):
        assert abs(pm["holdout"][k] - ref[k]) < 0.002, (k, pm["holdout"][k], ref[k])
    assert run["metrics"]["iou"] == pm["holdout"]["iou"]
    assert abs(pm["all_usable"]["iou"] - cm["all_usable_pixels_metrics"]["iou"]) < 0.002
    for layer in ("observed", "modelled", "difference"):
        assert client.get(f"/api/validation-runs/{run['id']}/layers/{layer}.png", headers=H).status_code == 200


def test_impact_exposure_only_no_money(client, auth):
    H = auth("viewer")
    f = client.get("/api/areas/atbasar/impact?t=0&include_calculation=true", headers=H).json()
    assert f["economic"]["asset_exposure"] is None and f["economic"]["status"] == "NOT_AVAILABLE_NO_APPROVED_VALUATION"
    assert f["population"]["method"] == "worldpop_dasymetric" and f["population"]["vulnerable_exposed"] is None
    assert f["buildings"]["total"] > 5000


def test_plan_a_baseline_then_high_real_causal_chain(client, auth):
    H = auth("planner")
    plans = client.get("/api/areas/atbasar/plans", headers=H).json()
    vid = plans[0]["versions"][-1]["id"]

    # Competition starts on the plan's approved BASE member: a meaningful plan must work before stress is applied.
    h0 = client.get(f"/api/plan-versions/{vid}/health", headers=H).json()
    assert h0["status"] == "PLAN_VALID"
    assert h0["scenario"]["member"] == "BASE" and h0["basis_scenario"]["member"] == "BASE"

    # Deliberate exercise escalation: the exact same human plan becomes at risk under HIGH and ARGUS explains why.
    r = client.post("/api/areas/atbasar/scenario/select-member",
                    json={"member_id": "HIGH", "note": "Competition exercise escalation BASE → HIGH", "lock": False},
                    headers=H)
    assert r.status_code == 200
    h = client.get(f"/api/plan-versions/{vid}/health", headers=H).json()
    assert h["status"] == "PLAN_AT_RISK" and h["scenario"]["member"] == "HIGH"
    types = [[n["type"] for n in chain["nodes"]] for chain in h["chains"]]
    assert any(t[:4] == ["SCENARIO_CHANGED", "ROAD_CLOSES_EARLIER", "RESOURCE_LOSES_ACCESS", "TASK_MISSES_WINDOW"]
               for t in types)
    assert h["next_critical_decision"] is not None

    # Restore BASE so the stress-test test measures robustness from the approved plan state.
    r = client.post("/api/areas/atbasar/scenario/select-member",
                    json={"member_id": "BASE", "note": "Restore approved BASE after causal-chain test", "lock": False},
                    headers=H)
    assert r.status_code == 200


def test_stress_alternatives_pumps_and_recompute(client, auth):
    P, C, OP = auth("planner"), auth("commander"), auth("operator")
    vid = client.get("/api/areas/atbasar/plans", headers=P).json()[0]["versions"][-1]["id"]

    st = client.post(f"/api/plan-versions/{vid}/stress-test", headers=P).json()
    print("ARGUS_STRESS_PLAN_A", json.dumps({
        "n_scenarios": st["n_scenarios"], "n_feasible": st["n_feasible"],
        "robustness": st["robustness"], "baseline_status": st["baseline_status"],
        "scenarios": [{"id": s["id"], "kind": s["kind"], "member": s["member"],
                       "status": s["status"], "failed": s["failed_tasks"]} for s in st["scenarios"]]
    }))
    kinds = {s["kind"] for s in st["scenarios"]}
    assert st["member"] == "BASE"
    assert st["baseline_status"] == "FEASIBLE"
    assert 0 < st["n_feasible"] < st["n_scenarios"]  # mixed, calculated result — not a hard-coded percentage
    assert {"HIGHER_WATER", "EARLIER_PEAK", "ROUTE_UNAVAILABLE", "CREW_DELAYED",
            "VEHICLE_UNAVAILABLE", "PUMP_UNAVAILABLE"} <= kinds

    alts = client.post(f"/api/plan-versions/{vid}/alternatives", json={"policy": "LIFE_SAFETY"}, headers=P).json()
    assert alts["feasible"] and alts["alternatives"]
    print("ARGUS_ALT_ROBUSTNESS", json.dumps([
        {"id": a["id"], "label": a["label"], "evaluation": a["evaluation"]["status"], "robustness": a.get("robustness")}
        for a in alts["alternatives"]
    ]))
    robust = [a for a in alts["alternatives"] if a.get("robustness") and a["robustness"].get("robustness") is not None]
    assert robust
    assert max(a["robustness"]["robustness"] for a in robust) > st["robustness"]
    assert all(t.get("why") for a in alts["alternatives"] for t in a["tasks"])

    r = client.post("/api/areas/atbasar/resources/pool", json={"resource_type": "PUMP", "count": 8}, headers=P)
    assert r.status_code == 200
    alts8 = client.post(f"/api/plan-versions/{vid}/alternatives", json={"policy": "BALANCED"}, headers=P).json()
    assert all(a["metrics"]["pumps_used"] <= 8 for a in alts8["alternatives"])

    roads = client.get("/api/areas/atbasar/access", headers=OP).json()["roads"]
    target = next(r["road_id"] for r in roads if r["road_class"] in ("trunk", "primary", "secondary"))
    ev = client.post("/api/areas/atbasar/road-events", json={"road_id": target, "state": "CLOSED"}, headers=OP).json()
    assert ev["pipeline"]["steps"][-1]["step"] == "PLAN_STRESS_CHECK"
    rc = client.post("/api/areas/atbasar/recompute", json={"policy": "BALANCED"}, headers=P).json()
    new_vid = rc["plan_version"]["id"]
    assert rc["plan_version"]["status"] == "DRAFT"
    for target_status, who in (("REVIEWED", P), ("APPROVED", C), ("ACTIVE", C)):
        assert client.post(f"/api/plan-versions/{new_vid}/transition", json={"target": target_status}, headers=who).status_code == 200
    assert client.post(f"/api/plan-versions/{new_vid}/transition", json={"target": "REVIEWED"}, headers=OP).status_code in (403, 409)

def test_kokshetau_bottlenecks_real_candidates(client, auth):
    from app.realdata.build import ensure_built

    bundle = ensure_built("kokshetau")
    analysis = json.loads((bundle / "analysis.json").read_text(encoding="utf-8"))
    cal = analysis["exercise_calibration"]
    # Official 2024 reports describe localised river-adjacent impacts, not city-wide inundation.
    # The exercise is intentionally conservative and only order-of-magnitude bounded: reported impact
    # categories are heterogeneous and are NOT treated as exact building labels.
    assert cal["status"] == "HISTORICALLY_IMPACT_BOUNDED_NOT_SPATIALLY_CALIBRATED"
    assert cal["channel_corridor_m"] <= 150
    base_hits = cal["modelled_base_building_centroids_depth_ge_0_10m"]
    high_hits = cal["modelled_high_building_centroids_depth_ge_0_10m"]
    # Current conservative exercise is deliberately near the reported order of magnitude
    # (58 heterogeneous official impact units) and must never regress to a city-wide flood.
    assert 40 <= base_hits <= 80, base_hits
    assert base_hits <= high_hits <= 120, high_hits
    assert 0.65 <= cal["base_to_reported_aggregate_ratio"] <= 1.35
    anchors = cal.get("historical_anchor_checks", [])
    ertostik = next((x for x in anchors if "ЕРТОСТИК" in x.get("name", "").upper()
                     or "ERTOSTIK" in x.get("name", "").upper()), None)
    assert ertostik and ertostik["matched"] and ertostik["base_exercise_depth_m"] >= 0.05

    H = auth("planner")
    lay = client.get("/api/areas/kokshetau/layers/bottlenecks", headers=H).json()["features"]
    kinds = {f["properties"]["kind"] for f in lay}
    assert "BRIDGE" in kinds and ({"CULVERT", "CHANNEL_CONSTRAINT"} & kinds) and "LOW_ROAD" in kinds
    res = client.post("/api/areas/kokshetau/bottlenecks/analyze", json={"bottleneck_ids": [], "as_of_min": 60}, headers=H).json()
    assert res["bottlenecks"] and any(b["affected_sectors"] or b["affected_facilities"] for b in res["bottlenecks"])
    assert all("hydraulic" in (b["notes"] or "").lower() or b["kind"] != "BRIDGE" for b in res["bottlenecks"])


def test_history_and_offline_live_context(client, auth):
    H = auth("viewer")
    h = client.get("/api/areas/atbasar/history", headers=H).json()
    assert h["available"] and h["events"] and h["glofas"]["rows"] and h["satellite"]["flood_item"] == "S2A_42UVC_20240414_1_L2A"
    live = client.get("/api/areas/atbasar/context/live?refresh=true", headers=H).json()
    assert live["glofas"]["mode"] in ("OFFLINE", "CACHED", "STALE")  # network blocked: never LIVE
    fr = client.get("/api/areas/atbasar/freshness", headers=H).json()["sources"]
    byl = {s["layer"]: s for s in fr}
    assert byl["kazhydromet"]["freshness"] == "NOT_CONFIGURED" and byl["tasqyn"]["freshness"] == "NOT_CONFIGURED"
    assert byl["resources"]["mode"] == "SIMULATION" and byl["satellite"]["mode"] == "HISTORICAL"
    assert get_settings().data_profile == "historical"


def test_reports_three_languages(client, auth):
    H = auth("commander")
    for lang in ("kk", "ru", "en"):
        r = client.get(f"/api/areas/atbasar/report.html?lang={lang}", headers=H)
        assert r.status_code == 200 and "Атбасар" in r.text or "Atbasar" in r.text
