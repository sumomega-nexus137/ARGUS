"""The primary competition demo flow, end to end, through the public API (Atbasar / Zhabai).

PLAN A AT RISK → WHY → STRESS TEST → GENERATE ALTERNATIVES → PUMPS 16→8 → re-run → adopt → review →
approve → activate → operations valid → manual road closure breaks the plan → explain → RECOMPUTE →
new version → audit trail records it.
"""

from __future__ import annotations


def test_competition_demo_flow(client, auth):
    P, C, O = auth("planner"), auth("commander"), auth("operator")

    # 1. PLAN A — AT RISK, with WHY
    ops = client.get("/api/areas/atbasar/operations", headers=P).json()
    assert ops["active_version"]["id"] == "plan-a-v1"
    h = ops["health"]
    assert h["status"] == "PLAN_AT_RISK"
    assert h["headline"]["type"] == "ROAD_CLOSES_EARLIER" and h["headline"]["params"]["road"] == "R7"
    chain = [n["type"] for n in next(c for c in h["chains"] if c["task"] == "T8")["nodes"]]
    assert chain[:2] == ["SCENARIO_CHANGED", "ROAD_CLOSES_EARLIER"] and "RESOURCE_LOSES_ACCESS" in chain

    # 2. STRESS TEST
    st = client.post("/api/plan-versions/plan-a-v1/stress-test", headers=P).json()
    assert st["n_scenarios"] > 10 and st["n_feasible"] == sum(s["feasible"] for s in st["scenarios"])

    # 3. GENERATE ALTERNATIVES (CP-SAT)
    alt = client.post("/api/plan-versions/plan-a-v1/alternatives", json={"policy": "LIFE_SAFETY"}, headers=P).json()
    assert alt["feasible"] and alt["alternatives"]
    best16 = alt["alternatives"][0]
    assert best16["robustness"]["n_feasible"] > st["n_feasible"]
    labels = {a["label"] for a in alt["alternatives"]}
    assert "POLICY_OPTIMUM" in labels

    # 4. AVAILABLE PUMPS 16 → 8, re-run: the plan changes
    pool = client.post("/api/areas/atbasar/resources/pool", json={"resource_type": "PUMP", "count": 8}, headers=P).json()
    assert pool["before"] == 16 and pool["after"] == 8
    alt8 = client.post("/api/plan-versions/plan-a-v1/alternatives", json={"policy": "LIFE_SAFETY"}, headers=P).json()
    best8 = alt8["alternatives"][0]
    assert best8["metrics"]["pumps_used"] <= 8
    assert {t["code"] for t in best8["tasks"]} != {t["code"] for t in best16["tasks"]}
    assert any(e["reason"] == "INSUFFICIENT_PUMPS" for e in best8["excluded_candidates"])

    # 5. adopt → review → approve → activate (human approval; planner cannot approve)
    pv = client.post(f"/api/optimization-runs/{alt8['id']}/adopt", json={"alternative_id": best8["id"]}, headers=P).json()
    assert pv["status"] == "DRAFT" and pv["version"] == 2 and pv["origin"] == "OPTIMIZER"
    assert client.post(f"/api/plan-versions/{pv['id']}/transition", json={"target": "REVIEWED"}, headers=P).status_code == 200
    denied = client.post(f"/api/plan-versions/{pv['id']}/transition", json={"target": "APPROVED"}, headers=P)
    assert denied.status_code == 403
    assert client.post(f"/api/plan-versions/{pv['id']}/transition", json={"target": "APPROVED"}, headers=C).status_code == 200
    act = client.post(f"/api/plan-versions/{pv['id']}/transition", json={"target": "ACTIVE"}, headers=C).json()
    assert act["status"] == "ACTIVE"
    ops = client.get("/api/areas/atbasar/operations", headers=P).json()
    assert ops["active_version"]["id"] == pv["id"]
    assert ops["health"]["evaluation"]["failed"] == []
    old = client.get("/api/plan-versions/plan-a-v1", headers=P).json()
    assert old["status"] == "SUPERSEDED"

    # 6. operator updates a task
    first = ops["active_version"]["tasks"][0]
    r = client.post(f"/api/plan-tasks/{first['id']}/status", json={"status": "EN_ROUTE"}, headers=O)
    assert r.status_code == 200

    # 7. manually close a road used by the active plan → road graph changes → PLAN AT RISK
    routes = [t for t in ops["health"]["evaluation"]["tasks"] if t["route_roads"] and t["code"] != first["code"]]
    road = next(r for t in routes for r in t["route_roads"] if r in ("R7", "R4", "R3", "R2", "R10"))
    ev = client.post("/api/areas/atbasar/road-events", json={"road_id": road, "state": "CLOSED", "verification": "VERIFIED",
                                                            "source": "Field patrol (test)"}, headers=O).json()
    assert ev["pipeline"]["steps"][0]["step"] == "STORE"
    assert [s["step"] for s in ev["pipeline"]["steps"]][-1] == "PLAN_STRESS_CHECK"
    health = client.get(f"/api/plan-versions/{pv['id']}/health", headers=P).json()
    assert health["status"] == "PLAN_AT_RISK"
    nodes = [n for c in health["chains"] for n in c["nodes"]]
    assert any(n["type"] == "ROAD_CLOSED_FIELD" and n["params"]["road"] == road for n in nodes)

    # 8. RECOMPUTE → new version, old versions kept
    rc = client.post("/api/areas/atbasar/recompute", json={"policy": "LIFE_SAFETY"}, headers=P).json()
    new = rc["plan_version"]
    assert new["origin"] == "RECOMPUTE" and new["status"] == "DRAFT" and new["version"] == 3
    assert new["change_summary"]["trigger"] == "RECOMPUTE"
    plans = client.get("/api/areas/atbasar/plans", headers=P).json()
    versions = next(p for p in plans if p["id"] == "plan-a")["versions"]
    assert [v["version"] for v in versions] == [1, 2, 3]
    cmp = client.get(f"/api/plans/plan-a/compare?a={pv['id']}&b={new['id']}", headers=P).json()
    assert cmp["tasks"]

    # 9. audit trail answers "why did ARGUS change its result?"
    audit = client.get("/api/audit?area_id=atbasar&limit=500", headers=P).json()
    actions = {a["action"] for a in audit}
    for a in ("PLAN_STRESS_TESTED", "ALTERNATIVES_GENERATED", "RESOURCE_POOL_CHANGED", "PLAN_APPROVED", "PLAN_ACTIVATED",
              "ROAD_CLOSED", "OPTIMIZER_RERUN", "PLAN_VERSION_CREATED", "TASK_STATUS_CHANGED", "PIPELINE_RUN"):
        assert a in actions, a
    changes = client.get("/api/areas/atbasar/changes?since_version=1", headers=P).json()
    assert any(c["action"] == "ROAD_CLOSED" for c in changes["changes"])
