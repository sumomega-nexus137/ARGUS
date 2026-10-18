# Real-data packs — install once, verify, reuse

ARGUS runs its two pilots on prepared real-data packs (Copernicus DEM, OpenStreetMap, WorldPop, JRC Global
Surface Water, Sentinel-2 L2A, curated official 2024 reports and Open-Meteo/GloFAS event context). The packs are
**not** stored in Git history. They are published as release assets and installed once:

**DOWNLOAD ONCE → VERIFY → INSTALL → REUSE ON EVERY START**

| Pack | Archive | Size | Integrity checks in pack |
|---|---|---|---|
| Atbasar / Zhabai (primary validation pilot) | `argus-atbasar-realdata.tar.gz` | 98.2 MB | 36 |
| Kokshetau / Kylshakty (portability / bottleneck pilot) | `argus-kokshetau-realdata.tar.gz` | 53.6 MB | 15 |

Archive SHA-256 values, the release tag (`realdata-2026-10-01`) and the source workflow runs are pinned in
[`data/realdata/packs.lock.json`](../data/realdata/packs.lock.json). The release itself is produced by
[`.github/workflows/realdata-release.yml`](../.github/workflows/realdata-release.yml) from the data-workflow
artifacts (validated with `scripts/realdata/validate_pack.py`, deterministic tar, `SHA256SUMS`).

## Install

```bash
cd backend && . .venv/bin/activate
python -m app.cli install-realdata              # both areas; downloads only what is missing
python -m app.cli realdata-status --verify      # re-hash every installed file against the pack manifest
```

What `install-realdata` does, per area:

1. If `<realdata>/<area>/generated/.argus_install.json` matches the lock → **nothing to do** (no network).
2. Otherwise it looks for a verified archive in `<realdata>/_cache/`, then `--archive FILE` (offline install
   from a USB copy), then downloads `ARGUS_REALDATA_RELEASE_BASE/<file>` (urllib, retries).
3. The archive SHA-256 must equal the lock value, otherwise it is rejected and deleted.
4. Safe extraction (`tarfile` data filter, no absolute paths / `..` / links) into a temporary directory,
   then every file is checked against the pack's own `metadata/dataset_manifest.json` (SHA-256 and size).
5. The verified tree is moved into `<realdata>/<area>/generated` (rename from a sibling temp directory) with an install marker.

Options: `--area atbasar|kokshetau`, `--archive F.tar.gz`, `--offline` (never touch the network), `--force`.

`<realdata>` defaults to `data/realdata` and is configurable with `ARGUS_REALDATA_DIR` (Docker uses the
`packs` volume at `/srv/argus/packs`). `data/realdata/*/generated/` and `data/realdata/_cache/` are gitignored.

## Start-up

Normal start-up **never downloads** pack data. On first start with installed packs ARGUS builds a small runtime
bundle per area (`data/runtime/realdata/<area>/`: road graph, buildings, facilities, sectors, population zones,
bottleneck candidates, scenario manifest wiring). It is rebuilt only when the pack checksum, the curated
exercise files or the builder version change.

| `ARGUS_DATA_PROFILE` | Behaviour |
|---|---|
| `auto` (default) | HISTORICAL real-data pilots when both packs are installed, otherwise the synthetic DEMO |
| `historical` | real-data pilots; start-up **fails loudly** if a pack is missing (never silently synthetic) |
| `demo` | synthetic DEMO / SIMULATION areas only (used by the unit-test suite) |

The database is seeded from the selected profile when it is empty. To switch profile, start with an empty
database (delete `data/argus.db` for SQLite, or `python -m app.cli reset-demo` in demo mode).

## Docker

`docker compose up --build` installs the packs into the `packs` volume on first start (entrypoint
`backend/docker/entrypoint.sh`, `ARGUS_INSTALL_REALDATA=true`) and reuses them afterwards. Without network
access an existing installation is kept; a missing one falls back according to `ARGUS_DATA_PROFILE`.

## What is in a pack (summary)

| Layer | Source | Mode in ARGUS |
|---|---|---|
| Terrain | Copernicus DEM GLO-30 (30 m DSM), reprojected to UTM 42N | HISTORICAL (static) |
| Roads, buildings, facilities, waterways | OpenStreetMap via OSMnx / Overpass extract (ODbL) | CACHED snapshot |
| Population | WorldPop 2024 100 m (modelled) → dasymetric zones on OSM buildings | HISTORICAL (modelled) |
| Permanent water | JRC Global Surface Water occurrence | HISTORICAL |
| Flood evidence (Atbasar) | Sentinel-2 L2A 14 Apr 2024 vs 21 Apr 2024 (no Sentinel-1 acquisition existed) | HISTORICAL, requires QC |
| Scenario (Atbasar) | hybrid terrain-conditioned susceptibility + stage proxy, LOW / BASE / HIGH rasters | HISTORICAL |
| Scenario (Kokshetau) | stage–HAND exercise on the real DEM (uncalibrated) | SIMULATION |
| Chronology / levels | curated official reports (gov.kz), timestamps with stated precision | HISTORICAL, UNVERIFIED |
| GloFAS / weather | Open-Meteo archive for the event period | HISTORICAL context (GLOBAL_MODEL / REANALYSIS) |

Full provenance and limitations: [`REAL_DATA_FINAL_STATUS.md`](REAL_DATA_FINAL_STATUS.md),
[`REAL_DATA_PIPELINE.md`](REAL_DATA_PIPELINE.md), [`METHODOLOGY.md`](METHODOLOGY.md).
