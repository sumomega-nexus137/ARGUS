"""DOWNLOAD ONCE → VERIFY → INSTALL → REUSE.

Installs the integrity-checked real-data packs produced by the data workflows into
``<realdata_root>/<area>/generated``. Normal application startup never calls this module's network
path: it only reads the installed files. The pinned archive checksums live in
``data/realdata/packs.lock.json`` (committed); every extracted file is then checked against the
pack's own ``metadata/dataset_manifest.json`` SHA-256 list.

Sources, in order: an already-installed pack whose marker matches the lock (no I/O beyond a hash
check of the marker), a cached archive in ``<realdata_root>/_cache``, an explicit local archive
(``--archive``), then the release URL (``ARGUS_REALDATA_RELEASE_BASE``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.core.config import REPO_ROOT, get_settings
from app.core.logging import get_logger

log = get_logger("argus.realdata")

AREAS = ("atbasar", "kokshetau")
LOCK_PATH = REPO_ROOT / "data" / "realdata" / "packs.lock.json"
MARKER = ".argus_install.json"


class PackError(RuntimeError):
    pass


@dataclass
class PackStatus:
    area: str
    installed: bool
    path: Path
    archive_sha256: str | None
    files_verified: int
    detail: str

    def as_dict(self) -> dict:
        return {"area": self.area, "installed": self.installed, "path": str(self.path),
                "archive_sha256": self.archive_sha256, "files_verified": self.files_verified, "detail": self.detail}


def load_lock() -> dict:
    with open(LOCK_PATH, encoding="utf-8") as f:
        return json.load(f)


def pack_dir(area: str) -> Path:
    return get_settings().realdata_root / area / "generated"


def cache_dir() -> Path:
    return get_settings().realdata_root / "_cache"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _manifest_files(root: Path) -> list[dict]:
    m = root / "metadata" / "dataset_manifest.json"
    if not m.exists():
        raise PackError(f"{root}: metadata/dataset_manifest.json missing")
    data = json.loads(m.read_text(encoding="utf-8"))
    files = data.get("files", [])
    if not files:
        raise PackError(f"{root}: dataset manifest lists no files")
    return files


def verify_tree(root: Path) -> int:
    """Verify every file listed in the pack manifest (presence, size, SHA-256). Returns files checked."""
    bad: list[str] = []
    files = _manifest_files(root)
    for entry in files:
        p = root / entry["path"]
        if not p.exists():
            bad.append(f"missing {entry['path']}")
            continue
        want = entry.get("sha256")
        if want and sha256_file(p) != want:
            bad.append(f"checksum {entry['path']}")
        elif entry.get("bytes") is not None and p.stat().st_size != int(entry["bytes"]):
            bad.append(f"size {entry['path']}")
    if bad:
        raise PackError(f"{root}: {len(bad)} file(s) failed verification: {bad[:5]}")
    return len(files)


def status(area: str) -> PackStatus:
    """Cheap check used at startup: marker exists and matches the pinned lock entry."""
    root = pack_dir(area)
    lock = load_lock()["packs"][area]
    marker = root / MARKER
    if not marker.exists():
        return PackStatus(area, False, root, None, 0, "not installed")
    try:
        mk = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PackStatus(area, False, root, None, 0, "install marker unreadable")
    if mk.get("archive_sha256") != lock["sha256"]:
        return PackStatus(area, False, root, mk.get("archive_sha256"), 0, "installed pack does not match packs.lock.json")
    return PackStatus(area, True, root, mk["archive_sha256"], int(mk.get("files_verified", 0)), "installed")


def _download(url: str, dest: Path, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            log.info("downloading %s (attempt %d)", url, attempt)
            req = urllib.request.Request(url, headers={"User-Agent": "argus-floodops-installer"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:  # noqa: S310 (pinned https URL)
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.replace(dest)
            return
        except Exception as exc:  # network errors are retried, then reported
            last = exc
            time.sleep(2 ** attempt)
    raise PackError(f"download failed for {url}: {last}")


def _safe_extract(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            p = (target / m.name).resolve()
            if not str(p).startswith(str(target.resolve())) or m.issym() or m.islnk():
                raise PackError(f"unsafe path in archive: {m.name}")
        tf.extractall(target, filter="data")


def install(area: str, archive: Path | None = None, force: bool = False, offline: bool = False) -> PackStatus:
    lock = load_lock()["packs"][area]
    current = status(area)
    if current.installed and not force:
        log.info("%s pack already installed and matches lock — nothing to do", area)
        return current

    cached = cache_dir() / lock["file"]
    src: Path | None = None
    for cand in (archive, cached):
        if cand is not None and cand.exists():
            digest = sha256_file(cand)
            if digest == lock["sha256"]:
                src = cand
                break
            log.warning("%s has sha256 %s, expected %s — ignoring", cand, digest, lock["sha256"])
    if src is None:
        if offline:
            raise PackError(f"{area}: no verified local archive and --offline given")
        url = f"{get_settings().realdata_release_base.rstrip('/')}/{lock['file']}"
        _download(url, cached)
        digest = sha256_file(cached)
        if digest != lock["sha256"]:
            cached.unlink(missing_ok=True)
            raise PackError(f"{area}: downloaded archive sha256 {digest} does not match lock {lock['sha256']}")
        src = cached
    elif src != cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, cached)

    root = pack_dir(area)
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root.parent, prefix=f".{area}-extract-") as tmpd:
        tmp = Path(tmpd) / "generated"
        tmp.mkdir()
        _safe_extract(src, tmp)
        n = verify_tree(tmp)
        (tmp / MARKER).write_text(json.dumps({
            "area": area, "archive": lock["file"], "archive_sha256": lock["sha256"], "files_verified": n,
            "source_run_id": lock.get("source_run_id"), "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, indent=2), encoding="utf-8")
        if root.exists():
            shutil.rmtree(root)
        tmp.replace(root)
    log.info("%s pack installed: %d files verified → %s", area, n, root)
    return status(area)


def verify_installed(area: str) -> PackStatus:
    st = status(area)
    if not st.installed:
        return st
    n = verify_tree(st.path)
    return PackStatus(area, True, st.path, st.archive_sha256, n, "installed; all files re-verified")


def installed_areas() -> list[str]:
    try:
        return [a for a in AREAS if status(a).installed]
    except (OSError, KeyError, ValueError):
        return []
