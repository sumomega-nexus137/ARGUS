"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type MapMode = "2d" | "3d";

export interface LayerToggles {
  flood: boolean;
  extent: boolean;
  buildings: boolean;
  roads: boolean;
  facilities: boolean;
  sites: boolean;
  sectors: boolean;
  basemap: boolean;
  hillshade: boolean;
  waterFx: boolean;
  labels: boolean;
}

interface UiState {
  cursor: number | null; // timeline cursor, minutes relative to scenario reference (null = follow NOW)
  playing: boolean;
  speed: number;
  mapMode: MapMode;
  layers: LayerToggles;
  selectedTask: string | null;
  highlightRoads: string[];
  setCursor: (m: number | null) => void;
  setPlaying: (p: boolean) => void;
  setSpeed: (s: number) => void;
  setMapMode: (m: MapMode) => void;
  toggleLayer: (k: keyof LayerToggles) => void;
  setSelectedTask: (c: string | null) => void;
  setHighlightRoads: (r: string[]) => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      cursor: null,
      playing: false,
      speed: 1,
      mapMode: "2d",
      layers: {
        flood: true, extent: true, buildings: true, roads: true, facilities: true, sites: true, sectors: false,
        basemap: false, hillshade: true, waterFx: true, labels: true,
      },
      selectedTask: null,
      highlightRoads: [],
      setCursor: (cursor) => set({ cursor }),
      setPlaying: (playing) => set({ playing }),
      setSpeed: (speed) => set({ speed }),
      setMapMode: (mapMode) => set({ mapMode }),
      toggleLayer: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),
      setSelectedTask: (selectedTask) => set({ selectedTask }),
      setHighlightRoads: (highlightRoads) => set({ highlightRoads }),
    }),
    {
      name: "argus.ui",
      partialize: (s) => ({ mapMode: s.mapMode, layers: s.layers, speed: s.speed }),
    },
  ),
);
