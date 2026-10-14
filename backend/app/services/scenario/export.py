"""Export a scenario as precomputed GeoTIFF depth rasters + manifest.json (the raster-manifest contract).

Demonstrates the exact format the external modelling pipeline must deliver; the exported folder can be
registered as a ``raster_manifest`` scenario to prove the demo provider is replaceable without code changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from sqlalchemy.orm import Session

from app.services.scenario.runtime import current_scenario, runtime_for


def export_raster_manifest(db: Session, area_id: str, out_dir: Path, members: list[str] | None = None) -> dict:
    sc = current_scenario(db, area_id)
    rt = runtime_for(sc)
    grid = rt.provider.grid()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"crs": grid.crs, "bankfull_cm": sc.parameters.get("bankfull_cm"), "members": [],
                "source": f"exported from {sc.id}", "mode": sc.mode}
    for mid in members or rt.members_order:
        frames = []
        for off in sc.frame_offsets_min:
            depth = rt.provider.depth_grid(mid, float(off))
            rel = Path(mid) / f"depth_{off:+05d}.tif"
            p = out_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(p, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="float32",
                               crs=grid.crs, transform=grid.transform, compress="deflate", nodata=0.0) as dst:
                dst.write(np.where(depth > 0, depth, 0).astype("float32"), 1)
                dst.update_tags(MODE=sc.mode, SCENARIO=sc.id, MEMBER=mid, OFFSET_MIN=str(off))
            frames.append({"offset_min": off, "depth_path": str(rel)})
        manifest["members"].append({"id": mid, "label": mid, "gauge": [[t, s] for t, s in rt.provider.gauge_series(mid)],
                                    "frames": frames})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {"manifest": str(out_dir / "manifest.json"), "members": len(manifest["members"])}
