# ARGUS real-data pipeline

This repository contains automated acquisition/pre-processing pipelines for the two competition pilots:

- **Atbasar / Zhabai, 2024** — primary historical validation pilot;
- **Kokshetau / Kylshakty** — portability and bottleneck-analysis pilot.

Run locally:

    pip install -r scripts/realdata/requirements.txt
    python scripts/realdata/atbasar_pipeline.py --output data/realdata/atbasar/generated
    python scripts/realdata/kokshetau_pipeline.py --output data/realdata/kokshetau/generated

The matching GitHub Actions workflows build, integrity-test and upload reusable processed data packs.
Normal ARGUS startup should consume those local/precomputed files; it should **not** redownload
Copernicus/OSM/satellite/WorldPop data every time the application starts.

## Atbasar pack

The Atbasar artifact contains:

- Copernicus GLO-30 terrain and slope in EPSG:32642;
- normalized OSM routable roads/nodes;
- OSM buildings, waterways, bridges/culverts and candidate critical facilities;
- WorldPop 2024 population exposure where available;
- JRC long-term surface-water occurrence where available;
- official curated 2024 Zhabai observations and event chronology;
- selected satellite flood-period/post-recession reference evidence;
- automatic 2024 observed-flood baseline and QC figure;
- provenance sidecars and SHA-256 manifest;
- validation folder with `observed.tif` but deliberately no fabricated `modelled.tif`.

### Historical satellite-source decision

ARGUS first probes Sentinel-1 because SAR is attractive for flood observation. For the Atbasar 2024
event, catalogue probes returned **zero Sentinel-1 acquisitions** for the target area/time, including
probes against Planetary Computer, Copernicus Data Space STAC and Element84 Earth Search. The
pipeline therefore records Sentinel-1 as unavailable for this event instead of manufacturing or
mislabeling data.

The real fallback is **Sentinel-2 L2A from Element84 Earth Search**. April 2024 scenes are available
over the Atbasar AOI. The pipeline selects a flood-period and post-recession reference pair using AOI coverage,
date proximity and cloud cover, downloads Green/NIR/SWIR1/SCL layers, masks cloud/shadow/snow, and compares flood-period open water with a clear post-recession reference. This avoids using the snow/ice-heavy 4 April scene as a false clean baseline.

Landsat Collection 2 Level-2 scenes are also confirmed available and remain an independent optical
fallback/check.

## Kokshetau pack

The Kokshetau artifact prepares:

- Copernicus GLO-30 terrain and slope;
- OSM road graph/roads, buildings, waterways, bridge/culvert candidates and critical-facility candidates;
- WorldPop 2024 population exposure;
- JRC surface-water baseline where available;
- curated official Kylshakty 2024 water-level/threshold records;
- curated 2024 flood impact/response chronology;
- provenance and integrity manifests.

Kokshetau is intentionally the **portability/bottleneck** pilot. Lake Kopa is treated as downstream
receiving water, not as the primary cause of Kylshakty flooding. Atbasar remains the primary
historical satellite-validation area.

## Scientific gates

The automatically derived satellite flood mask is **not automatically accepted as ground truth**.
It is marked `AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC`.

For the Sentinel-2 fallback, important limitations include cloud gaps, snow/ice, shallow/turbid water
and mixed pixels. Validation is restricted to usable observation coverage, and visual QC remains
mandatory before the mask is presented as competition validation evidence.

The curated hydrology tables intentionally keep different gauge/reference descriptions separate.
Bridge-reference values and local operational levels must not be merged into a single hydrograph
unless datum equivalence is established.

OSM facility criticality is a placeholder/default and is not an official emergency-service priority.

Validation metrics remain unavailable until:

1. the satellite-derived observation mask passes visual QC; and
2. a model-generated `modelled.tif` is produced on a compatible grid.

No IoU, precision, recall or claimed damage reduction may be invented.

## Integrity checks

Run:

    python scripts/realdata/validate_pack.py --area atbasar --root data/realdata/atbasar/generated
    python scripts/realdata/validate_pack.py --area kokshetau --root data/realdata/kokshetau/generated

The validator checks file presence, CRS/grid sanity, readable rasters/vectors, valid geometries,
CSV contracts, manifest references, satellite selection metadata and optical clear-pixel coverage.

The next modelling step is a terrain/HAND-like scenario pipeline calibrated against the accepted
2024 observation. ARGUS must not be described as a full hydrodynamic digital twin unless a
validated hydraulic model is actually integrated.

See `docs/REAL_DATA_HANDOFF.md` for the application-integration boundary and API/provider status.


## Terrain susceptibility refinement

The Atbasar data workflow also builds a reproducible historical flood-extent component from the
prepared evidence. It combines river-relative terrain features with a
`HistGradientBoostingClassifier`. The classifier intentionally **does not use raw X/Y coordinates**.
Features include relative elevation to the Zhabai, distance to river, slope, absolute/nearest-channel
elevation, multi-scale topographic-position indices, aspect and JRC water-occurrence context.

Parameter/threshold selection uses alternating ~1.2 km spatial calibration blocks; the other blocks
are reported as a same-event spatial holdout. This is useful evidence that the terrain features
generalise locally, but it is **not** out-of-event forecast validation and must never be described as
such. The operational scenario rasters additionally impose river-relative stage/time and
connectivity constraints.

The workflow produces:

- `scenarios/atbasar/flood_susceptibility_probability_2024.tif`;
- `scenarios/atbasar/calibration_metrics.json`;
- LOW / BASE / HIGH precomputed depth frames;
- `scenarios/atbasar/manifest.json` for the existing `RasterManifestProvider`;
- `validation/atbasar/atbasar-2024/modelled.tif`;
- a satellite-usable validation AOI.

## Public forecast/context APIs

The static packs also include historical context fetched from public APIs:

- Open-Meteo Flood API / GloFAS v4 river discharge;
- Open-Meteo Historical Weather API for temperature, precipitation, rain and snowfall.

These are labelled `GLOBAL_MODEL` or `REANALYSIS_OR_HISTORICAL_MODEL` and never override
Kazhydromet, Tasqyn or verified field observations. Concrete request/normalisation profiles are in
`data/realdata/api_profiles.json`.
