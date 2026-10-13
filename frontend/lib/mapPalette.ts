import type * as ML from "maplibre-gl";

import type { Theme } from "@/lib/theme";

/** Map colours per UI theme. MapLibre paint cannot read CSS variables, so the palette is literal. */
export interface MapPalette {
  bg: string;
  hillshade: { exaggeration: number; shadow: string; highlight: string; accent: string };
  carto: { opacity: number; brightnessMax: number; saturation: number };
  sector: string;
  waterFill: string;
  waterFillOpacity: number;
  waterLine: string;
  river: string;
  riverOpacity: number;
  extent: string;
  water3d: string;
  roadCase: string;
  roadOpen: string;
  roadHighlight: string;
  buildings: [string, string, string, string];
  sky: { sky: string; horizon: string; fog: string };
  lightIntensity: number;
}

export const MAP_PALETTE: Record<Theme, MapPalette> = {
  light: {
    bg: "#eef0ea",
    hillshade: { exaggeration: 0.42, shadow: "#8e9a98", highlight: "#ffffff", accent: "#c7cfca" },
    carto: { opacity: 0.85, brightnessMax: 1, saturation: -0.35 },
    sector: "#4f7a8c",
    waterFill: "#9fcaf0",
    waterFillOpacity: 0.75,
    waterLine: "#5b9fdc",
    river: "#3d8ad6",
    riverOpacity: 0.7,
    extent: "#174f96",
    water3d: "#2f86d8",
    roadCase: "#ffffff",
    roadOpen: "#8a97a3",
    roadHighlight: "#0f9d93",
    buildings: ["#dcd6cc", "#cfc7ba", "#bfb5a6", "#ada292"],
    sky: { sky: "#bcd9f2", horizon: "#e8f1f8", fog: "#eef0ea" },
    lightIntensity: 0.3,
  },
  dark: {
    bg: "#0c1219",
    hillshade: { exaggeration: 0.55, shadow: "#05080c", highlight: "#3a4a5c", accent: "#1d2835" },
    carto: { opacity: 0.55, brightnessMax: 0.45, saturation: -0.6 },
    sector: "#7aa2c7",
    waterFill: "#2a6fb0",
    waterFillOpacity: 0.35,
    waterLine: "#3d8fd6",
    river: "#5fb4ff",
    riverOpacity: 0.35,
    extent: "#c8ecff",
    water3d: "#2f86d8",
    roadCase: "#05080c",
    roadOpen: "#8aa2b8",
    roadHighlight: "#3fb3ff",
    buildings: ["#2b3746", "#36475b", "#425a74", "#4f6d8c"],
    sky: { sky: "#0d1b2c", horizon: "#22384f", fog: "#0c1219" },
    lightIntensity: 0.38,
  },
};

export function roadLineColor(p: MapPalette): ML.ExpressionSpecification {
  return ["case", ["boolean", ["feature-state", "hl"], false], p.roadHighlight,
    ["match", ["coalesce", ["feature-state", "state"], 0], 2, "#e0393e", 1, "#ee7d14", p.roadOpen]];
}

export function buildingColor(p: MapPalette): ML.ExpressionSpecification {
  return ["case", [">", ["coalesce", ["feature-state", "depth"], 0], 5],
    ["interpolate", ["linear"], ["coalesce", ["feature-state", "depth"], 0], 10, "#f2c14e", 50, "#f59e2b", 100, "#ef6b3b", 200, "#c81d3d"],
    ["interpolate", ["linear"], ["get", "height_m"], 3, p.buildings[0], 9, p.buildings[1], 18, p.buildings[2], 30, p.buildings[3]]];
}

/** Re-colour an existing map in place (theme switch) — no reload, camera and data stay. */
export function applyMapPalette(m: ML.Map, p: MapPalette): void {
  type Prop = Parameters<ML.Map["setPaintProperty"]>[1];
  const set = (layer: string, prop: Prop, value: Parameters<ML.Map["setPaintProperty"]>[2]) => {
    if (m.getLayer(layer)) m.setPaintProperty(layer, prop, value);
  };
  set("bg", "background-color", p.bg);
  set("hillshade", "hillshade-exaggeration", p.hillshade.exaggeration);
  set("hillshade", "hillshade-shadow-color", p.hillshade.shadow);
  set("hillshade", "hillshade-highlight-color", p.hillshade.highlight);
  set("hillshade", "hillshade-accent-color", p.hillshade.accent);
  set("carto", "raster-opacity", p.carto.opacity);
  set("carto", "raster-brightness-max", p.carto.brightnessMax);
  set("carto", "raster-saturation", p.carto.saturation);
  set("sectors-fill", "fill-color", p.sector);
  set("sectors-line", "line-color", p.sector);
  set("water-fill", "fill-color", p.waterFill);
  set("water-fill", "fill-opacity", p.waterFillOpacity);
  set("water-line", "line-color", p.waterLine);
  set("river", "line-color", p.river);
  set("river", "line-opacity", p.riverOpacity);
  set("extent", "line-color", p.extent);
  set("water-3d", "fill-extrusion-color", p.water3d);
  set("roads-case", "line-color", p.roadCase);
  set("roads-line", "line-color", roadLineColor(p));
  set("buildings", "fill-extrusion-color", buildingColor(p));
}
