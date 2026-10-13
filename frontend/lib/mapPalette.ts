import type * as ML from "maplibre-gl";

/** Map colours (MapLibre paint cannot read CSS variables, so the palette is literal). */
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

export const MAP_PALETTE: MapPalette = {
  bg: "#eef1ec",
  hillshade: { exaggeration: 0.45, shadow: "#8b9a9c", highlight: "#ffffff", accent: "#c5cfcc" },
  carto: { opacity: 0.9, brightnessMax: 1, saturation: -0.3 },
  sector: "#3f6f97",
  waterFill: "#a6cdf0",
  waterFillOpacity: 0.8,
  waterLine: "#4f97da",
  river: "#2f80d0",
  riverOpacity: 0.75,
  extent: "#0f4a99",
  water3d: "#2f86d8",
  roadCase: "#ffffff",
  roadOpen: "#7f8fa1",
  roadHighlight: "#d6338a",
  buildings: ["#dad5cb", "#cdc5b8", "#bdb3a4", "#aca191"],
  sky: { sky: "#b9d8f2", horizon: "#e6f0f8", fog: "#eef1ec" },
  lightIntensity: 0.3,
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
