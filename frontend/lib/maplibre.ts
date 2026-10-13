"use client";

import * as maplibregl from "maplibre-gl";

import { BASE_PATH } from "./staticDemo";

let configured = false;

/** MapLibre configured to load its worker same-origin from /public/maplibre (see scripts/copy-maplibre-worker.mjs). */
export function getMaplibre(): typeof maplibregl {
  if (!configured && typeof window !== "undefined") {
    maplibregl.setWorkerUrl(new URL(`${BASE_PATH}/maplibre/maplibre-gl-worker.mjs`, window.location.origin).href);
    configured = true;
  }
  return maplibregl;
}

export type { maplibregl };
