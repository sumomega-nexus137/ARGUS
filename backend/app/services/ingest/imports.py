"""Import workflow: UPLOAD → PREVIEW → VALIDATE → SHOW ERRORS → CONFIRM → IMPORT.

Invalid rows are never silently accepted: they are listed with errors and excluded at confirmation.
Supported: CSV, XLSX, JSON (array of objects), GeoJSON (FeatureCollection; geometry → lon/lat).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ArgusError, Conflict
from app.db.base import new_id
from app.models import Base_, HydroStation, ImportJob, OperationalArea, Resource, RoadSegment
from app.services.audit import Actor, record

IMPORT_TYPES = ("resources", "facilities", "observations", "road_events")
MAX_ROWS = 5000

TEMPLATES = {
    "resources": ["id", "resource_type", "subtype", "capacity", "capacity_unit", "base_id", "name_kk", "name_ru", "name_en",
                  "status"],
    "facilities": ["id", "facility_type", "name_kk", "name_ru", "name_en", "lon", "lat", "criticality", "population_served",
                   "sector_id", "verification", "source"],
    "observations": ["station_id", "observed_at", "water_level_cm", "discharge_m3s", "source", "source_type",
                     "verification", "notes"],
    "road_events": ["road_id", "segment_ids", "state", "effective_from", "effective_until", "source", "verification",
                    "notes"],
}


def parse_file(filename: str, content: bytes) -> tuple[str, list[dict[str, Any]]]:
    name = filename.lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        sample = text[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return "CSV", [dict(r) for r in csv.DictReader(io.StringIO(text), dialect=dialect)]
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return "XLSX", []
        header = [str(h).strip() if h is not None else "" for h in rows[0]]
        return "XLSX", [{header[i]: v for i, v in enumerate(r) if i < len(header) and header[i]} for r in rows[1:]
                        if any(v is not None and str(v).strip() for v in r)]
    if name.endswith(".geojson") or name.endswith(".json"):
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            out = []
            for f in data.get("features", []):
                props = dict(f.get("properties") or {})
                g = f.get("geometry") or {}
                if g.get("type") == "Point":
                    props.setdefault("lon", g["coordinates"][0])
                    props.setdefault("lat", g["coordinates"][1])
                out.append(props)
            return "GEOJSON", out
        if isinstance(data, list):
            return "JSON", [dict(x) for x in data]
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return "JSON", [dict(x) for x in data["rows"]]
        raise ArgusError("unsupported_json", "JSON must be an array of objects or a GeoJSON FeatureCollection")
    raise ArgusError("unsupported_format", "Supported formats: CSV, XLSX, JSON, GeoJSON")


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _f(v: Any, errors: list[str], field: str, required: bool = False) -> float | None:
    s = _s(v)
    if s is None:
        if required:
            errors.append(f"missing:{field}")
        return None
    try:
        x = float(s.replace(",", "."))
    except ValueError:
        errors.append(f"not_a_number:{field}")
        return None
    if x != x or x in (float("inf"), float("-inf")):
        errors.append(f"not_a_number:{field}")
        return None
    return x


def _dt(v: Any, errors: list[str], field: str, required: bool = False) -> str | None:
    if isinstance(v, datetime):
        if v.tzinfo is None:
            errors.append(f"timestamp_without_timezone:{field}")
            return None
        return v.isoformat()
    s = _s(v)
    if s is None:
        if required:
            errors.append(f"missing:{field}")
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"invalid_timestamp:{field}")
        return None
    if d.tzinfo is None:
        errors.append(f"timestamp_without_timezone:{field}")
        return None
    return d.isoformat()


def validate_row(db: Session, area: OperationalArea, kind: str, raw: dict, seen: set) -> tuple[dict, list[str], list[str]]:
    e: list[str] = []
    w: list[str] = []
    r = {k.strip().lower() if isinstance(k, str) else k: v for k, v in raw.items()}
    if kind == "resources":
        rid = _s(r.get("id"))
        rtype = (_s(r.get("resource_type")) or "").upper()
        if not rid:
            e.append("missing:id")
        if rtype not in ("CREW", "PUMP", "VEHICLE", "EQUIPMENT", "OTHER"):
            e.append("invalid:resource_type")
        cap = _f(r.get("capacity"), e, "capacity")
        base = _s(r.get("base_id"))
        if base and db.get(Base_, base) is None:
            e.append("unknown:base_id")
        status = (_s(r.get("status")) or "AVAILABLE").upper()
        if status not in ("AVAILABLE", "UNAVAILABLE", "FAILED"):
            e.append("invalid:status")
        if rid and rid in seen:
            e.append("duplicate_in_file:id")
        if rid:
            existing = db.get(Resource, rid)
            if existing is not None and existing.area_id != area.id:
                e.append("id_used_in_other_area")
            elif existing is not None:
                w.append("will_update_existing")
            seen.add(rid)
        data = {"id": rid, "resource_type": rtype, "subtype": (_s(r.get("subtype")) or "GENERIC").upper(), "capacity": cap,
                "capacity_unit": _s(r.get("capacity_unit")), "base_id": base, "name_kk": _s(r.get("name_kk")),
                "name_ru": _s(r.get("name_ru")), "name_en": _s(r.get("name_en")), "status": status, "source": "IMPORT"}
    elif kind == "facilities":
        ftype = (_s(r.get("facility_type")) or "").upper()
        from app.services.operations.inputs import FACILITY_TYPES

        if ftype not in FACILITY_TYPES:
            e.append("invalid:facility_type")
        lon = _f(r.get("lon"), e, "lon", required=True)
        lat = _f(r.get("lat"), e, "lat", required=True)
        if lon is not None and lat is not None and not (area.bbox[0] <= lon <= area.bbox[2] and area.bbox[1] <= lat <= area.bbox[3]):
            e.append("outside_area")
        crit = _f(r.get("criticality"), e, "criticality")
        if crit is not None and not 0 <= crit <= 100:
            e.append("out_of_range:criticality")
        if not any(_s(r.get(k)) for k in ("name_kk", "name_ru", "name_en", "name_original", "name")):
            e.append("missing:name")
        ver = (_s(r.get("verification")) or "UNVERIFIED").upper()
        if ver not in ("VERIFIED", "UNVERIFIED"):
            e.append("invalid:verification")
        fid = _s(r.get("id"))
        if fid and fid in seen:
            e.append("duplicate_in_file:id")
        if fid:
            seen.add(fid)
        data = {"id": fid, "facility_type": ftype, "lon": lon, "lat": lat, "criticality": int(crit) if crit is not None else 50,
                "population_served": int(_f(r.get("population_served"), e, "population_served") or 0),
                "sector_id": _s(r.get("sector_id")), "verification": ver, "source": _s(r.get("source")) or "IMPORT",
                "name_kk": _s(r.get("name_kk")), "name_ru": _s(r.get("name_ru")), "name_en": _s(r.get("name_en")),
                "name_original": _s(r.get("name_original")) or _s(r.get("name"))}
    elif kind == "observations":
        st = _s(r.get("station_id"))
        station = db.get(HydroStation, st) if st else None
        if station is None or station.area_id != area.id:
            e.append("unknown:station_id")
        ts = _dt(r.get("observed_at"), e, "observed_at", required=True)
        lvl = _f(r.get("water_level_cm"), e, "water_level_cm", required=True)
        if lvl is not None and not -100 <= lvl <= 3000:
            e.append("out_of_range:water_level_cm")
        q = _f(r.get("discharge_m3s"), e, "discharge_m3s")
        stype = (_s(r.get("source_type")) or "").upper()
        if stype not in ("FIELD", "HYDROPOST", "FORECAST", "SATELLITE", "GLOBAL_MODEL", "SIMULATION"):
            e.append("invalid:source_type")
        ver = (_s(r.get("verification")) or "UNVERIFIED").upper()
        if ver not in ("VERIFIED", "UNVERIFIED", "REJECTED"):
            e.append("invalid:verification")
        src = _s(r.get("source"))
        if not src:
            e.append("missing:source")
        key = (st, ts, src, lvl)
        if key in seen:
            e.append("duplicate_in_file")
        seen.add(key)
        data = {"station_id": st, "observed_at": ts, "water_level_cm": lvl, "discharge_m3s": q, "source": src,
                "source_type": stype, "verification": ver, "notes": _s(r.get("notes"))}
    elif kind == "road_events":
        rid = _s(r.get("road_id"))
        segs_all = set(db.scalars(select(RoadSegment.id).where(RoadSegment.area_id == area.id, RoadSegment.road_id == rid))) if rid else set()
        if not segs_all:
            e.append("unknown:road_id")
        segs_raw = r.get("segment_ids")
        segs = [x.strip() for x in segs_raw.replace(",", ";").split(";") if x.strip()] if isinstance(segs_raw, str) else list(segs_raw or [])
        if any(s not in segs_all for s in segs):
            e.append("unknown:segment_ids")
        state = (_s(r.get("state")) or "").upper()
        if state not in ("OPEN", "RESTRICTED", "CLOSED"):
            e.append("invalid:state")
        ver = (_s(r.get("verification")) or "UNVERIFIED").upper()
        if ver not in ("VERIFIED", "UNVERIFIED"):
            e.append("invalid:verification")
        data = {"road_id": rid, "segment_ids": segs, "state": state,
                "effective_from": _dt(r.get("effective_from"), e, "effective_from"),
                "effective_until": _dt(r.get("effective_until"), e, "effective_until"),
                "source": _s(r.get("source")) or "IMPORT", "verification": ver, "notes": _s(r.get("notes"))}
        if not data["effective_from"]:
            w.append("effective_from_defaults_to_now")
    else:
        raise ArgusError("invalid_import_type")
    return data, e, w


def create_preview(db: Session, area: OperationalArea, kind: str, filename: str, content: bytes, actor: Actor) -> ImportJob:
    if kind not in IMPORT_TYPES:
        raise ArgusError("invalid_import_type", f"Import type must be one of {IMPORT_TYPES}")
    fmt, rows = parse_file(filename, content)
    if len(rows) > MAX_ROWS:
        raise ArgusError("too_many_rows", f"Maximum {MAX_ROWS} rows per import", max=MAX_ROWS)
    seen: set = set()
    out, nv, ni, nw = [], 0, 0, 0
    for i, raw in enumerate(rows, start=1):
        data, errs, warns = validate_row(db, area, kind, raw, seen)
        status = "INVALID" if errs else ("WARNING" if warns else "VALID")
        nv += status != "INVALID"
        ni += status == "INVALID"
        nw += status == "WARNING"
        out.append({"row": i, "status": status, "errors": errs, "warnings": warns, "data": data,
                    "raw": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in raw.items()}})
    job = ImportJob(id=new_id("imp-"), area_id=area.id, import_type=kind, filename=filename, file_format=fmt,
                    status="PREVIEW", created_by=actor.username, rows_total=len(rows), rows_valid=nv, rows_invalid=ni,
                    rows_warning=nw, preview={"rows": out, "columns": list(rows[0].keys()) if rows else [],
                                              "template": TEMPLATES[kind]})
    db.add(job)
    db.flush()
    record(db, actor, "IMPORT_PREVIEWED", "import", job.id, f"{kind} from {filename}: {nv} valid, {ni} invalid",
           area_id=area.id)
    return job


def confirm(db: Session, job: ImportJob, actor: Actor) -> ImportJob:
    from app.services.ingest.observations import ObservationInput, add_observation
    from app.services.operations.inputs import add_facility, add_road_event, upsert_resource

    if job.status != "PREVIEW":
        raise Conflict("import_not_in_preview", "Import already confirmed or cancelled")
    applied, failed = 0, []
    for row in job.preview.get("rows", []):
        if row["status"] == "INVALID":
            continue
        d = row["data"]
        try:
            with db.begin_nested():
                if job.import_type == "resources":
                    upsert_resource(db, job.area_id, d, actor, import_id=job.id)
                elif job.import_type == "facilities":
                    add_facility(db, job.area_id, d, actor, import_id=job.id)
                elif job.import_type == "observations":
                    add_observation(db, job.area_id, ObservationInput(
                        station_id=d["station_id"], observed_at=datetime.fromisoformat(d["observed_at"]),
                        water_level_cm=d["water_level_cm"], discharge_m3s=d["discharge_m3s"], source=d["source"],
                        source_type=d["source_type"], verification=d["verification"], notes=d.get("notes"),
                        mode="LIVE", import_id=job.id), actor)
                elif job.import_type == "road_events":
                    add_road_event(db, job.area_id, road_id=d["road_id"], segment_ids=d["segment_ids"], state=d["state"],
                                   effective_from=datetime.fromisoformat(d["effective_from"]) if d["effective_from"] else None,
                                   effective_until=datetime.fromisoformat(d["effective_until"]) if d["effective_until"] else None,
                                   source=d["source"], verification=d["verification"], notes=d.get("notes"), actor=actor,
                                   import_id=job.id)
            applied += 1
        except ArgusError as exc:
            failed.append({"row": row["row"], "error": exc.code, "message": exc.message})
    job.status = "CONFIRMED"
    job.applied_count = applied
    from app.services.audit import operational_now

    job.confirmed_at = operational_now(db, job.area_id)
    job.message = json.dumps({"failed_on_apply": failed}) if failed else None
    record(db, actor, "IMPORT_CONFIRMED", "import", job.id,
           f"{job.import_type}: {applied} rows imported, {job.rows_invalid} rejected, {len(failed)} failed on apply",
           area_id=job.area_id, details={"failed": failed})
    return job


def template_csv(kind: str) -> str:
    if kind not in TEMPLATES:
        raise ArgusError("invalid_import_type")
    return ",".join(TEMPLATES[kind]) + "\n"
