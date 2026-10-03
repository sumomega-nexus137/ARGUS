# Data contracts

Real geospatial and hydrological datasets are prepared separately and plug in here. Nothing in the
code assumes the demo data; the demo simply implements the same contracts.

## Coordinate systems

Vector inputs: GeoJSON in EPSG:4326. Rasters: GeoTIFF / COG in a projected CRS (e.g. UTM 42N,
EPSG:32642 for both areas), all frames of one scenario on the same grid.

## 1. Precomputed flood scenarios (`raster_manifest` provider)

```
<scenario_dir>/manifest.json
{
  "crs": "EPSG:32642",               // optional; read from rasters otherwise
  "bankfull_cm": 500,                // reference hydropost bankfull stage
  "hand_path": "hand.tif",           // optional
  "members": [
    {"id": "M1", "label": "P10",
     "gauge": [[-360, 548.0], [0, 590.0], [1440, 640.0]],          // [offset_min, stage_cm]
     "frames": [{"offset_min": -360, "depth_path": "M1/f_-360.tif"}, ...]}
  ]
}
```
Depth in metres, nodata = dry; frames are interpolated linearly in time. Example export:
`python -m app.cli export-scenario atbasar /tmp/atbasar_scenario`.

## 2. Static layers (per area)

| Layer | Required properties |
|---|---|
| roads (LineString per segment) | `id`, `road_id`, `road_class`, `speed_kmh`, `embankment_m`, `bridge_id?`, `names{kk,ru,en,original}` |
| bridges | `id`, `deck_level_m` / clearance |
| buildings (Polygon/Point) | `id`, `use`, `floor_area_m2`, `floor_height_m` |
| population_zones (Polygon) | `id`, `sector`, `population`, `vulnerable_share` — aggregated only |
| facilities (Point) | `id`, `facility_type`, `criticality 0–100`, `population_served`, `sector_id`, `names` |
| sectors (Polygon) | `id`, `names` |
| task_sites (Point) | `id`, `kind`, `work_depth_limit_m`, `protects{sector_ids,facility_ids,road_ids}`, `names` |
| terrain | DEM GeoTIFF (for HAND / 3D terrain) |

Names are multilingual; missing languages fall back kk → ru → en → original.

## 3. Imports (Data & input → Imports)

Upload CSV / XLSX / JSON / GeoJSON → preview → row validation → errors listed → confirm → import.
Invalid rows are never imported silently. Templates: `GET /api/imports/templates/{type}.csv`.

| Type | Columns |
|---|---|
| resources | id, resource_type (CREW/PUMP/VEHICLE/EQUIPMENT/OTHER), subtype, capacity, capacity_unit, base_id, name_kk, name_ru, name_en, status |
| facilities | id, facility_type, name_kk, name_ru, name_en, lon, lat, criticality, population_served, sector_id, verification, source |
| observations | station_id, observed_at (ISO 8601 with timezone), water_level_cm, discharge_m3s, source, source_type (FIELD/HYDROPOST/FORECAST/SATELLITE/GLOBAL_MODEL/SIMULATION), verification, notes |
| road_events | road_id, segment_ids (space/semicolon separated), state (OPEN/RESTRICTED/CLOSED), effective_from, effective_until, source, verification, notes |

## 4. Validation datasets

```
data/imports/validation/<area_id>/<dataset_id>/
  metadata.json                      {"name": ..., "event_date": ..., "observed_source": "Sentinel-1 ...", ...}
  observed.tif | observed.geojson    observed flood mask (e.g. Sentinel-1 SAR derived)
  modelled.tif | modelled.geojson    ARGUS modelled flood (depth raster or mask)
  aoi.geojson                        optional evaluation area
```
Registered dataset: `atbasar/atbasar-2024`. Status becomes READY when both masks exist; then
*Run validation* computes the metrics. Until then the UI shows **VALIDATION DATA NOT LOADED**.

## 5. External providers

Adapters (hydropost network, official forecasts, satellite, global models) implement polling with
status, mode (LIVE/CACHED/HISTORICAL/SIMULATION), last success, schedule and message. Without
configuration they report NOT_CONFIGURED and never fabricate values.
