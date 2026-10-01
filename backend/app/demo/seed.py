"""Seed the database with DEMO fixtures (idempotent: only when no areas exist)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.base import new_id
from app.demo import library
from app.demo.generator import DEMO_NOTE, generate_all
from app.models import (
    ApprovedAction,
    Base_,
    Bottleneck,
    Bridge,
    Building,
    CriticalFacility,
    HydroStation,
    ModelVersion,
    Observation,
    OperationalArea,
    Plan,
    PlanTask,
    PlanVersion,
    PopulationZone,
    ProviderStatus,
    Resource,
    ResourceStatus,
    RoadNode,
    RoadSegment,
    Scenario,
    Sector,
    TaskSite,
    User,
)
from app.services.audit import Actor, record
from app.services.ingest.observations import detect_conflicts
from app.services.scenario.conditioning import condition_current

log = get_logger("argus.seed")


def _load(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _names(p: dict) -> dict:
    return {k: p.get(k) for k in ("name_kk", "name_ru", "name_en", "name_original")}


def _names_from(n: dict) -> dict:
    return {"name_kk": n.get("kk"), "name_ru": n.get("ru"), "name_en": n.get("en"),
            "name_original": n.get("original") or n.get("ru")}


def ensure_demo_files() -> None:
    demo = get_settings().demo_dir
    if not (demo / "atbasar" / "area.json").exists() or not (demo / "kokshetau" / "area.json").exists():
        log.info("demo fixtures missing — generating into %s", demo)
        generate_all(demo)


def seed_users(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(User)):
        return
    pw = hash_password(library.DEMO_PASSWORD)
    for u in library.USERS:
        db.add(User(username=u["username"], full_name=u["full_name"], role=u["role"], password_hash=pw))


def seed_library(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(ApprovedAction)):
        return
    for a in library.ACTIONS:
        db.add(ApprovedAction(
            id=a["id"], area_id=None, action_type=a["action_type"], **_names_from(a["names"]),
            description=a["description"], requirements=a["requirements"], setup_min=a["setup_min"],
            execution_min=a["execution_min"], safety_buffer_min=a["safety_buffer_min"],
            equipment_release=a["equipment_release"], site_kinds=a["site_kinds"], prerequisites=a["prerequisites"],
            constraints=a["constraints"], approved_by=library.DEMO_APPROVER, notes=DEMO_NOTE,
        ))
    for mid, comp, ver, desc in library.MODEL_VERSIONS:
        db.add(ModelVersion(id=mid, component=comp, version=ver, description=desc, active=True))


def seed_area(db: Session, area_dir: Path) -> None:
    a = _load(area_dir / "area.json")
    area_id = a["id"]
    hist = a.get("data_profile") == "historical"
    src_default = "DEMO" if not hist else "OpenStreetMap (ODbL)"
    ref = datetime.fromisoformat(a["reference_time"])
    start = datetime.fromisoformat(a["clock_start"]) if a.get("clock_start") else ref
    config = {"grid": a["grid"], "static_version": 1, "data_profile": a.get("data_profile", "demo")}
    if hist:
        config.update({k: a[k] for k in ("river_lines", "dem_path", "economic_model", "population_method", "assumptions",
                                         "pack", "validation", "role", "population_meta", "road_meta") if k in a})
        config.update({"clock_start": start.isoformat(), "bundle_dir": str(area_dir), "demo_note": None})
    else:
        config.update({"river_centerline": a["river_centerline"], "demo_note": DEMO_NOTE})
    area = OperationalArea(
        id=area_id, **_names_from(a["names"]), river_names=a["river_names"], archetype=a["archetype"],
        crs_epsg=a["crs_epsg"], bbox=a["bbox"], center=Point(*a["center"]), utc_offset_min=a["utc_offset_min"],
        timezone="Asia/Almaty", clock_mode=a.get("clock_mode", "SIMULATION"), sim_now=start, data_version=1,
        is_demo=not hist, sort_order=a["sort_order"], config=config,
    )
    db.add(area)
    db.flush()

    for s in a["stations"]:
        db.add(HydroStation(id=s["id"], area_id=area_id, **_names_from(s["names"]), geom=Point(*s["lonlat"]),
                            river=s["river"], bankfull_stage_cm=s["bankfull"], watch_stage_cm=s["watch"],
                            warning_stage_cm=s["warning"], critical_stage_cm=s["critical"],
                            provider=s.get("provider", "simulation"), is_demo=not hist))
    for b in a["bases"]:
        db.add(Base_(id=b["id"], area_id=area_id, **_names_from(b["names"]), geom=Point(*b["lonlat"]), safe=b["safe"]))

    roads = _load(area_dir / "roads.geojson")
    embankments: dict[str, float] = {}  # DEMO road embankment heights (geometry attribute)
    for n in roads["nodes"]:
        db.add(RoadNode(id=f"{area_id}:{n['properties']['id']}", area_id=area_id, geom=shape(n["geometry"])))
    for f in roads["features"]:
        p = f["properties"]
        db.add(RoadSegment(
            id=p["id"], area_id=area_id, road_id=p["road_id"], road_class=p["road_class"],
            geom=shape(f["geometry"]), length_m=p["length_m"], speed_kmh=p["speed_kmh"],
            u_node=f"{area_id}:{p['u']}", v_node=f"{area_id}:{p['v']}", bridge_id=p["bridge_id"],
            source=p.get("source", src_default),
            **_names(p),
        ))
        embankments[p["id"]] = p["embankment_m"]
    for f in _load(area_dir / "bridges.geojson")["features"]:
        p = f["properties"]
        db.add(Bridge(id=p["id"], area_id=area_id, geom=shape(f["geometry"]), structure_type=p["structure_type"],
                      segment_ids=p["segment_ids"], deck_clearance_m=p["deck_clearance_m"], **_names(p)))
    for f in _load(area_dir / "bottlenecks.geojson")["features"]:
        p = f["properties"]
        db.add(Bottleneck(id=p["id"], area_id=area_id, kind=p["kind"], geom=shape(f["geometry"]),
                          segment_ids=p["segment_ids"], bridge_id=p.get("bridge_id"), notes=p.get("notes"), **_names(p)))
    for f in _load(area_dir / "buildings.geojson")["features"]:
        p = f["properties"]
        db.add(Building(id=p["id"], area_id=area_id, geom=shape(f["geometry"]), use=p["use"], floors=p["floors"],
                        height_m=p["height_m"], floor_area_m2=p["floor_area_m2"], sector_id=p["sector_id"],
                        source=p.get("source", src_default)[:255]))
    for f in _load(area_dir / "sectors.geojson")["features"]:
        p = f["properties"]
        db.add(Sector(id=f"{area_id}:{p['id']}", area_id=area_id, code=p["code"], geom=shape(f["geometry"]), **_names(p)))
    for f in _load(area_dir / "population_zones.geojson")["features"]:
        p = f["properties"]
        db.add(PopulationZone(id=p["id"], area_id=area_id, sector_id=p["sector_id"], geom=shape(f["geometry"]),
                              population=p["population"], vulnerable_share=p["vulnerable_share"], source=p["source"][:255],
                              mode="HISTORICAL" if hist else "SIMULATION"))
    for f in _load(area_dir / "facilities.geojson")["features"]:
        p = f["properties"]
        db.add(CriticalFacility(id=p["id"], area_id=area_id, facility_type=p["facility_type"], geom=shape(f["geometry"]),
                                criticality=p["criticality"], population_served=p["population_served"],
                                sector_id=p["sector_id"], source=p.get("source", "DEMO"),
                                verification=p.get("verification", "VERIFIED"), **_names(p)))
    for f in _load(area_dir / "task_sites.geojson")["features"]:
        p = f["properties"]
        db.add(TaskSite(id=p["id"], area_id=area_id, kind=p["kind"], geom=shape(f["geometry"]), sector_id=p["sector_id"],
                        protects=p["protects"], work_depth_limit_m=p["work_depth_limit_m"], **_names(p)))

    res_src = "SIMULATION" if hist else "DEMO"
    for r in _load(area_dir / "resources.json")["resources"]:
        db.add(Resource(id=r["id"], area_id=area_id, resource_type=r["type"], subtype=r["subtype"],
                        capacity=r["capacity"], capacity_unit=r["unit"], base_id=r["base"],
                        name_en=f"{r['id']} ({r['subtype'].replace('_', ' ').lower()})", source=res_src))
        db.add(ResourceStatus(resource_id=r["id"], status="AVAILABLE", source=res_src, updated_by="seed",
                              updated_at=start - timedelta(hours=3)))
    db.flush()

    # ---------------------------------------------------------------- scenario family (v1 = issuance)
    sc = _load(area_dir / "scenario.json")
    params = {"station_id": sc["station_id"], "issued_at": sc["issued_at"], "bankfull_cm": sc["bankfull_cm"],
              "series_step_min": sc["series_step_min"]}
    v1 = Scenario(
        id=f"{sc['family_id']}-v1", area_id=area_id, family_id=sc["family_id"], version=1,
        name=(f"{sc['name']} · v1" if sc.get("name") else
              f"Ensemble forecast {datetime.fromisoformat(sc['issued_at']):%d.%m %H:%M} · v1"),
        mode=sc.get("mode", "SIMULATION"),
        created_at=datetime.fromisoformat(sc["issued_at"]) + timedelta(minutes=10),
        reference_time=ref, source=sc.get("source", "DEMO synthetic ensemble (SIMULATION)"), provider=sc["provider"],
        provider_config={**sc["provider_config"], "bankfull_cm": sc["bankfull_cm"]},
        frame_offsets_min=sc["frame_offsets_min"],
        members=sc["members"], active_member_id=sc["issued_member"],
        selection={"method": "ISSUANCE_DEFAULT", "best_member": sc["issued_member"],
                   "note": "BASE member at exercise start" if hist else "Median member selected at forecast issuance"},
        parameters=params,
        uncertainty={"members": [m["id"] for m in sc["members"]], "envelope": [], "description":
                     ("LOW / BASE / HIGH sensitivity members (not probabilistic return periods)." if hist else
                      "Precomputed ensemble members (stage hydrograph variants).")},
        provenance={"note": sc["note"], "generator": "app.realdata.build" if hist else "app.demo.generator",
                    "mode": sc.get("mode", "SIMULATION"), "limitations": sc.get("limitations", [])},
        model_version=sc["model_version"], is_current=True, created_by="seed",
    )
    db.add(v1)
    db.flush()
    system = Actor.system()
    planner = Actor("planner", "PLANNER")
    commander = Actor("commander", "COMMANDER")
    record(db, system, "SCENARIO_GENERATED", "scenario", v1.id,
           f"Scenario v1 from ensemble issued {sc['issued_at']} (member {sc['issued_member']})",
           area_id=area_id, op_time=v1.created_at, details={"demo_seed": True})

    # ---------------------------------------------------------------- plans (authored against v1)
    plans = _load(area_dir / "plans.json")
    area.config = {**area.config, "embankments": embankments, "extra_candidates": plans.get("extra_candidates", [])}
    for p in plans["plans"]:
        t0 = start if hist else ref
        plan = Plan(id=p["id"], area_id=area_id, name=p["name"], description=p.get("description"), created_by="planner",
                    created_at=t0 - timedelta(hours=3, minutes=30))
        db.add(plan)
        db.flush()
        pv = PlanVersion(
            id=f"{p['id']}-v1", plan_id=p["id"], area_id=area_id, version=1, status="ACTIVE", origin="HUMAN",
            basis_scenario_id=v1.id, basis_data_version=1, policy=None, weights={}, constraints=[],
            change_summary={"note": p.get("note", "Initial human plan")}, created_by="planner",
            created_at=t0 - timedelta(hours=3, minutes=30), reviewed_by="planner", reviewed_at=t0 - timedelta(hours=3, minutes=10),
            approved_by="commander", approved_at=t0 - timedelta(hours=2, minutes=55),
            activated_at=t0 - timedelta(hours=2, minutes=50),
        )
        db.add(pv)
        db.flush()
        for i, t in enumerate(p["tasks"]):
            if t.get("depart_min") is not None:
                dep = ref + timedelta(minutes=float(t["depart_min"]))
            else:
                dep = datetime.fromisoformat(t["depart"]) if t.get("depart") else None
            db.add(PlanTask(id=new_id("pt-"), plan_version_id=pv.id, code=t["code"], template_id=t["template"],
                            site_id=t["site"], resource_ids=t["resources"], planned_departure=dep,
                            dependencies=t.get("depends", []), sort_order=t.get("sort", i)))
        db.flush()
        record(db, planner, "PLAN_CREATED", "plan_version", pv.id, f"{p['name']} v1 created (basis {v1.id})",
               area_id=area_id, op_time=pv.created_at, details={"demo_seed": True})
        record(db, planner, "PLAN_REVIEWED", "plan_version", pv.id, f"{p['name']} v1 reviewed", area_id=area_id,
               op_time=pv.reviewed_at, details={"demo_seed": True})
        record(db, commander, "PLAN_APPROVED", "plan_version", pv.id, f"{p['name']} v1 approved", area_id=area_id,
               op_time=pv.approved_at, details={"demo_seed": True})
        record(db, commander, "PLAN_ACTIVATED", "plan_version", pv.id, f"{p['name']} v1 activated", area_id=area_id,
               op_time=pv.activated_at, details={"demo_seed": True})

    # ---------------------------------------------------------------- observations → conflicts → conditioning
    for o in _load(area_dir / "observations.json")["observations"]:
        ob = Observation(id=new_id("ob-"), area_id=area_id, station_id=o["station_id"],
                         observed_at=datetime.fromisoformat(o["observed_at"]), water_level_cm=o["water_level_cm"],
                         source=o["source"][:255], source_type=o["source_type"], verification=o["verification"],
                         mode=o["mode"], entered_by="seed" if not hist else "import:official-curated",
                         quality=o.get("quality", "DEMO"), notes=o.get("notes"))
        db.add(ob)
        db.flush()
        conflicts = detect_conflicts(db, ob)
        if o["source_type"] == "FIELD":
            record(db, Actor("operator", "OPERATOR"), "OBSERVATION_ENTERED", "observation", ob.id,
                   f"{o['station_id']}: {o['water_level_cm']} cm (FIELD, {o['verification']})", area_id=area_id,
                   op_time=ob.observed_at + timedelta(minutes=2), details={"demo_seed": True})
        for c in conflicts:
            record(db, system, "DATA_CONFLICT_DETECTED", "data_conflict", c.id,
                   f"{o['station_id']}: Δ {c.difference:.0f} cm between hydropost and field reading", area_id=area_id,
                   op_time=ob.observed_at + timedelta(minutes=3), details={"demo_seed": True})
    db.flush()
    if hist:
        _seed_historical_tail(db, area, v1, plans, start, system)
        return
    condition_current(db, v1, ref - timedelta(minutes=5), system)
    newest = db.scalars(select(Scenario).where(Scenario.area_id == area_id).order_by(Scenario.version.desc())).first()
    if newest is not None and newest.id != v1.id:
        newest.created_at = ref - timedelta(minutes=5)

    # ---------------------------------------------------------------- data sources / freshness
    last_obs = max(datetime.fromisoformat(o["observed_at"]) for o in _load(area_dir / "observations.json")["observations"])
    layers = [
        ("hydrology", "simulation", "DEMO hydropost series", "SIMULATION", "OK", last_obs, False, 15),
        ("scenario", "synthetic_stage_hand", "DEMO synthetic ensemble", "SIMULATION", "OK",
         datetime.fromisoformat(sc["issued_at"]), False, 360),
        ("road_status", "field", "Field reports / manual road events", "SIMULATION", "OK", ref - timedelta(minutes=40), False, None),
        ("resources", "operational", "Operational resource register (DEMO)", "SIMULATION", "OK", ref - timedelta(minutes=25), False, None),
        ("terrain", "local_dem", "Synthetic DEM (DEMO)", "STATIC", "OK", None, False, None),
        ("buildings", "local_file", "Synthetic buildings (DEMO)", "STATIC", "OK", None, False, None),
        ("roads", "local_file", "Synthetic road network (DEMO)", "STATIC", "OK", None, False, None),
        ("population", "local_file", "Aggregated synthetic population (DEMO)", "STATIC", "OK", None, False, None),
        ("weather", "weather_api", "Weather provider (not configured)", "LIVE", "NOT_CONFIGURED", None, True, 30),
        ("rainfall", "nasa_imerg", "NASA IMERG (not configured)", "LIVE", "NOT_CONFIGURED", None, True, 60),
        ("sentinel1", "copernicus_s1", "Copernicus Sentinel-1 (not configured)", "HISTORICAL", "NOT_CONFIGURED", None, True, 720),
        ("glofas", "glofas", "Copernicus GloFAS (not configured)", "LIVE", "NOT_CONFIGURED", None, True, 1440),
        ("kazhydromet", "kazhydromet", "Kazhydromet hydropost feed (not configured)", "LIVE", "NOT_CONFIGURED", None, True, 15),
        ("osm", "openstreetmap", "OpenStreetMap extract (not configured)", "CACHED", "NOT_CONFIGURED", None, True, 10080),
    ]
    for layer, prov, source, mode, status, last, ext, sched in layers:
        db.add(ProviderStatus(id=f"{area_id}:{layer}", area_id=area_id, layer=layer, provider=prov, source=source,
                              mode=mode, status=status, quality="DEMO" if not ext else None, last_success_at=last,
                              last_attempt_at=last, schedule_min=sched, is_external=ext,
                              message=None if not ext else "Adapter contract available; credentials / endpoint not configured"))
    db.flush()


def resolve_profile() -> str:
    """'historical' when real-data packs are installed (or required), else 'demo'. Never silently synthetic
    when HISTORICAL was explicitly requested."""
    from app.realdata.install import AREAS, installed_areas

    want = (get_settings().data_profile or "auto").lower()
    if want == "demo":
        return "demo"
    have = installed_areas()
    if want == "historical":
        missing = [a for a in AREAS if a not in have]
        if missing:
            raise RuntimeError(f"ARGUS_DATA_PROFILE=historical but real-data packs are not installed for {missing}: "
                               "run `python -m app.cli install-realdata`")
        return "historical"
    return "historical" if set(have) == set(AREAS) else "demo"


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(OperationalArea)):
        return False
    profile = resolve_profile()
    seed_users(db)
    seed_library(db)
    if profile == "historical":
        from app.realdata.build import ensure_built

        dirs = [ensure_built(a) for a in ("atbasar", "kokshetau")]
    else:
        ensure_demo_files()
        demo = get_settings().demo_dir
        dirs = [demo / a for a in ("atbasar", "kokshetau")]
    for d in dirs:
        seed_area(db, d)
    db.commit()
    log.info("database seeded (profile=%s)", profile)
    return True


def _seed_historical_tail(db: Session, area: OperationalArea, v1: Scenario, plans: dict, start: datetime,
                          system: Actor) -> None:
    """Exercise injects (SIMULATION, audited) and provider statuses for a HISTORICAL real-data area."""
    from app.services.scenario.conditioning import select_member_manually

    area_id = area.id
    for inj in plans.get("injects", []):
        if inj.get("kind") == "SELECT_MEMBER":
            s2 = select_member_manually(db, v1, inj["member"], inj.get("note", "Exercise inject"),
                                        Actor("planner", "PLANNER"), lock=True)
            s2.created_at = start - timedelta(minutes=int(inj.get("minutes_before_start", 5)))
            record(db, Actor("planner", "PLANNER"), "EXERCISE_INJECT", "scenario", s2.id,
                   f"EXERCISE INJECT (SIMULATION): {inj.get('note', '')}", area_id=area_id, op_time=s2.created_at,
                   details={"inject": inj, "mode": "SIMULATION"})
    cfg = area.config or {}
    pack_date = datetime.fromisoformat("2026-10-01T15:48:00+00:00")
    rows = [
        ("scenario", "raster_manifest" if area_id == "atbasar" else "stage_hand_exercise",
         ("Atbasar 2024 hybrid terrain-susceptibility + stage proxy (real-data pack)" if area_id == "atbasar" else
          "Kylshakty stage–HAND exercise on real DEM (uncalibrated)"),
         "HISTORICAL" if area_id == "atbasar" else "SIMULATION", "OK", pack_date, False, None, "REAL_DATA_PACK"),
        ("terrain", "copernicus_dem", "Copernicus DEM GLO-30 (30 m DSM)", "HISTORICAL", "OK", pack_date, False, None, "PACK"),
        ("roads", "openstreetmap", "OpenStreetMap road graph (OSMnx, ODbL)", "CACHED", "OK", pack_date, False, None, "PACK"),
        ("buildings", "openstreetmap", "OpenStreetMap buildings (ODbL)", "CACHED", "OK", pack_date, False, None, "PACK"),
        ("population", "worldpop", "WorldPop 2024 100 m (modelled)", "HISTORICAL", "OK", pack_date, False, None, "MODELLED"),
        ("water_baseline", "jrc_gsw", "JRC Global Surface Water occurrence", "HISTORICAL", "OK", pack_date, False, None, "PACK"),
        ("hydrology", "official_reports", "Official public reports (gov.kz), curated", "HISTORICAL", "OK", pack_date, False, None,
         "OFFICIAL_REPORTED"),
        ("glofas_context", "open_meteo_glofas_archive", "Open-Meteo / GloFAS v4 — event-period context (pack)",
         "HISTORICAL", "OK", pack_date, False, None, "GLOBAL_MODEL"),
        ("weather_context", "open_meteo_archive", "Open-Meteo Historical Weather — event-period context (pack)",
         "HISTORICAL", "OK", pack_date, False, None, "REANALYSIS"),
        ("glofas", "open_meteo_glofas", "Open-Meteo Flood API (GloFAS v4) — live context", "LIVE", "NOT_POLLED", None, True, 60,
         "GLOBAL_MODEL"),
        ("weather", "open_meteo_forecast", "Open-Meteo Forecast API — live context", "LIVE", "NOT_POLLED", None, True, 60,
         "GLOBAL_MODEL"),
        ("kazhydromet", "kazhydromet", "Kazhydromet hydropost feed", "LIVE", "NOT_CONFIGURED", None, True, 15, None),
        ("tasqyn", "tasqyn", "Tasqyn flood forecast feed", "LIVE", "NOT_CONFIGURED", None, True, 60, None),
        ("road_status", "field", "Field reports / manual road events", "LIVE", "OK", None, False, None, None),
        ("resources", "operational", "Resource register (SIMULATION — no verified agency inventory)", "SIMULATION", "OK",
         start - timedelta(minutes=25), False, None, "SIMULATION"),
    ]
    if area_id == "atbasar":
        rows.insert(1, ("satellite", "sentinel2_l2a", "Sentinel-2 L2A (fallback — no Sentinel-1 acquisition for the event)",
                        "HISTORICAL", "OK", datetime.fromisoformat("2024-04-14T06:44:53+00:00"), False, None, "REQUIRES_QC"))
    msgs = {"kazhydromet": "No authorized stable endpoint supplied — use official reports / manual or file import",
            "tasqyn": "No authorized integration endpoint supplied — use manual or file import",
            "glofas": "Public API (no key). Polled on demand; GLOBAL_MODEL authority — never overrides local observations",
            "weather": "Public API (no key). Polled on demand; GLOBAL_MODEL context only"}
    for layer, prov, source, mode, st, last, ext, sched, quality in rows:
        db.add(ProviderStatus(id=f"{area_id}:{layer}", area_id=area_id, layer=layer, provider=prov, source=source, mode=mode,
                              status=st, quality=quality, last_success_at=last, last_attempt_at=last, schedule_min=sched,
                              is_external=ext, message=msgs.get(layer)))
    _ = cfg
    db.flush()
