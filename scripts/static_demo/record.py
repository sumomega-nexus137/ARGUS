"""Record a read-only snapshot of the ARGUS API for the static online demo (GitHub Pages).

Runs the real backend in-process on a fresh database (real-data packs must be installed), performs the
computations a visitor would trigger (stress test, CP-SAT alternatives for every policy, resource gap,
bottleneck analyses, validation run) and stores every response the console requests, keyed exactly like
`frontend/lib/staticDemo.ts` looks them up.

    cd backend && python ../scripts/static_demo/record.py --out ../frontend/public/demo-data

Nothing here is invented: every file is a response of the real ARGUS engines, recorded at build time.
External live feeds are disabled so a recording can never pose as live data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

EXT = {"application/json": "json", "text/html": "html", "image/png": "png", "text/csv": "csv", "text/plain": "txt"}


def num(v: str) -> str:
    """Same normalisation as staticDemo.ts: numeric strings are rewritten like JavaScript String(Number(v))."""
    try:
        f = float(v)
    except ValueError:
        return v
    if not math.isfinite(f) or v.strip() == "":
        return v
    return str(int(f)) if f.is_integer() else repr(f)


def get_key(path: str) -> str:
    parts = urlsplit(path)
    q = sorted((k, num(v)) for k, v in parse_qsl(parts.query, keep_blank_values=True))
    return "GET " + parts.path + ("?" + "&".join(f"{k}={v}" for k, v in q) if q else "")


def post_key(path: str, body: dict | None) -> str:
    b = {k: v for k, v in (body or {}).items() if k != "as_of_min"}
    return "POST " + urlsplit(path).path + " " + json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Resp:
    def __init__(self, status: int, content: bytes, ct: str):
        self.status_code, self.content, self.headers = status, content, {"content-type": ct}

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:300]}")


class Http:
    """Minimal client for the real ARGUS API process (no test-client dependency)."""

    def __init__(self, base: str):
        self.base = base

    def _req(self, method: str, path: str, headers: dict | None = None, json_body=None) -> Resp:
        data = None
        h = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return Resp(r.status, r.read(), r.headers.get("content-type", ""))
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read(), e.headers.get("content-type", "") if e.headers else "")

    def get(self, path: str, headers: dict | None = None) -> Resp:
        return self._req("GET", path, headers)

    def post(self, path: str, headers: dict | None = None, json=None) -> Resp:  # noqa: A002 — mirrors requests' API
        return self._req("POST", path, headers, json if json is not None else {})


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Recorder:
    def __init__(self, client, out: Path, token: str):
        self.c = client
        self.out = out
        self.h = {"Authorization": f"Bearer {token}"}
        self.entries: dict[str, dict] = {}
        self.bytes = 0
        self.misses: list[str] = []
        (out / "r").mkdir(parents=True, exist_ok=True)

    def _store(self, key: str, content: bytes, ct: str) -> None:
        ct = ct.split(";")[0].strip() or "application/octet-stream"
        f = f"r/{hashlib.sha1(key.encode()).hexdigest()[:20]}.{EXT.get(ct, 'bin')}"
        (self.out / f).write_bytes(content)
        self.entries[key] = {"f": f, "ct": ct}
        self.bytes += len(content)

    def get(self, path: str, required: bool = False):
        key = get_key(path)
        if key in self.entries:
            return json.loads((self.out / self.entries[key]["f"]).read_bytes()) if self.entries[key]["ct"] == "application/json" else None
        r = self.c.get(path, headers=self.h)
        if r.status_code != 200:
            self.misses.append(f"{r.status_code} {path}")
            if required:
                raise RuntimeError(f"{path} → {r.status_code}: {r.text[:300]}")
            return None
        self._store(key, r.content, r.headers.get("content-type", ""))
        return r.json() if "json" in r.headers.get("content-type", "") else None

    def post(self, path: str, body: dict | None = None):
        r = self.c.post(path, headers=self.h, json=body or {})
        if r.status_code != 200:
            self.misses.append(f"{r.status_code} POST {path}")
            print(f"  ! POST {path} → {r.status_code} {r.text[:200]}", flush=True)
            return None
        self._store(post_key(path, body), r.content, r.headers.get("content-type", ""))
        return r.json()

    def tile(self, area: str, z: int, x: int, y: int) -> bool:
        r = self.c.get(f"/api/tiles/terrain/{area}/{z}/{x}/{y}.png", headers=self.h)
        if r.status_code != 200:
            return False
        p = self.out / "tiles" / "terrain" / area / str(z) / str(x)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{y}.png").write_bytes(r.content)
        self.bytes += len(r.content)
        return True


def tiles_for(bbox: list[float], z: int) -> list[tuple[int, int]]:
    def xy(lon: float, lat: float) -> tuple[int, int]:
        n = 2 ** z
        x = int((lon + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        return x, y

    pad = 0.08
    x0, y0 = xy(bbox[0] - pad, bbox[3] + pad)
    x1, y1 = xy(bbox[2] + pad, bbox[1] - pad)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


LAYERS = ["roads", "buildings", "facilities", "task_sites", "bases", "bridges", "bottlenecks", "sectors", "waterways", "river", "stations"]
TILE_ZOOMS = range(7, 13)  # the static map caps the DEM source at z12 (≈15–20 m/px at 52°N, finer than the 30 m DEM)


def record_area(rec: Recorder, a: str) -> None:
    t0 = time.time()
    area = rec.get(f"/api/areas/{a}", required=True)
    sc = rec.get(f"/api/areas/{a}/scenario", required=True)
    plans = rec.get(f"/api/areas/{a}/plans", required=True) or []
    active = [v for p in plans for v in p["versions"] if v["status"] == "ACTIVE"]
    policies = rec.get("/api/policies", required=True)["policies"]

    # --- computations a visitor triggers, recorded with the exact request bodies the console sends
    for v in active:
        vid = v["id"]
        print(f"  {a}: stress test {vid}", flush=True)
        rec.post(f"/api/plan-versions/{vid}/stress-test")
        for pol, w in policies.items():
            print(f"  {a}: alternatives {pol}", flush=True)
            rec.post(f"/api/plan-versions/{vid}/alternatives",
                     {"policy": pol, "weights": {"life": w["life"], "infra": w["infra"], "economic": w["economic"]},
                      "what_if_unavailable": [], "extra_constraints": []})
        print(f"  {a}: resource gap", flush=True)
        w = policies["BALANCED"]
        rec.post(f"/api/plan-versions/{vid}/resource-gap",
                 {"policy": "BALANCED", "weights": {"life": w["life"], "infra": w["infra"], "economic": w["economic"]},
                  "what_if_unavailable": [], "extra_constraints": []})
    # the alternatives run shown by default is the BALANCED one: re-run it last so it is the latest run
    for v in active:
        w = policies["BALANCED"]
        rec.post(f"/api/plan-versions/{v['id']}/alternatives",
                 {"policy": "BALANCED", "weights": {"life": w["life"], "infra": w["infra"], "economic": w["economic"]},
                  "what_if_unavailable": [], "extra_constraints": []})
    now = sc["now_min"]
    bns = (rec.get(f"/api/areas/{a}/layers/bottlenecks") or {}).get("features", [])
    print(f"  {a}: bottleneck analyses ({len(bns)})", flush=True)
    rec.post(f"/api/areas/{a}/bottlenecks/analyze", {"bottleneck_ids": [], "as_of_min": now})
    for f in bns:
        rec.post(f"/api/areas/{a}/bottlenecks/analyze", {"bottleneck_ids": [f["properties"]["id"]], "as_of_min": now})
    val = rec.get(f"/api/areas/{a}/validation") or {}
    for ds in val.get("datasets") or []:
        if ds.get("status") in ("READY", "PARTIAL"):
            print(f"  {a}: validation run {ds['id']}", flush=True)
            rec.post(f"/api/areas/{a}/validation/run", {"dataset_id": ds["id"]})

    # --- every GET the screens issue (after the computations, so lists include their results)
    for k in ("/api/areas", f"/api/areas/{a}", f"/api/areas/{a}/scenario", f"/api/areas/{a}/plans"):
        rec.entries.pop(get_key(k), None)
    area = rec.get(f"/api/areas/{a}", required=True)
    sc = rec.get(f"/api/areas/{a}/scenario", required=True)
    plans = rec.get(f"/api/areas/{a}/plans", required=True) or []
    for layer in LAYERS:
        rec.get(f"/api/areas/{a}/layers/{layer}")
    frames = sc["frame_offsets_min"]
    rec.get(f"/api/areas/{a}/access")
    rec.get(f"/api/areas/{a}/access/timeline")
    rec.get(f"/api/areas/{a}/impact/timeline")
    for calc in ("false", "true"):
        rec.get(f"/api/areas/{a}/impact?include_calculation={calc}")
    for t in sorted(set(frames) | {now}):
        rec.get(f"/api/areas/{a}/access?t={num(str(t))}")
        for calc in ("false", "true"):
            rec.get(f"/api/areas/{a}/impact?t={num(str(t))}&include_calculation={calc}")
    lo, hi = min(frames), max(frames)
    for t in range(int(math.floor(lo / 10) * 10), int(math.ceil(hi / 10) * 10) + 1, 10):
        rec.get(f"/api/scenarios/{sc['id']}/frames/{t}/depth.png?member={sc['active_member']}")
        rec.get(f"/api/scenarios/{sc['id']}/frames/{t}/extent?member={sc['active_member']}")
    rec.get(f"/api/scenarios/{sc['id']}/stats")
    for p in ("operations", "sites", "resources", "optimization-runs", "observations", "conflicts", "road-events",
              "freshness", "imports", "history", "hydrograph", "context/live", "validation", "after-action"):
        rec.get(f"/api/areas/{a}/{p}")
    rec.get(f"/api/actions?area_id={a}")
    for lang in ("kk", "ru", "en"):
        rec.get(f"/api/areas/{a}/report.html?lang={lang}")
    for p in plans:
        for v in p["versions"]:
            vid = v["id"]
            rec.get(f"/api/plan-versions/{vid}")
            rec.get(f"/api/plan-versions/{vid}/health")
            for st in rec.get(f"/api/plan-versions/{vid}/stress-tests") or []:
                rec.get(f"/api/stress-tests/{st['id']}")
    for run in rec.get(f"/api/areas/{a}/optimization-runs") or []:
        rec.get(f"/api/optimization-runs/{run['id']}")
    val = rec.get(f"/api/areas/{a}/validation") or {}
    if (val.get("historical") or {}).get("has_qc_png") or val.get("has_qc_png"):
        rec.get(f"/api/areas/{a}/validation/qc.png")
    for run in val.get("runs") or []:
        for layer in ("observed", "modelled", "difference"):
            rec.get(f"/api/validation-runs/{run['id']}/layers/{layer}.png")
    for only in (False, True):
        rec.get(f"/api/audit?limit=300&area_id={a}" + ("&affects_results=true" if only else ""))
    n = 0
    for z in TILE_ZOOMS:
        n += sum(rec.tile(a, z, x, y) for x, y in tiles_for(area["bbox"], z))
    print(f"  {a}: done in {time.time() - t0:.0f}s ({n} terrain tiles)", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="argus-snapshot-"))
    os.environ.update({
        "ARGUS_DATABASE_URL": f"sqlite:///{(work / 'snapshot.db').as_posix()}",
        "ARGUS_WARMUP": "false",
        "ARGUS_OPEN_METEO_ENABLED": "false",  # a recording must never pose as live data
        "ARGUS_ENABLE_PROVIDER_WORKER": "false",
    })
    backend = Path(__file__).resolve().parents[2] / "backend"
    port = free_port()
    log = open(work / "api.log", "wb")  # noqa: SIM115 — must outlive this block (API process output)
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                           cwd=backend, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
    started = time.time()
    try:
        c = Http(f"http://127.0.0.1:{port}")
        for _ in range(600):
            if api.poll() is not None:
                raise RuntimeError("ARGUS API exited during startup:\n" + (work / "api.log").read_text()[-3000:])
            try:
                if c.get("/api/system/health").status_code == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("ARGUS API did not become healthy")
        r = c.post("/api/auth/login", json={"username": "planner", "password": "argus2026"})
        r.raise_for_status()
        token = r.json()["token"]
        rec = Recorder(c, out, token)
        me = c.get("/api/auth/me", headers=rec.h).json()
        for p in ("/api/system/health", "/api/areas", "/api/policies", "/api/admin/model-versions"):
            rec.get(p)
        for a in [x["id"] for x in rec.get("/api/areas", required=True)]:
            record_area(rec, a)
        for k in ("/api/areas", "/api/system/health"):
            rec.entries.pop(get_key(k), None)
            rec.get(k)
        for only in (False, True):
            rec.get("/api/audit?limit=300" + ("&affects_results=true" if only else ""))
        for kind in ("resources", "facilities", "observations", "road_events"):
            rec.get(f"/api/imports/templates/{kind}.csv")
    finally:
        api.terminate()
        try:
            api.wait(timeout=30)
        except subprocess.TimeoutExpired:
            api.kill()
        log.close()
    manifest = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "user": {**me, "full_name": me.get("full_name", "Demo")},
        "tiles": {"maxzoom": max(TILE_ZOOMS)},
        "entries": dict(sorted(rec.entries.items())),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(f"snapshot: {len(rec.entries)} responses, {rec.bytes / 1e6:.1f} MB, {time.time() - started:.0f}s → {out}")
    if rec.misses:
        print("not recorded (non-200):\n  " + "\n  ".join(rec.misses[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
