# ARGUS real-data pipeline

This repository now contains an automated acquisition/pre-processing pipeline for the primary real-data pilot: **Atbasar / Zhabai, 2024**.

Run locally:

    pip install -r scripts/realdata/requirements.txt
    python scripts/realdata/atbasar_pipeline.py --output data/realdata/atbasar/generated

The GitHub Actions workflow `.github/workflows/realdata-atbasar.yml` runs automatically when the real-data pipeline/config changes and uploads the generated pack as the artifact **argus-atbasar-realdata**.

## What the artifact contains

- Copernicus GLO-30 terrain and slope in EPSG:32642;
- normalized OSM routable roads/nodes;
- OSM buildings, waterways, bridges/culverts and candidate critical facilities;
- selected Sentinel-1 pre-flood and flood-period VV/VH scenes clipped to the AOI;
- JRC long-term surface-water occurrence where available;
- automatic Sentinel-1 2024 observed-flood baseline and QC figure;
- WorldPop 2024 100 m population raster where available;
- official curated 2024 Zhabai observations and event timeline;
- provenance sidecars and SHA-256 manifest;
- validation folder with `observed.tif` but deliberately no `modelled.tif` yet.

## Scientific gates

The generated SAR flood mask is **not automatically accepted as ground truth**. It is marked `REQUIRES_QC` because SAR thresholding can confuse wet soil, shadow, ice and other low-backscatter surfaces with water.

The curated hydrology table intentionally keeps different local gauge/reference descriptions separate. Values from bridge references and other local operational references must not be merged into a single hydrograph unless datum equivalence is established.

OSM facility criticality is a placeholder/default and is not an official emergency-service priority.

Validation metrics remain unavailable until:
1. the Sentinel-derived observation mask passes visual QC; and
2. a model-generated `modelled.tif` is produced on a compatible grid.

The next modelling step is a terrain/HAND-like scenario pipeline calibrated against the 2024 Sentinel observation. ARGUS must not be described as a full hydrodynamic digital twin unless a validated hydraulic model is actually integrated.
