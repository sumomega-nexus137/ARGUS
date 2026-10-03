"""Import workflow: UPLOAD → PREVIEW → VALIDATE → SHOW ERRORS → CONFIRM → IMPORT.

Invalid rows are never silently accepted: they are listed with errors and excluded at confirmation.
Supported: CSV, XLSX, JSON (array of objects), GeoJSON (FeatureCollection; geometry → lon/lat).
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ArgusError, Conflict
from app.db.base import new_id
from app.models import Base_, HydroStation, ImportJob, OperationalArea, Resource, RoadSegment
from app.services.audit import Actor, record

IMPORT_TYPES = ("resources", "facilities", "observations", "road_events")
MAX_ROWS = 5000
REQUIRED = {
    "resources": ["id", "resource_type"],
    "facilities": ["facility_type", "lon", "lat"],
    "observations": ["station_id", "observed_at", "water_level_cm", "source", "source_type"],
    "road_events": ["road_id", "state"],
}
OPTIONAL_EXTRA = {"utc_offset", "name", "name_original"}

TEMPLATES = {
    "resources": ["id", "resource_type", "subtype", "capacity", "capacity_unit", "base_id", "name_kk", "name_ru", "name_en",
                  "status"],
    "facilities": ["id", "facility_type", "name_kk", "name_ru", "name_en", "lon", "lat", "criticality", "population_served",
                   "sector_id", "verification", "source"],
    "observations": ["station_id", "observed_at", "utc_offset", "water_level_cm", "discharge_m3s", "source", "source_type",
                     "verification", "notes"],
    "road_events": ["road_id", "segment_ids", "state", "effective_from", "effective_until", "utc_offset", "source",
                    "verification", "notes"],
}


def _decode(content: bytes) -> str:
    """UTF-8 (with or without BOM) first; Excel on Russian/Kazakh Windows saves CSV as cp1251."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1251")


def _delimiter(text: str) -> str:
    """The header line decides: Excel in ru/kk locales writes ';', others ',' or tab."""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    counts = {d: first.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def _blank(row: dict) -> bool:
    return not any(v is not None and str(v).strip() for k, v in row.items() if k is not None)


def _parse(filename: str, content: bytes) -> tuple[str, list[dict[str, Any]]]:
    name = filename.lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = _decode(content)
        reader = csv.DictReader(io.StringIO(text), delimiter=_delimiter(text))
        rows = [{(k.strip().lstrip("\ufeff") if isinstance(k, str) else k): v for k, v in r.items()} for r in reader]
        return "CSV", [r for r in rows if not _blank(r)]
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
        data = json.loads(_decode(content))
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            out = []
            for f in data.get("features") or []:
                if not isinstance(f, dict):
                    continue
                props = dict(f.get("properties") or {})
                g = f.get("geometry") or {}
                coords = g.get("coordinates") if isinstance(g, dict) else None
                if isinstance(g, dict) and g.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
                    props.setdefault("lon", coords[0])
                    props.setdefault("lat", coords[1])
                out.append(props)
            return "GEOJSON", out
        items = data if isinstance(data, list) else data.get("rows") if isinstance(data, dict) else None
        if isinstance(items, list) and all(isinstance(x, dict) for x in items):
            return "JSON", [dict(x) for x in items]
        raise ArgusError("unsupported_json", "JSON must be an array of objects or a GeoJSON FeatureCollection")
    raise ArgusError("unsupported_format", "Supported formats: CSV, XLSX, JSON, GeoJSON")


def parse_file(filename: str, content: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Any parser failure (broken XLSX zip, bad JSON, binary data) becomes one clear, localizable error, never a 500."""
    try:
        return _parse(filename, content)
    except ArgusError:
        raise
    except Exception as exc:  # noqa: BLE001 — third-party parsers raise many exception types
        raise ArgusError("unreadable_file", f"File could not be parsed: {type(exc).__name__}") from exc


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


_DMY = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*(.*)$")


def _tz(offset: Any) -> timezone | None:
    """'+05:00', '+5', '300' (minutes) or 5 (hours) → tzinfo; None when absent or unreadable."""
    s = _s(offset)
    if s is None:
        return None
    m = re.fullmatch(r"(?:UTC)?\s*([+-])?(\d{1,2})(?::?(\d{2}))?", s, re.I)
    if m and int(m.group(2)) <= 14:
        sign = -1 if m.group(1) == "-" else 1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
    try:
        minutes = int(float(s))
    except ValueError:
        return None
    return timezone(timedelta(minutes=minutes)) if abs(minutes) <= 14 * 60 else None


def _dt(v: Any, errors: list[str], field: str, required: bool = False, tz: timezone | None = None) -> str | None:
    if isinstance(v, datetime):
        d = v
    else:
        s = _s(v)
        if s is None:
            if required:
                errors.append(f"missing:{field}")
            return None
        m = _DMY.match(s)
        if m:  # 10.04.2024 18:00[+05:00] — the way dates are typed in Kazakhstan
            dd, mm, yyyy, hh, mi, ss, rest = m.groups()
            s = f"{yyyy}-{int(mm):02d}-{int(dd):02d}T{int(hh or 0):02d}:{mi or '00'}:{ss or '00'}{rest.strip()}"
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"invalid_timestamp:{field}")
            return None
    if d.tzinfo is None:
        if tz is None:
            errors.append(f"timestamp_without_timezone:{field}")
            return None
        d = d.replace(tzinfo=tz)
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
        tz = _tz(r.get("utc_offset"))
        ts = _dt(r.get("observed_at"), e, "observed_at", required=True, tz=tz)
        lvl = _f(r.get("water_level_cm"), e, "water_level_cm", required=True)
        if lvl is not None and not -100 <= lvl <= 3000:
            e.append("out_of_range:water_level_cm")
        q = _f(r.get("discharge_m3s"), e, "discharge_m3s")
        if q is not None and not 0 <= q <= 50000:
            e.append("out_of_range:discharge_m3s")
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
        if station is not None and ts and src and lvl is not None and not e:
            from app.services.ingest.observations import ObservationInput, is_duplicate

            if is_duplicate(db, ObservationInput(station_id=st, observed_at=datetime.fromisoformat(ts), water_level_cm=lvl,
                                                 discharge_m3s=q, source=src, source_type=stype, verification=ver)):
                e.append("duplicate_in_database")
        data = {"station_id": st, "observed_at": ts, "water_level_cm": lvl, "discharge_m3s": q, "source": src,
                "source_type": stype, "verification": ver, "notes": _s(r.get("notes"))}
    elif kind == "road_events":
        rid = _s(r.get("road_id"))
        segs_all = set(db.scalars(select(RoadSegment.id).where(RoadSegment.area_id == area.id, RoadSegment.road_id == rid))) if rid else set()
        if not segs_all:
            e.append("unknown:road_id")
        segs_raw = r.get("segment_ids")
        if isinstance(segs_raw, (list, tuple)):
            segs = [str(x).strip() for x in segs_raw if str(x).strip()]
        else:
            segs = [x.strip() for x in str(segs_raw or "").replace(",", ";").split(";") if x.strip()]
        if any(s not in segs_all for s in segs):
            e.append("unknown:segment_ids")
        state = (_s(r.get("state")) or "").upper()
        if state not in ("OPEN", "RESTRICTED", "CLOSED"):
            e.append("invalid:state")
        ver = (_s(r.get("verification")) or "UNVERIFIED").upper()
        if ver not in ("VERIFIED", "UNVERIFIED"):
            e.append("invalid:verification")
        data = {"road_id": rid, "segment_ids": segs, "state": state,
                "effective_from": _dt(r.get("effective_from"), e, "effective_from", tz=_tz(r.get("utc_offset"))),
                "effective_until": _dt(r.get("effective_until"), e, "effective_until", tz=_tz(r.get("utc_offset"))),
                "source": _s(r.get("source")) or "IMPORT", "verification": ver, "notes": _s(r.get("notes"))}
        if not data["effective_from"]:
            w.append("effective_from_defaults_to_now")
        if data["effective_from"] and data["effective_until"] and data["effective_until"] <= data["effective_from"]:
            e.append("until_before_from")
    else:
        raise ArgusError("invalid_import_type")
    return data, e, w


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return str(v)


def create_preview(db: Session, area: OperationalArea, kind: str, filename: str, content: bytes, actor: Actor) -> ImportJob:
    if kind not in IMPORT_TYPES:
        raise ArgusError("invalid_import_type", f"Import type must be one of {IMPORT_TYPES}")
    fmt, rows = parse_file(filename, content)
    if len(rows) > MAX_ROWS:
        raise ArgusError("too_many_rows", f"Maximum {MAX_ROWS} rows per import", max=MAX_ROWS)
    columns = [c.strip().lower() for c in (rows[0].keys() if rows else []) if isinstance(c, str) and c.strip()]
    missing_columns = [c for c in REQUIRED[kind] if c not in columns]
    unknown_columns = [c for c in columns if c not in TEMPLATES[kind] and c not in OPTIONAL_EXTRA]
    seen: set = set()
    out, nv, ni, nw = [], 0, 0, 0
    for i, raw in enumerate(rows, start=1):
        try:
            data, errs, warns = validate_row(db, area, kind, raw, seen)
        except ArgusError:
            raise
        except Exception:  # noqa: BLE001 — one malformed row must not abort the whole preview
            data, errs, warns = {}, ["unreadable_row"], []
        status = "INVALID" if errs else ("WARNING" if warns else "VALID")
        nv += status != "INVALID"
        ni += status == "INVALID"
        nw += status == "WARNING"
        out.append({"row": i, "status": status, "errors": errs, "warnings": warns, "data": data,
                    "raw": {(k if isinstance(k, str) else "_extra"): _jsonable(v) for k, v in raw.items()}})
    job = ImportJob(id=new_id("imp-"), area_id=area.id, import_type=kind, filename=filename, file_format=fmt,
                    status="PREVIEW", created_by=actor.username, rows_total=len(rows), rows_valid=nv, rows_invalid=ni,
                    rows_warning=nw, preview={"rows": out, "columns": columns, "template": TEMPLATES[kind],
                                              "missing_columns": missing_columns, "unknown_columns": unknown_columns})
    db.add(job)
    db.flush()
    record(db, actor, "IMPORT_PREVIEWED", "import", job.id, f"{kind} from {filename}: {nv} valid, {ni} invalid",
           area_id=area.id)
    return job


def confirm(db: Session, job: ImportJob, actor: Actor) -> ImportJob:
    from app.services.ingest.observations import ObservationInput, add_observation, entry_mode
    from app.services.operations.inputs import add_facility, add_road_event, upsert_resource

    if job.status != "PREVIEW":
        raise Conflict("import_not_in_preview", "Import already confirmed or cancelled")
    area = db.get(OperationalArea, job.area_id)
    obs_mode = entry_mode(area)
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
                        mode=obs_mode, import_id=job.id), actor)
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
