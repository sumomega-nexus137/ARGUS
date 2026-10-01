# ARGUS real-data & API readiness

This document is the handoff boundary between the **data acquisition/preparation work** and the
application work. Claude Code can consume the processed packs through the existing ARGUS data
contracts; it should not reimplement the upstream download logic inside normal application startup.

## Operating rule

Historical/demo datasets are **downloaded and processed once**, then ARGUS runs from local/cached
files. Live providers are separate adapters. A missing live provider must show
`NOT_CONFIGURED / OFFLINE / CACHED`; it must never be replaced with fabricated data.

Authority order:

`VERIFIED FIELD > OFFICIAL LOCAL SENSOR/HYDROPOST > OFFICIAL FORECAST > SATELLITE > GLOBAL MODEL > SIMULATION`

## Prepared public sources

| Source | Access | Purpose | Credentials | Current preparation |
|---|---|---|---|---|
| Copernicus DEM GLO-30 | public COG | DEM, slope, terrain/model input | none | automated for Atbasar + Kokshetau |
| OpenStreetMap / Overpass | public API | roads, graph, buildings, waterways, bridges/culverts, candidate facilities | none | automated + cached pack |
| WorldPop 2024 | public raster | population exposure | none | automated + cached pack |
| JRC Global Surface Water | public STAC/raster | permanent-water baseline | none | automated where catalogue/asset is available |
| Sentinel-2 L2A / Earth Search | public STAC/COG | Atbasar 2024 observed flood evidence fallback | none | event scenes confirmed; automated selection + masking |
| Landsat C2 L2 / Earth Search | public STAC/COG | independent optical fallback/check | none | event scenes confirmed |
| Sentinel-1 | public catalogues | preferred SAR flood evidence when an acquisition exists | none for catalogue | **no Atbasar 2024 acquisition found in catalogue probes**; recorded as unavailable, not faked |

## Official/local sources

Kazhydromet and Tasqyn are authoritative sources when an authorized endpoint/integration is
available, but ARGUS must not assume an undocumented public REST API. For the competition pack,
official public reports are stored with exact provenance and measurement/reference caveats.
The existing backend provider adapters can be configured later with authorized endpoints.

Manual/CSV/XLSX/JSON/GeoJSON ingestion remains a first-class production path for:

- hydrology observations;
- road closures/field reports;
- resource inventories and status;
- critical facilities;
- approved actions.

This is intentional, not a demo shortcut: emergency agencies often operate with mixed
API/manual/field channels.

## Pilot packs

### Atbasar / Zhabai

Primary historical validation pilot. Output directory:

`data/realdata/atbasar/generated/`

Expected core contents after a successful build:

- `processed/dem_atbasar_utm42n.tif`
- `processed/slope_atbasar_deg.tif`
- `processed/argus_roads.geojson`
- `processed/argus_road_nodes.geojson`
- `processed/argus_buildings.geojson`
- `processed/osm_waterways.geojson`
- `processed/osm_bridges_culverts.geojson`
- `processed/argus_critical_facilities.geojson`
- `processed/worldpop_2024_100m_utm42n.tif` when available
- selected satellite scene rasters
- `processed/observed_flood_mask_2024.tif`
- `processed/flood_mask_qc.png`
- `validation/atbasar/atbasar-2024/observed.tif`
- provenance/selection/manifests under `metadata/`
- official event/hydrology CSVs under `curated/`

The observed mask is always labelled
`AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC`. It is not ground truth merely because it
came from a satellite. No IoU/precision/recall should be shown until a modelled mask exists and the
observed mask has passed visual QC.

### Kokshetau / Kylshakty

Portability/bottleneck pilot. Output directory:

`data/realdata/kokshetau/generated/`

The build already produces and integrity-tests real DEM, slope, OSM road graph, roads, buildings,
waterways, bridge/culvert candidates, critical-facility candidates, WorldPop exposure and curated
official 2024 hydrology/event records. Atbasar remains the primary historical satellite-validation
pilot.

## CI quality gates

`scripts/realdata/validate_pack.py` checks generated data for:

- readable rasters/vectors;
- expected CRS;
- nonempty required layers;
- valid geometries;
- raster dimensions/resolution/finite data;
- manifest references;
- curated CSV schemas and duplicate rows;
- selected satellite source and scene metadata;
- minimum usable clear-pixel coverage for optical flood evidence;
- explicit `REQUIRES_QC` state.

Passing this validator means the **data package is structurally ready for ARGUS**. It does not
claim that an automatically derived flood mask has been manually certified by a hydrologist.

## Application handoff

Claude Code should:

1. Download/materialize the successful Atbasar and Kokshetau real-data artifacts once.
2. Put the processed files in the local deployment/data volume; normal startup must not call the
   upstream satellite/DEM/OSM download pipeline.
3. Point area `dem_path`, vector imports and validation dataset paths at those local files.
4. Keep external live providers optional/degraded-mode safe.
5. Preserve source/mode/data-age/confidence/assumptions in the UI.
6. Run backend, frontend, integration and full demo tests after the data packs are mounted.
7. Never replace unavailable official data with simulation without an explicit SIMULATION badge.

The acquisition pipelines remain reproducible update tools, not runtime dependencies.
