"""AreaContext — in-memory, engine-ready view of an operational area.

Static layers (roads, buildings, facilities, zones…) are cached per ``static_version``; dynamic
layers (resources, road events, action library) are loaded fresh for every computation.
Engines never touch the ORM directly: they consume this context.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import (
    ApprovedAction,
    Base_,
    Bottleneck,
    Bridge,
    Building,
    CriticalFacility,
    HydroStation,
    OperationalArea,
    PopulationZone,
    Resource,
    ResourceStatus,
    RoadEvent,
    RoadNode,
    RoadSegment,
    Sector,
    TaskSite,
)

ACCESS_LINK_SPEED_KMH = 20.0


def short(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def names_of(obj) -> dict:  # type: ignore[no-untyped-def]
    return {"kk": obj.name_kk, "ru": obj.name_ru, "en": obj.name_en, "original": obj.name_original}


@dataclass
class NodeInfo:
    id: str
    lon: float
    lat: float
    x: float
    y: float


@dataclass
class SegmentInfo:
    id: str
    road_id: str
    u: str
    v: str
    length_m: float
    speed_kmh: float
    road_class: str
    bridge_id: str | None
    embankment_m: float
    coords: list[list[float]]
    sample_x: np.ndarray
    sample_y: np.ndarray
    names: dict


@dataclass
class RoadInfo:
    id: str
    names: dict
    segment_ids: list[str]
    road_class: str


@dataclass
class PointFeature:
    id: str
    kind: str
    names: dict
    lon: float
    lat: float
    x: float
    y: float
    node: str
    access_min: float
    sector: str | None = None
    attrs: dict = field(default_factory=dict)


@dataclass
class SectorInfo:
    code: str
    names: dict
    geom: BaseGeometry
    nodes: list[str]


@dataclass
class ZoneInfo:
    id: str
    sector: str | None
    population: int
    vulnerable_share: float
    geom: BaseGeometry
    residential_idx: np.ndarray


@dataclass
class BuildingArrays:
    ids: list[str]
    x: np.ndarray
    y: np.ndarray
    use: np.ndarray
    floor_area: np.ndarray
    sector: list[str | None]


@dataclass
class ResourceInfo:
    id: str
    type: str
    subtype: str
    base: str | None
    capacity: float | None
    unit: str | None
    status: str
    delay_min: int
    available_from: datetime | None
    names: dict
    note: str | None = None


@dataclass
class ActionTemplate:
    id: str
    action_type: str
    names: dict
    description: dict
    requirements: dict
    setup_min: int
    execution_min: int
    safety_buffer_min: int
    equipment_release: str
    site_kinds: list[str]
    constraints: dict
    prerequisites: list

    @property
    def pumps(self) -> int:
        return int(self.requirements.get("pumps", 0) or 0)

    @property
    def work_min(self) -> int:
        return self.setup_min + self.execution_min

    @property
    def requires_egress(self) -> bool:
        return bool(self.constraints.get("requires_egress", True))


@dataclass
class StaticContext:
    area_id: str
    names: dict
    crs_epsg: int
    utc_offset_min: int
    config: dict
    nodes: dict[str, NodeInfo]
    segments: dict[str, SegmentInfo]
    roads: dict[str, RoadInfo]
    adjacency: dict[str, list[tuple[str, str]]]
    bridges: dict[str, dict]
    bottlenecks: dict[str, dict]
    facilities: dict[str, PointFeature]
    sites: dict[str, PointFeature]
    bases: dict[str, PointFeature]
    stations: dict[str, dict]
    sectors: dict[str, SectorInfo]
    zones: list[ZoneInfo]
    buildings: BuildingArrays
    static_version: int


@dataclass
class AreaContext:
    static: StaticContext
    data_version: int
    resources: dict[str, ResourceInfo]
    templates: dict[str, ActionTemplate]
    road_events: list[RoadEvent]
    now: datetime

    def __getattr__(self, item):  # type: ignore[no-untyped-def]
        return getattr(self.static, item)


_cache: dict[tuple[str, int], StaticContext] = {}
_lock = threading.Lock()


def _nearest_node(nodes: dict[str, NodeInfo], x: float, y: float) -> tuple[str, float]:
    best, bd = "", float("inf")
    for n in nodes.values():
        d = (n.x - x) ** 2 + (n.y - y) ** 2
        if d < bd:
            best, bd = n.id, d
    return best, float(np.sqrt(bd))


def _build_static(db: Session, area: OperationalArea) -> StaticContext:
    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{area.crs_epsg}", always_xy=True)

    def proj(lon: float, lat: float) -> tuple[float, float]:
        x, y = tr.transform(lon, lat)
        return float(x), float(y)

    nodes: dict[str, NodeInfo] = {}
    for n in db.scalars(select(RoadNode).where(RoadNode.area_id == area.id)):
        x, y = proj(n.geom.x, n.geom.y)
        nodes[short(n.id)] = NodeInfo(short(n.id), n.geom.x, n.geom.y, x, y)

    emb = (area.config or {}).get("embankments", {})
    segments: dict[str, SegmentInfo] = {}
    roads: dict[str, RoadInfo] = {}
    adjacency: dict[str, list[tuple[str, str]]] = {k: [] for k in nodes}
    for s in db.scalars(select(RoadSegment).where(RoadSegment.area_id == area.id).order_by(RoadSegment.id)):
        coords = [list(c) for c in s.geom.coords]
        xy = np.array([proj(c[0], c[1]) for c in coords])
        n_samples = max(2, int(s.length_m / 25.0) + 1)
        seg_len = np.r_[0, np.cumsum(np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1])))]
        d = np.linspace(0, seg_len[-1], n_samples)
        sx = np.interp(d, seg_len, xy[:, 0])
        sy = np.interp(d, seg_len, xy[:, 1])
        u, v = short(s.u_node), short(s.v_node)
        segments[s.id] = SegmentInfo(s.id, s.road_id, u, v, s.length_m, s.speed_kmh, s.road_class, s.bridge_id,
                                     float(emb.get(s.id, 0.3)), coords, sx, sy, names_of(s))
        adjacency.setdefault(u, []).append((s.id, v))
        adjacency.setdefault(v, []).append((s.id, u))
        r = roads.setdefault(s.road_id, RoadInfo(s.road_id, names_of(s), [], s.road_class))
        r.segment_ids.append(s.id)

    def point_feature(fid: str, kind: str, names: dict, geom, sector=None, attrs=None) -> PointFeature:  # type: ignore[no-untyped-def]
        x, y = proj(geom.x, geom.y)
        node, dist = _nearest_node(nodes, x, y)
        return PointFeature(fid, kind, names, geom.x, geom.y, x, y, node, dist / 1000 / ACCESS_LINK_SPEED_KMH * 60,
                            sector, attrs or {})

    bridges = {b.id: {"id": b.id, "names": names_of(b), "segment_ids": b.segment_ids, "clearance": b.deck_clearance_m,
                      "lon": b.geom.x, "lat": b.geom.y, "structure_type": b.structure_type}
               for b in db.scalars(select(Bridge).where(Bridge.area_id == area.id))}
    bottlenecks = {b.id: {"id": b.id, "names": names_of(b), "kind": b.kind, "segment_ids": b.segment_ids,
                          "bridge_id": b.bridge_id, "lon": b.geom.x, "lat": b.geom.y, "notes": b.notes}
                   for b in db.scalars(select(Bottleneck).where(Bottleneck.area_id == area.id))}
    facilities = {
        f.id: point_feature(f.id, f.facility_type, names_of(f), f.geom, f.sector_id,
                            {"criticality": f.criticality, "population_served": f.population_served,
                             "verification": f.verification, "source": f.source})
        for f in db.scalars(select(CriticalFacility).where(CriticalFacility.area_id == area.id))
    }
    sites = {
        t.id: point_feature(t.id, t.kind, names_of(t), t.geom, t.sector_id,
                            {"protects": t.protects or {}, "work_limit": t.work_depth_limit_m,
                             "explicit_deadline": t.explicit_deadline, "is_candidate": t.is_candidate})
        for t in db.scalars(select(TaskSite).where(TaskSite.area_id == area.id))
    }
    bases = {b.id: point_feature(b.id, "BASE", names_of(b), b.geom, None, {"safe": b.safe})
             for b in db.scalars(select(Base_).where(Base_.area_id == area.id))}
    stations = {s.id: {"id": s.id, "names": names_of(s), "lon": s.geom.x, "lat": s.geom.y,
                       "bankfull": s.bankfull_stage_cm, "watch": s.watch_stage_cm, "warning": s.warning_stage_cm,
                       "critical": s.critical_stage_cm, "river": s.river, "provider": s.provider}
                for s in db.scalars(select(HydroStation).where(HydroStation.area_id == area.id))}

    sectors: dict[str, SectorInfo] = {}
    for s in db.scalars(select(Sector).where(Sector.area_id == area.id)):
        pg = prep(s.geom)
        inside = [n.id for n in nodes.values() if pg.contains(Point(n.lon, n.lat))]
        if not inside:
            c = s.geom.centroid
            x, y = proj(c.x, c.y)
            inside = [_nearest_node(nodes, x, y)[0]]
        sectors[s.code] = SectorInfo(s.code, names_of(s), s.geom, inside)

    blds = list(db.scalars(select(Building).where(Building.area_id == area.id).order_by(Building.id)))
    cents = [b.geom.centroid for b in blds]
    bx, by = tr.transform(np.array([c.x for c in cents]), np.array([c.y for c in cents])) if cents else ([], [])
    buildings = BuildingArrays(
        ids=[b.id for b in blds], x=np.asarray(bx, dtype=float), y=np.asarray(by, dtype=float),
        use=np.array([b.use for b in blds]), floor_area=np.array([b.floor_area_m2 for b in blds], dtype=float),
        sector=[b.sector_id for b in blds],
    )
    res_mask = buildings.use == "residential"
    zones: list[ZoneInfo] = []
    from shapely import points as shp_points
    from shapely.strtree import STRtree

    cent_pts = shp_points([c.x for c in cents], [c.y for c in cents]) if cents else []
    tree = STRtree(cent_pts) if cents else None
    for z in db.scalars(select(PopulationZone).where(PopulationZone.area_id == area.id)):
        idx = np.array(tree.query(z.geom, predicate="contains"), dtype=int) if tree is not None else np.array([], dtype=int)
        idx = idx[res_mask[idx]] if idx.size else idx
        zones.append(ZoneInfo(z.id, z.sector_id, z.population, z.vulnerable_share, z.geom, idx))

    return StaticContext(
        area_id=area.id, names=names_of(area), crs_epsg=area.crs_epsg, utc_offset_min=area.utc_offset_min,
        config=area.config or {}, nodes=nodes, segments=segments, roads=roads, adjacency=adjacency, bridges=bridges,
        bottlenecks=bottlenecks, facilities=facilities, sites=sites, bases=bases, stations=stations, sectors=sectors,
        zones=zones, buildings=buildings, static_version=int((area.config or {}).get("static_version", 1)),
    )


def invalidate_static(area_id: str) -> None:
    with _lock:
        for k in [k for k in _cache if k[0] == area_id]:
            _cache.pop(k, None)


def load_static(db: Session, area: OperationalArea) -> StaticContext:
    key = (area.id, int((area.config or {}).get("static_version", 1)))
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    st = _build_static(db, area)
    with _lock:
        _cache[key] = st
    return st


def load_templates(db: Session, area_id: str) -> dict[str, ActionTemplate]:
    q = select(ApprovedAction).where(ApprovedAction.active.is_(True))
    out = {}
    for a in db.scalars(q):
        if a.area_id not in (None, area_id):
            continue
        out[a.id] = ActionTemplate(a.id, a.action_type, names_of(a), a.description or {}, a.requirements or {},
                                   a.setup_min, a.execution_min, a.safety_buffer_min, a.equipment_release,
                                   a.site_kinds or [], a.constraints or {}, a.prerequisites or [])
    return out


def load_resources(db: Session, area_id: str) -> dict[str, ResourceInfo]:
    rows = db.execute(
        select(Resource, ResourceStatus).join(ResourceStatus, ResourceStatus.resource_id == Resource.id, isouter=True)
        .where(Resource.area_id == area_id).order_by(Resource.id)
    ).all()
    out = {}
    for r, st in rows:
        out[r.id] = ResourceInfo(
            r.id, r.resource_type, r.subtype, r.base_id, r.capacity, r.capacity_unit,
            st.status if st else "AVAILABLE", st.delay_min if st else 0, st.available_from if st else None,
            names_of(r), st.note if st else None,
        )
    return out


def load_context(db: Session, area_id: str) -> AreaContext:
    from app.services.clock import area_now

    area = db.get(OperationalArea, area_id)
    if area is None:
        raise NotFound("operational area", area_id)
    st = load_static(db, area)
    events = list(db.scalars(select(RoadEvent).where(RoadEvent.area_id == area_id, RoadEvent.active.is_(True))
                             .order_by(RoadEvent.effective_from)))
    return AreaContext(static=st, data_version=area.data_version, resources=load_resources(db, area_id),
                       templates=load_templates(db, area_id), road_events=events, now=area_now(area))
