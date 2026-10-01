# ARGUS real-data final status — 2026-10-01

**Scope:** datasets, reproducible acquisition/pre-processing, public API profiles, historical
validation evidence, and application handoff. Backend/frontend/demo integration remains Claude
Code's job after these packs are mounted.

## Final workflow state

| Pack | Workflow run | Result | GitHub artifact | Compressed size | Retention |
|---|---:|---|---|---:|---|
| Atbasar / Zhabai | 36886595533 | **SUCCESS** | `argus-atbasar-realdata` (artifact 11174673127) | 98,198,711 B | through 2026-10-31 |
| Kokshetau / Kylshakty | 36886613476 | **SUCCESS** | `argus-kokshetau-realdata` (artifact 11174708363) | 53,519,434 B | through 2026-10-31 |
| Upstream public API readiness | 36884150119 | **SUCCESS** | `argus-api-readiness` | — | CI artifact |

The extracted packs are roughly **108 MB Atbasar** and **71 MB Kokshetau** in the checked build.

## Atbasar data checks

All **36 required integrity checks passed with zero warnings** in the final successful build.
The pack includes real Copernicus DEM/slope, OSM roads/nodes/buildings/waterways/bridge candidates,
WorldPop, JRC water occurrence, curated official hydrology/event records, satellite evidence,
historical GloFAS/weather context, scenario rasters, validation masks, provenance and checksums.

### Satellite evidence

Sentinel-1 was preferred, but the probed catalogues returned no suitable acquisition for the Atbasar
2024 event. ARGUS records that absence instead of faking SAR data.

The accepted optical fallback is Sentinel-2 L2A:

- flood-period scene: `S2A_42UVC_20240414_1_L2A`, 2024-04-14 06:44:53 UTC,
  scene cloud cover 14.97%;
- post-recession reference: `S2A_42UVC_20240421_0_L2A`, 2024-04-21 06:34:57 UTC,
  scene cloud cover ~0.0003%;
- common usable optical coverage: **86.46%** of the analysis raster;
- automatic newly-observed-water baseline: about **30.19 km² by raw 20 m pixel count** before any
  claim of official ground-truth certification.

A development visual review of `processed/flood_mask_qc.png` confirms that the extracted mask
tracks the main flood-period water expansion visible in the spectral comparison and that the
post-recession reference greatly improves usable coverage over the snow/ice-heavy early-April
scene. This is a **technical visual QC pass with limitations**, not hydrologist/agency certification.
The data therefore keeps the explicit `REQUIRES_DOMAIN_QC` caveat.

### Historical model evidence

The pack now contains a **hybrid terrain-susceptibility + river-relative stage/connectivity proxy**,
not a claimed full hydrodynamic digital twin. Its susceptibility component uses terrain/hydro
features and deliberately excludes raw X/Y coordinates.

Final measured same-event results:

| Evaluation | IoU | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Spatial calibration blocks | 0.7842 | 0.8622 | 0.8966 | 0.8791 |
| **Alternating spatial holdout blocks** | **0.5881** | **0.8155** | **0.6783** | **0.7406** |
| All usable pixels | 0.6762 | 0.8392 | 0.7768 | 0.8068 |

These are **same historical event spatial-holdout metrics**. They are useful for historical
validation/demo evidence, but they must not be described as independent future-event forecast
accuracy.

The scenario pack includes LOW / BASE / HIGH precomputed depth frames, a raster manifest for the
existing ARGUS provider contract, susceptibility probability, relative elevation to the Zhabai,
distance-to-river rasters, `observed.tif`, `modelled.tif`, and a satellite-usable validation AOI.

## Kokshetau data checks

All **15 required integrity checks passed with zero warnings**. The Kokshetau pack contains real
terrain, OSM routing/buildings/waterways/bridges/facility candidates, JRC water baseline, WorldPop,
official curated Kylshakty 2024 observations/events, and public historical GloFAS/weather context.

Kokshetau remains the portability/bottleneck pilot; Atbasar remains the primary satellite-validation
pilot.

## Public API readiness

CI successfully probes the ready public sources. Concrete request/normalization contracts are stored
in `data/realdata/api_profiles.json`.

Ready without private secrets:

- Open-Meteo Flood API / GloFAS v4 — global-model discharge context/forecast;
- Open-Meteo Forecast API — precipitation, snowfall, snow depth, temperature and soil-moisture context;
- Open-Meteo Historical Weather API — historical meteorological context;
- Element84 Earth Search — Sentinel-2 / Landsat catalogue and assets;
- Planetary Computer — JRC Global Surface Water;
- Copernicus DEM public COGs;
- OpenStreetMap / Overpass;
- WorldPop.

Not falsely claimed as configured:

- Kazhydromet live API — requires an authorized/stable endpoint; official public reports and
  manual/CSV/XLSX ingestion are prepared instead;
- Tasqyn live API — requires an authorized integration endpoint;
- any agency-only resource/road/field feed — must remain `NOT_CONFIGURED` until supplied.

## Handoff to Claude Code

The data work is now at the application-integration boundary. Claude Code should consume the
successful artifacts once, mount/copy them into the persistent deployment data volume, configure the
existing ARGUS provider/import paths, and then run the backend/frontend/integration/demo test suite.

Normal ARGUS startup must **not** redownload these historical packs. Live/global-model APIs are
separate optional providers with cached/degraded modes.

Machine-readable status: `data/realdata/final_status.json`.
