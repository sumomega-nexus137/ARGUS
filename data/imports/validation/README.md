# Validation datasets

Place real data for the registered dataset here:

```
atbasar/atbasar-2024/
  metadata.json          {"name": "Atbasar 2024 flood", "event_date": "2024-04-..", "observed_source": "Sentinel-1 ..."}
  observed.tif|geojson   observed flood mask
  modelled.tif|geojson   ARGUS modelled flood (depth or mask)
  aoi.geojson            optional
```

Until both masks exist the Validation screen shows **VALIDATION DATA NOT LOADED** and no metric is
displayed. Metrics are always computed from these files — never entered by hand.
