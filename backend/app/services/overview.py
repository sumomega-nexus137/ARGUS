"""Regional overview: WHERE DOES ATTENTION NEED TO GO?"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import OperationalArea
from app.repositories.context import load_context
from app.services.clock import area_now, to_minutes
from app.services.ingest.observations import effective_observations
from app.services.ingest.providers import area_freshness, outage_enabled
from app.services.planning.health import plan_health
from app.services.planning.plans import active_version, plan_name
from app.services.scenario.runtime import current_scenario, runtime_for

LEVELS = ["NORMAL", "WATCH", "WARNING", "CRITICAL"]


def _lvl(stage: float | None, st: dict, forecast: bool) -> int:
    if stage is None:
        return 0
    lvl = 0
    for k, v in (("watch", 1), ("warning", 2), ("critical", 3)):
        thr = st.get(k)
        if thr is not None and stage >= thr:
            lvl = v
    return max(0, lvl - 1) if forecast else lvl


def area_overview(db: Session, area: OperationalArea, include_health: bool = True) -> dict:
    ctx = load_context(db, area.id)
    sc = current_scenario(db, area.id)
    rt = runtime_for(sc)
    now = area_now(area)
    now_min = to_minutes(rt.reference_time, now)
    reasons: list[dict] = []
    level = 0
    gauges = []
    for sid, st in ctx.stations.items():
        eff, _ = effective_observations(db, sid, until=now)
        last = eff[-1].obs if eff else None
        prev = next((e.obs for e in reversed(eff[:-1]) if last and (last.observed_at - e.obs.observed_at).total_seconds() >= 1800), None)
        trend = None
        if last and prev:
            hours = (last.observed_at - prev.observed_at).total_seconds() / 3600
            trend = round((last.water_level_cm - prev.water_level_cm) / hours, 1) if hours > 0 else None
        # forecast series only for the scenario's own stage station (official gauges may use other datums)
        is_proxy = sid == (sc.parameters or {}).get("station_id")
        series = rt.provider.gauge_series(rt.member) if is_proxy else []
        fut = [s for t, s in series if t >= now_min]
        peak = max(fut) if fut else None
        peak_t = next((t for t, s in series if t >= now_min and s == peak), None) if peak is not None else None
        obs_lvl = _lvl(last.water_level_cm if last else None, st, False)
        fc_lvl = _lvl(peak, st, True)
        if obs_lvl:
            reasons.append({"type": "OBSERVED_STAGE", "params": {"station": sid, "stage_cm": last.water_level_cm,
                                                                 "level": LEVELS[obs_lvl]}})
        if fc_lvl:
            reasons.append({"type": "FORECAST_PEAK", "params": {"station": sid, "stage_cm": round(peak, 1),
                                                                "level": LEVELS[fc_lvl + 1] if fc_lvl < 3 else "CRITICAL",
                                                                "at_min": peak_t}})
        level = max(level, obs_lvl, fc_lvl)
        age = (now - last.observed_at).total_seconds() / 60 if last else None
        gauges.append({
            "station_id": sid, "names": st["names"], "stage_cm": last.water_level_cm if last else None,
            "observed_at": last.observed_at.isoformat() if last else None, "age_min": None if age is None else round(age),
            "source": last.source if last else None, "source_type": last.source_type if last else None,
            "verification": last.verification if last else None, "mode": last.mode if last else None,
            "trend_cm_h": trend, "forecast_peak_cm": None if peak is None else round(peak, 1), "forecast_peak_at_min": peak_t,
            "thresholds": {"bankfull": st["bankfull"], "watch": st["watch"], "warning": st["warning"], "critical": st["critical"]},
            "open_conflict": any(e.conflict_status == "OPEN" for e in eff), "scenario_station": is_proxy,
            "provider": st.get("provider"),
        })
    health = None
    pv = active_version(db, area.id)
    if include_health and pv is not None:
        h = plan_health(db, ctx, pv)
        health = {"plan_version_id": pv.id, "plan_name": plan_name(db, pv), "version": pv.version, "status": h["status"],
                  "severity": h["severity"], "headline": h["headline"], "failed": h["evaluation"]["failed"],
                  "at_risk": h["evaluation"]["at_risk"], "next_critical_decision": h["next_critical_decision"]}
        if h["severity"] == "critical":
            level = max(level, 2)
            reasons.append({"type": "PLAN_AT_RISK", "params": {"plan": plan_name(db, pv), "failed": h["evaluation"]["failed"]}})
        nd = h["next_critical_decision"]
        if nd and nd["minutes"] <= get_settings().window_closing_threshold_min:
            level = 3
            reasons.append({"type": "WINDOW_CLOSING", "params": {"task": nd["task"], "minutes": round(nd["minutes"])}})
    fresh = area_freshness(db, area)
    return {
        "id": area.id, "names": {"kk": area.name_kk, "ru": area.name_ru, "en": area.name_en, "original": area.name_original},
        "river_names": area.river_names, "archetype": area.archetype, "center": [area.center.x, area.center.y],
        "bbox": area.bbox, "is_demo": area.is_demo, "clock_mode": area.clock_mode, "now": now.isoformat(),
        "utc_offset_min": area.utc_offset_min, "status": LEVELS[level], "reasons": reasons, "gauges": gauges,
        "scenario": {"id": sc.id, "version": sc.version, "member": sc.active_member_id, "mode": sc.mode,
                     "reference_time": sc.reference_time.isoformat(), "model_version": sc.model_version},
        "plan": health, "freshness": fresh, "external_offline": outage_enabled(), "data_version": area.data_version,
    }
