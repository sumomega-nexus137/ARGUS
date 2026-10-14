// Shared handle to the operational MapLibre map so overlay controls (camera, fit) can act on it without prop drilling.
import type * as ML from "maplibre-gl";

let current: ML.Map | null = null;
let home: { center: [number, number]; zoom: number; bbox?: [number, number, number, number] } | null = null;

export const mapHandle = {
  set(m: ML.Map | null, h?: typeof home) { current = m; if (h !== undefined) home = h; },
  get: () => current,
  home: () => home,
};
