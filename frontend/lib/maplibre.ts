"use client";

import * as maplibregl from "maplibre-gl";

let configured = false;

/** MapLibre configured to load its worker same-origin from /public/maplibre (see scripts/copy-maplibre-worker.mjs). */
export function getMaplibre(): typeof maplibregl {
  if (!configured && typeof window !== "undefined") {
    maplibregl.setWorkerUrl(new URL("/maplibre/maplibre-gl-worker.mjs", window.location.origin).href);
    configured = true;
  }
  return maplibregl;
}

export type { maplibregl };
