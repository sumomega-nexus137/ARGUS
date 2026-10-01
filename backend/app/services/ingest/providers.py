"""Provider status, data freshness and the scheduled update worker."""

from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import HydroStation, OperationalArea, ProviderStatus
from app.providers.registry import REGISTRY, ProviderNotConfigured
from app.services.audit import Actor, record
from app.services.clock import area_now

log = get_logger("argus.providers")
_outage = {"enabled": False}


def outage_enabled() -> bool:
    return _outage["enabled"]


def freshness(ps: ProviderStatus, now: datetime) -> dict:
    s = get_settings()
    age = (now - ps.last_success_at).total_seconds() / 60 if ps.last_success_at else None
    if ps.status == "NOT_CONFIGURED":
        cls = "NOT_CONFIGURED"
    elif ps.status == "OFFLINE":
        cls = "OFFLINE"
    elif ps.status == "NOT_POLLED":
        cls = "NOT_POLLED"
    elif ps.status == "DEGRADED":
        cls = "STALE" if age is not None and age > (get_settings().open_meteo_stale_after_min) else "CACHED"
    elif ps.mode == "STATIC":
        cls = "STATIC"
    elif ps.mode == "SIMULATION":
        limit = max(s.stale_after_min, (ps.schedule_min or 0) * 1.5)
        cls = "SIMULATION" if age is None or age <= limit else "STALE"
    elif ps.mode == "HISTORICAL":
        cls = "HISTORICAL"
    elif age is None:
        cls = "UNKNOWN"
    elif age > s.stale_after_min:
        cls = "STALE"
    elif ps.schedule_min and age > ps.schedule_min * 1.5:
        cls = "CACHED"
    else:
        cls = "LIVE" if ps.mode == "LIVE" else ps.mode
    return {
        "id": ps.id, "layer": ps.layer, "provider": ps.provider, "source": ps.source, "mode": ps.mode, "status": ps.status,
        "quality": ps.quality, "last_success_at": ps.last_success_at.isoformat() if ps.last_success_at else None,
        "last_attempt_at": ps.last_attempt_at.isoformat() if ps.last_attempt_at else None,
        "age_min": None if age is None else round(age, 1), "freshness": cls, "schedule_min": ps.schedule_min,
        "is_external": ps.is_external, "message": ps.message,
    }


def area_freshness(db: Session, area: OperationalArea) -> list[dict]:
    """Freshness per source. External live feeds are aged against the WALL CLOCK (they describe current conditions);
    local / historical layers against the area's operational clock."""
    from datetime import UTC

    now = area_now(area)
    wall = datetime.now(UTC)
    rows = db.scalars(select(ProviderStatus).where(ProviderStatus.area_id == area.id).order_by(ProviderStatus.layer))
    return [freshness(r, wall if (r.is_external and r.mode == "LIVE") else now) for r in rows]


def set_outage(db: Session, enabled: bool, actor: Actor) -> int:
    _outage["enabled"] = enabled
    n = 0
    for ps in db.scalars(select(ProviderStatus).where(ProviderStatus.is_external.is_(True))):
        if enabled:
            ps.message = "SIMULATED OUTAGE — external providers unreachable"
            if ps.status != "NOT_CONFIGURED":
                ps.status = "OFFLINE"
            ps.quality = "OFFLINE"
        else:
            p = REGISTRY.get(ps.provider)
            configured = bool(p and p.configured())
            ps.status = ("NOT_POLLED" if ps.provider.startswith("open_meteo") else "OK") if configured else "NOT_CONFIGURED"
            ps.message = None if configured else "Adapter contract available; credentials / endpoint not configured"
            ps.quality = "GLOBAL_MODEL" if ps.provider.startswith("open_meteo") else None
        n += 1
    record(db, actor, "PROVIDER_OUTAGE_SIMULATION", "providers", None,
           f"External provider outage simulation {'ENABLED' if enabled else 'DISABLED'}", details={"providers": n})
    return n


def poll_once(db: Session) -> list[dict]:
    """Run every configured external adapter once; failures never propagate."""
    out = []
    from datetime import UTC

    for area in db.scalars(select(OperationalArea)):
        now = datetime.now(UTC)
        stations = db.scalars(select(HydroStation.id).where(HydroStation.area_id == area.id)).all()
        info = {"id": area.id, "bbox": area.bbox, "center": [area.center.x, area.center.y],
                "stations": [{"id": sid} for sid in stations]}
        for ps in db.scalars(select(ProviderStatus).where(ProviderStatus.area_id == area.id,
                                                          ProviderStatus.is_external.is_(True))):
            prov = REGISTRY.get(ps.provider)
            if prov is None:
                continue
            ps.last_attempt_at = now
            if outage_enabled():
                ps.status = "OFFLINE"
                out.append({"area": area.id, "provider": ps.provider, "status": "OFFLINE"})
                continue
            try:
                res = prov.fetch(info)
                ps.status, ps.last_success_at, ps.message = "OK", now, None
                out.append({"area": area.id, "provider": ps.provider, "status": "OK", "records": len(res.records)})
            except ProviderNotConfigured:
                ps.status = "NOT_CONFIGURED"
                out.append({"area": area.id, "provider": ps.provider, "status": "NOT_CONFIGURED"})
            except Exception as exc:  # network / format errors → degraded, never a crash
                ps.status = "OFFLINE"
                ps.message = f"{type(exc).__name__}: last attempt failed"
                log.warning("provider %s failed for %s: %s", ps.provider, area.id, exc)
                out.append({"area": area.id, "provider": ps.provider, "status": "OFFLINE"})
    return out


class ProviderScheduler:
    """Background worker. Disabled by default (ARGUS_ENABLE_PROVIDER_WORKER=true to enable)."""

    def __init__(self, interval_s: int = 300):
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="argus-provider-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        from app.db.session import session_scope

        while not self._stop.wait(self.interval_s):
            try:
                with session_scope() as db:
                    poll_once(db)
            except Exception:
                log.exception("provider worker iteration failed")


def update_live_status(db: Session, area: OperationalArea, layer: str, res: dict) -> None:
    """Mirror a live-context result into the provider status row (honest mode; wall-clock timestamps)."""
    ps = db.get(ProviderStatus, f"{area.id}:{layer}")
    if ps is None:
        return
    from datetime import UTC

    ps.last_attempt_at = datetime.now(UTC)
    if res["mode"] == "LIVE":
        ps.status, ps.message = "OK", res.get("message")
        ps.last_success_at = datetime.fromisoformat(res["fetched_at"])
    elif res["mode"] in ("CACHED", "STALE"):
        ps.status, ps.message = "DEGRADED", res.get("message")
        ps.last_success_at = datetime.fromisoformat(res["fetched_at"])
    elif res["mode"] == "NOT_CONFIGURED":
        ps.status, ps.message = "NOT_CONFIGURED", res.get("message")
    else:
        ps.status, ps.message = "OFFLINE", res.get("message")
