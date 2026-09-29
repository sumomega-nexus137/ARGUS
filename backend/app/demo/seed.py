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
    ref = datetime.fromisoformat(a["reference_time"])
    area = OperationalArea(
        id=area_id, **_names_from(a["names"]), river_names=a["river_names"], archetype=a["archetype"],
        crs_epsg=a["crs_epsg"], bbox=a["bbox"], center=Point(*a["center"]), utc_offset_min=a["utc_offset_min"],
        timezone="Asia/Almaty", clock_mode="SIMULATION", sim_now=ref, data_version=1, is_demo=True,
        sort_order=a["sort_order"],
        config={"grid": a["grid"], "river_centerline": a["river_centerline"], "demo_note": DEMO_NOTE,
                "static_version": 1},
    )
    db.add(area)
    db.flush()

    for s in a["stations"]:
        db.add(HydroStation(id=s["id"], area_id=area_id, **_names_from(s["names"]), geom=Point(*s["lonlat"]),
                            river=s["river"], bankfull_stage_cm=s["bankfull"], watch_stage_cm=s["watch"],
                            warning_stage_cm=s["warning"], critical_stage_cm=s["critical"], provider="simulation",
                            is_demo=True))
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
            u_node=f"{area_id}:{p['u']}", v_node=f"{area_id}:{p['v']}", bridge_id=p["bridge_id"], source="DEMO",
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
                        height_m=p["height_m"], floor_area_m2=p["floor_area_m2"], sector_id=p["sector_id"], source="DEMO"))
    for f in _load(area_dir / "sectors.geojson")["features"]:
        p = f["properties"]
        db.add(Sector(id=f"{area_id}:{p['id']}", area_id=area_id, code=p["code"], geom=shape(f["geometry"]), **_names(p)))
    for f in _load(area_dir / "population_zones.geojson")["features"]:
        p = f["properties"]
        db.add(PopulationZone(id=p["id"], area_id=area_id, sector_id=p["sector_id"], geom=shape(f["geometry"]),
                              population=p["population"], vulnerable_share=p["vulnerable_share"], source=p["source"]))
    for f in _load(area_dir / "facilities.geojson")["features"]:
        p = f["properties"]
        db.add(CriticalFacility(id=p["id"], area_id=area_id, facility_type=p["facility_type"], geom=shape(f["geometry"]),
                                criticality=p["criticality"], population_served=p["population_served"],
                                sector_id=p["sector_id"], source="DEMO", verification="VERIFIED", **_names(p)))
    for f in _load(area_dir / "task_sites.geojson")["features"]:
        p = f["properties"]
        db.add(TaskSite(id=p["id"], area_id=area_id, kind=p["kind"], geom=shape(f["geometry"]), sector_id=p["sector_id"],
                        protects=p["protects"], work_depth_limit_m=p["work_depth_limit_m"], **_names(p)))

    for r in _load(area_dir / "resources.json")["resources"]:
        db.add(Resource(id=r["id"], area_id=area_id, resource_type=r["type"], subtype=r["subtype"],
                        capacity=r["capacity"], capacity_unit=r["unit"], base_id=r["base"],
                        name_en=f"{r['id']} ({r['subtype'].replace('_', ' ').lower()})", source="DEMO"))
        db.add(ResourceStatus(resource_id=r["id"], status="AVAILABLE", source="DEMO", updated_by="seed",
                              updated_at=ref - timedelta(hours=3)))
    db.flush()

    # ---------------------------------------------------------------- scenario family (v1 = issuance)
    sc = _load(area_dir / "scenario.json")
    params = {"station_id": sc["station_id"], "issued_at": sc["issued_at"], "bankfull_cm": sc["bankfull_cm"],
              "series_step_min": sc["series_step_min"]}
    v1 = Scenario(
        id=f"{sc['family_id']}-v1", area_id=area_id, family_id=sc["family_id"], version=1,
        name=f"Ensemble forecast {datetime.fromisoformat(sc['issued_at']):%d.%m %H:%M} · v1", mode="SIMULATION",
        created_at=datetime.fromisoformat(sc["issued_at"]) + timedelta(minutes=10),
        reference_time=ref, source="DEMO synthetic ensemble (SIMULATION)", provider=sc["provider"],
        provider_config={**sc["provider_config"], "bankfull_cm": sc["bankfull_cm"]},
        frame_offsets_min=sc["frame_offsets_min"],
        members=sc["members"], active_member_id=sc["issued_member"],
        selection={"method": "ISSUANCE_DEFAULT", "best_member": sc["issued_member"],
                   "note": "Median member selected at forecast issuance"},
        parameters=params,
        uncertainty={"members": [m["id"] for m in sc["members"]], "envelope": [], "description":
                     "Precomputed ensemble members (stage hydrograph variants)."},
        provenance={"note": sc["note"], "generator": "app.demo.generator", "mode": "SIMULATION"},
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
        plan = Plan(id=p["id"], area_id=area_id, name=p["name"], description=p.get("description"), created_by="planner",
                    created_at=ref - timedelta(hours=3, minutes=30))
        db.add(plan)
        db.flush()
        pv = PlanVersion(
            id=f"{p['id']}-v1", plan_id=p["id"], area_id=area_id, version=1, status="ACTIVE", origin="HUMAN",
            basis_scenario_id=v1.id, basis_data_version=1, policy=None, weights={}, constraints=[],
            change_summary={"note": "Initial human plan"}, created_by="planner",
            created_at=ref - timedelta(hours=3, minutes=30), reviewed_by="planner", reviewed_at=ref - timedelta(hours=3, minutes=10),
            approved_by="commander", approved_at=ref - timedelta(hours=2, minutes=55),
            activated_at=ref - timedelta(hours=2, minutes=50),
        )
        db.add(pv)
        db.flush()
        for t in p["tasks"]:
            db.add(PlanTask(id=new_id("pt-"), plan_version_id=pv.id, code=t["code"], template_id=t["template"],
                            site_id=t["site"], resource_ids=t["resources"],
                            planned_departure=datetime.fromisoformat(t["depart"]) if t.get("depart") else None,
                            dependencies=t.get("depends", []), sort_order=t["sort"]))
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
                         source=o["source"], source_type=o["source_type"], verification=o["verification"],
                         mode=o["mode"], entered_by="seed", quality="DEMO")
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
        ("resources", "operational", "Operational resource register (DEMO)", "SIMULATION", "OK", ref - timedelta(hours=3), False, None),
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


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(OperationalArea)):
        return False
    ensure_demo_files()
    seed_users(db)
    seed_library(db)
    demo = get_settings().demo_dir
    for area_id in ("atbasar", "kokshetau"):
        seed_area(db, demo / area_id)
    db.commit()
    log.info("demo database seeded")
    return True
