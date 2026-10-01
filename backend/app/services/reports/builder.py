"""Operational briefing report (JSON). Rendered by the frontend (print → PDF) and by the server-side
HTML template (``/report.html``) which is the integration point for headless PDF generation."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelVersion, OperationalArea, OptimizationRun, StressTestRun
from app.repositories.context import load_context
from app.services.clock import area_now, to_minutes
from app.services.deadlines.windows import facility_access, road_windows, sector_access
from app.services.impact import assumptions as A
from app.services.impact.engine import frame_impact
from app.services.ingest.providers import area_freshness, outage_enabled
from app.services.overview import area_overview
from app.services.planning.health import plan_health
from app.services.planning.plans import active_version, plan_name
from app.services.routing.access import AccessConfig, build_access_model
from app.services.scenario.runtime import current_scenario, runtime_for


def build_report(db: Session, area: OperationalArea) -> dict:
    ctx = load_context(db, area.id)
    sc = current_scenario(db, area.id)
    rt = runtime_for(sc)
    now = area_now(area)
    now_min = to_minutes(rt.reference_time, now)
    m = build_access_model(ctx, rt, AccessConfig(member=rt.member), now_min=now_min)
    impact_now = frame_impact(ctx, rt, rt.member, now_min, m)
    peak_t = max(rt.frame_offsets, key=lambda off: frame_impact(ctx, rt, rt.member, float(off), None)["buildings"]["affected"]
                 if off >= now_min else -1)
    impact_peak = frame_impact(ctx, rt, rt.member, float(peak_t), m)
    roads = [r for r in road_windows(m, now_min) if r["state"] in ("CLOSED", "RESTRICTED", "CLOSES_IN")][:10]
    sectors, loss = sector_access(m, now_min)
    facilities = facility_access(m, now_min, loss)
    pv = active_version(db, area.id)
    health = plan_health(db, ctx, pv) if pv else None
    stress = None
    alternatives = None
    if pv is not None:
        st = db.scalars(select(StressTestRun).where(StressTestRun.plan_version_id == pv.id)
                        .order_by(StressTestRun.created_at.desc())).first()
        if st:
            stress = {"id": st.id, "n_scenarios": st.n_scenarios, "n_feasible": st.n_feasible, "robustness": st.robustness,
                      "created_at": st.created_at}
        opt = db.scalars(select(OptimizationRun).where(OptimizationRun.area_id == area.id,
                                                       OptimizationRun.kind.in_(("ALTERNATIVES", "RECOMPUTE")))
                         .order_by(OptimizationRun.started_at.desc())).first()
        if opt:
            alternatives = {"id": opt.id, "policy": opt.policy, "weights": opt.weights, "created_at": opt.started_at,
                            "alternatives": [{"id": a["id"], "label": a["label"], "metrics": a["metrics"],
                                              "robustness": a.get("robustness"), "status": a["evaluation"]["status"]}
                                             for a in opt.result.get("alternatives", [])]}
    ov = area_overview(db, area, include_health=False)
    historical = None
    if (area.config or {}).get("data_profile") == "historical":
        from app.models import ValidationRun

        vr = db.scalars(select(ValidationRun).where(ValidationRun.area_id == area.id, ValidationRun.kind == "REAL")
                        .order_by(ValidationRun.created_at.desc())).first()
        historical = {"role": (area.config or {}).get("role"), "limitations": (sc.provenance or {}).get("limitations", []),
                      "assumptions": (area.config or {}).get("assumptions", []),
                      "validation": None if vr is None else {**{k: vr.metrics.get(k) for k in ("iou", "precision", "recall", "f1")},
                                                             "label": (vr.result or {}).get("label")}}
    return {
        "generated_at": datetime.now(UTC).isoformat(), "op_time": now.isoformat(), "clock_mode": area.clock_mode,
        "area": {"id": area.id, "names": {"kk": area.name_kk, "ru": area.name_ru, "en": area.name_en},
                 "river_names": area.river_names, "is_demo": area.is_demo, "utc_offset_min": area.utc_offset_min},
        "status": ov["status"], "status_reasons": ov["reasons"], "gauges": ov["gauges"],
        "scenario": {"id": sc.id, "version": sc.version, "name": sc.name, "mode": sc.mode, "member": sc.active_member_id,
                     "selection": sc.selection, "reference_time": sc.reference_time.isoformat(),
                     "model_version": sc.model_version, "provider_note": rt.provider.mode_note,
                     "envelope": (sc.uncertainty or {}).get("envelope", [])},
        "now_min": now_min, "reference_time": rt.reference_time.isoformat(),
        "impact_now": impact_now, "impact_peak": {**impact_peak, "t_min": peak_t},
        "critical_roads": roads, "sectors": sectors, "facilities": facilities[:10],
        "plan": None if pv is None else {"id": pv.id, "name": plan_name(db, pv), "version": pv.version, "status": pv.status,
                                         "approved_by": pv.approved_by, "approved_at": pv.approved_at,
                                         "health": health["status"] if health else None,
                                         "headline": health["headline"] if health else None,
                                         "chains": health["chains"] if health else [],
                                         "tasks": health["evaluation"]["tasks"] if health else [],
                                         "resource_conflicts": health["evaluation"]["resource_conflicts"] if health else [],
                                         "next_critical_decision": health["next_critical_decision"] if health else None},
        "stress_test": stress, "alternatives": alternatives,
        "data_sources": area_freshness(db, area), "external_offline": outage_enabled(),
        "assumptions": {"impact": A.as_dict(), "demo": area.is_demo,
                        "notes": (["All DEMO fixtures are synthetic.", "Economic values are ranges based on stated assumptions.",
                                   "Flood surfaces come from precomputed scenario members (no hydrodynamic simulation in ARGUS)."]
                                  if area.is_demo else
                                  [a["note"] for a in (area.config or {}).get("assumptions", [])] +
                                  ["Flood surfaces come from precomputed scenario members (no hydrodynamic simulation in ARGUS)."])},
        "model_versions": [{"component": mv.component, "version": mv.version} for mv in
                           db.scalars(select(ModelVersion).where(ModelVersion.active.is_(True)).order_by(ModelVersion.component))],
        "data_version": area.data_version, "historical": historical,
    }
