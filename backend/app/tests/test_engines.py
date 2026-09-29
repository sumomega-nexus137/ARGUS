"""Engine-level tests: scenario → access → windows → evaluator → causality → stress test → optimizer → validation."""

from __future__ import annotations

import numpy as np

from app.repositories.context import load_context
from app.services.planning.evaluator import evaluate_plan
from app.services.planning.health import plan_health
from app.services.planning.model import EvalConfig
from app.services.planning.plans import active_version, evaluate_version, to_specs, version_tasks
from app.services.routing.access import AccessConfig, build_access_model
from app.services.routing.intervals import INF, merge, subtract, threshold_intervals
from app.services.scenario.runtime import current_scenario, get_scenario, runtime_for
from app.services.stress_test.engine import run_stress_test
from app.services.validation.engine import MaskPair, metrics


def test_threshold_intervals_interpolates_crossings():
    t = np.array([0.0, 10.0, 20.0, 30.0])
    d = np.array([0.0, 0.2, 0.4, 0.1])
    iv = threshold_intervals(t, d, 0.3)
    assert len(iv) == 1
    a, b = iv[0]
    assert abs(a - 15.0) < 1e-9 and abs(b - (20 + (0.4 - 0.3) / 0.3 * 10)) < 1e-9
    assert threshold_intervals(t, np.array([0.5, 0.5, 0.5, 0.5]), 0.3) == [(-INF, INF)]
    assert merge([(0, 5), (4, 8), (10, 12)]) == [(0, 8), (10, 12)]
    assert subtract([(0, 10)], (3, 5)) == [(0, 3), (5, 10)]


def test_scenario_versions_and_conditioning(db):
    sc = current_scenario(db, "atbasar")
    assert sc.version == 2 and sc.active_member_id == "M4"
    assert sc.selection["method"] == "OBSERVATION_CONDITIONING"
    scores = {s["member"]: s["weighted_rmse_cm"] for s in sc.selection["scores"]}
    assert scores["M4"] == min(v for v in scores.values() if v is not None)


def test_road_r7_closes_earlier_in_updated_scenario(db):
    ctx = load_context(db, "atbasar")
    pv = active_version(db, "atbasar")
    rt_basis = runtime_for(get_scenario(db, pv.basis_scenario_id))
    rt_cur = runtime_for(current_scenario(db, "atbasar"))
    m1 = build_access_model(ctx, rt_basis, AccessConfig(member=rt_basis.member), now_min=0)
    m2 = build_access_model(ctx, rt_cur, AccessConfig(member=rt_cur.member), now_min=0)
    c1 = min(m1.closure_from(s, 0) for s in ctx.roads["R7"].segment_ids)
    c2 = min(m2.closure_from(s, 0) for s in ctx.roads["R7"].segment_ids)
    assert c2 < c1 - 60, (c1, c2)


def test_latest_departure_respects_closures(db):
    ctx = load_context(db, "atbasar")
    rt = runtime_for(current_scenario(db, "atbasar"))
    m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=0)
    site = ctx.sites["S-DRAIN-B"]
    L, succ = m.latest_departure({site.node: 600.0})
    base = ctx.bases["BASE-A"].node
    assert L[base] < 600.0
    # departing at the latest time must still reach the site in time
    arr, _ = m.earliest_arrival(base, L[base] - 0.01)
    assert site.node in arr and arr[site.node] <= 600.0 + 1e-6


def test_plan_a_feasible_on_basis_and_fails_on_current(db):
    ctx = load_context(db, "atbasar")
    pv = active_version(db, "atbasar")
    ev1, _ = evaluate_version(db, ctx, pv, get_scenario(db, pv.basis_scenario_id))
    ev2, _ = evaluate_version(db, ctx, pv)
    assert ev1.status != "INFEASIBLE"
    assert ev2.status == "INFEASIBLE"
    t8 = ev2.by_code["T8"]
    assert t8.status == "INFEASIBLE"
    assert {i.type for i in t8.issues} & {"NO_ROUTE", "MISSED_ACTION_WINDOW"}
    assert t8.latest_departure is not None and t8.latest_departure < (t8.planned_departure or 1e9)


def test_causal_chain_explains_t8(db):
    ctx = load_context(db, "atbasar")
    h = plan_health(db, ctx, active_version(db, "atbasar"))
    assert h["status"] == "PLAN_AT_RISK"
    chain = next(c for c in h["chains"] if c["task"] == "T8")
    types = [n["type"] for n in chain["nodes"]]
    assert types[0] == "SCENARIO_CHANGED"
    assert "ROAD_CLOSES_EARLIER" in types
    assert any(n["type"] == "ROAD_CLOSES_EARLIER" and n["params"]["road"] == "R7" for n in chain["nodes"])
    assert "RESOURCE_LOSES_ACCESS" in types
    assert types[-1] in ("TASK_MISSES_WINDOW", "TASK_NO_ROUTE")
    assert h["headline"]["type"] == "ROAD_CLOSES_EARLIER" and h["headline"]["params"]["road"] == "R7"


def test_stress_test_robustness_is_computed(db):
    ctx = load_context(db, "atbasar")
    pv = active_version(db, "atbasar")
    rt = runtime_for(current_scenario(db, "atbasar"))
    res = run_stress_test(ctx, rt, to_specs(version_tasks(db, pv), rt), 0.0)
    assert res["n_scenarios"] >= 10
    assert res["robustness"] == res["n_feasible"] / res["n_scenarios"]
    assert sum(1 for s in res["scenarios"] if s["feasible"]) == res["n_feasible"]
    kinds = {s["kind"] for s in res["scenarios"]}
    assert {"HIGHER_WATER", "EARLIER_PEAK", "CREW_DELAYED", "VEHICLE_UNAVAILABLE", "PUMP_UNAVAILABLE"} <= kinds


def test_optimizer_alternatives_are_verified_and_resource_sensitive(db):
    from app.services.optimization.alternatives import optimize

    ctx = load_context(db, "atbasar")
    pv = active_version(db, "atbasar")
    rt = runtime_for(current_scenario(db, "atbasar"))
    specs = to_specs(version_tasks(db, pv), rt)
    extra = ctx.config.get("extra_candidates", [])
    full = optimize(ctx, rt, 0.0, policy="LIFE_SAFETY", weights=None, constraints=(), plan_specs=specs,
                    extra_candidates=extra, with_stress=False)
    assert full["feasible"] and full["alternatives"]
    for alt in full["alternatives"]:
        assert all(t["status"] != "INFEASIBLE" for t in alt["evaluation"]["tasks"])
    best = full["alternatives"][0]
    assert "T8" in {t["code"] for t in best["tasks"]}
    for t in best["tasks"]:
        assert set(t["why"]) == {"task", "resource", "now", "if_delayed"}
    few = optimize(ctx, rt, 0.0, policy="LIFE_SAFETY", weights=None, constraints=(), plan_specs=specs,
                   extra_candidates=extra, unavailable={f"P{i:02d}" for i in range(9, 17)}, with_stress=False)
    assert few["alternatives"][0]["metrics"]["pumps_used"] <= 8
    assert few["alternatives"][0]["metrics"]["pumps_used"] < best["metrics"]["pumps_used"]
    # re-verify one alternative independently with the evaluator
    from app.services.planning.model import TaskSpec

    specs2 = [TaskSpec(**s) for s in best["specs"]]
    ev = evaluate_plan(ctx, rt, specs2, EvalConfig(access=AccessConfig(member=rt.member), as_of=0.0))
    assert ev.status != "INFEASIBLE"


def test_commander_constraint_is_respected(db):
    from app.services.optimization.alternatives import optimize
    from app.services.planning.model import Constraint

    ctx = load_context(db, "atbasar")
    pv = active_version(db, "atbasar")
    rt = runtime_for(current_scenario(db, "atbasar"))
    specs = to_specs(version_tasks(db, pv), rt)
    cons = (Constraint("FORBID_RESOURCE_SECTOR", resource_id="C3", sector="B"),)
    res = optimize(ctx, rt, 0.0, policy="BALANCED", weights=None, constraints=cons, plan_specs=specs,
                   extra_candidates=ctx.config.get("extra_candidates", []), with_stress=False, max_alternatives=1)
    for t in res["alternatives"][0]["tasks"]:
        if ctx.sites[t["site_id"]].sector == "B":
            assert t["crew"] != "C3"


def test_validation_metrics_exact():
    from affine import Affine

    from app.providers.flood.base import GridInfo

    obs = np.zeros((10, 10), bool)
    mod = np.zeros((10, 10), bool)
    obs[2:6, 2:6] = True  # 16
    mod[4:8, 4:8] = True  # 16, overlap 4
    g = GridInfo("EPSG:32642", Affine(10, 0, 0, 0, -10, 0), 10, 10)
    m = metrics(MaskPair(obs, mod, np.ones_like(obs), g))
    assert m["tp_cells"] == 4 and m["fp_cells"] == 12 and m["fn_cells"] == 12
    assert m["iou"] == round(4 / 28, 4)
    assert m["precision"] == 0.25 and m["recall"] == 0.25


def test_kokshetau_bottlenecks(db):
    from app.services.routing.bottlenecks import analyze

    ctx = load_context(db, "kokshetau")
    rt = runtime_for(current_scenario(db, "kokshetau"))
    res = analyze(ctx, rt, 0.0)
    ids = {b["id"] for b in res["bottlenecks"]}
    assert {"KBN-B1", "KBN-UP", "KBN-CV", "KBN-CH"} <= ids
    assert res["structural_candidates"]
    b1 = next(b for b in res["bottlenecks"] if b["id"] == "KBN-B1")
    assert b1["affected_sectors"] or b1["affected_facilities"]
