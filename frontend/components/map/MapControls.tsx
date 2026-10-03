"use client";

import clsx from "clsx";
import { Box, Expand, Home, Layers, RotateCw, Square } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { Badge } from "@/components/ui/primitives";
import { mapHandle } from "@/lib/mapRef";
import { useUi, type LayerToggles } from "@/lib/store";

const GROUPS: { key: string; items: (keyof LayerToggles)[] }[] = [
  { key: "groupFlood", items: ["flood", "extent", "waterFx"] },
  { key: "groupCity", items: ["buildings", "roads", "labels", "facilities", "sites", "sectors"] },
  { key: "groupBase", items: ["hillshade", "basemap"] },
];

const DEPTH_STOPS = [
  { c: "#8cd7ff", l: "0.05" },
  { c: "#56b4fa", l: "0.3" },
  { c: "#2882eb", l: "0.7" },
  { c: "#145acd", l: "1.2" },
  { c: "#0c37a0", l: "2.0" },
  { c: "#081e6e", l: "3.5+" },
];

export function MapControls() {
  const t = useTranslations("map");
  const tr = useTranslations("road");
  const tm = useTranslations("mode");
  const { scenario, t: time, nowMin, area } = useAreaCtx();
  const ta = useTranslations("app");
  const tt = useTranslations("timeline");
  const mapMode = useUi((s) => s.mapMode);
  const setMapMode = useUi((s) => s.setMapMode);
  const layers = useUi((s) => s.layers);
  const toggle = useUi((s) => s.toggleLayer);
  const [open, setOpen] = useState(false);
  const forecast = time !== null && nowMin !== null && time > nowMin + 0.5;
  // LIVE only for a live clock with a live scenario; the 2024 reconstruction is HISTORICAL REPLAY; exercises are SIMULATION
  const modeKey = area?.clock_mode === "LIVE" && scenario?.mode === "LIVE" ? "LIVE" : scenario?.mode === "HISTORICAL" ? "HISTORICAL" : "SIMULATION";
  const modeLabel = modeKey === "LIVE" ? tm("LIVE") : modeKey === "HISTORICAL" ? ta("historicalClock") : tm("SIMULATION");
  const cam = (kind: "home" | "fit" | "rotate") => {
    const m = mapHandle.get();
    const h = mapHandle.home();
    if (!m || !h) return;
    if (kind === "rotate") m.easeTo({ bearing: m.getBearing() + 90, duration: 900 });
    else if (kind === "fit" && h.bbox) m.fitBounds([[h.bbox[0], h.bbox[1]], [h.bbox[2], h.bbox[3]]], { padding: 40, pitch: mapMode === "3d" ? 55 : 0, duration: 1200 });
    else m.easeTo({ center: h.center, zoom: mapMode === "3d" ? 13.6 : h.zoom, pitch: mapMode === "3d" ? 60 : 0, bearing: mapMode === "3d" ? -20 : 0, duration: 1100 });
  };
  return (
    <>
      <div className="absolute left-3 right-14 top-3 z-10 flex flex-wrap items-start gap-2">
        <div role="group" aria-label="2D / 3D" className="flex overflow-hidden rounded-[3px] border border-line-2 bg-panel/95">
          <button aria-pressed={mapMode === "2d"} onClick={() => setMapMode("2d")} className={clsx("flex h-7 items-center gap-1 px-2.5 text-xs font-bold", mapMode === "2d" ? "bg-accent/20 text-accent" : "text-ink-2 hover:bg-panel-2")}>
            <Square className="h-3.5 w-3.5" />{t("mode2d")}
          </button>
          <button aria-pressed={mapMode === "3d"} onClick={() => setMapMode("3d")} className={clsx("flex h-7 items-center gap-1 border-l border-line-2 px-2.5 text-xs font-bold", mapMode === "3d" ? "bg-accent/20 text-accent" : "text-ink-2 hover:bg-panel-2")}>
            <Box className="h-3.5 w-3.5" />{t("mode3d")}
          </button>
        </div>
        <div className="relative">
          <button aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex h-7 items-center gap-1.5 rounded-[3px] border border-line-2 bg-panel/95 px-2.5 text-xs font-semibold text-ink-2 hover:bg-panel-2">
            <Layers className="h-3.5 w-3.5" />{t("layers")}
          </button>
          {open && (
            <div className="absolute left-0 top-8 w-64 rounded-[4px] border border-line-2 bg-panel/98 p-2 shadow-xl backdrop-blur">
              {GROUPS.map((g) => (
                <div key={g.key} className="mb-1">
                  <div className="px-1.5 pb-0.5 pt-1 text-[9.5px] font-bold uppercase tracking-wider text-muted">{t(g.key)}</div>
                  {g.items.map((k) => (
                    <label key={k} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-panel-2">
                      <span className={clsx("relative inline-flex h-3.5 w-6 shrink-0 rounded-full border transition-colors", layers[k] ? "border-accent bg-accent/40" : "border-line-2 bg-bg")}>
                        <span className={clsx("absolute top-[1px] h-2.5 w-2.5 rounded-full transition-all", layers[k] ? "left-[11px] bg-accent" : "left-[1px] bg-muted")} />
                      </span>
                      <input type="checkbox" checked={layers[k]} onChange={() => toggle(k)} className="sr-only" />
                      <span>{t(k)}</span>
                      {k === "waterFx" && <span className="ml-auto rounded-sm border border-line-2 px-1 text-[9px] text-muted">{t("fx")}</span>}
                    </label>
                  ))}
                </div>
              ))}
              <p className="mt-1 border-t border-line pt-1.5 text-[10.5px] leading-snug text-muted">{t("waterFxNote")}</p>
              {mapMode === "3d" && <p className="mt-1 text-[10.5px] leading-snug text-muted">{t("heightNote")}</p>}
              {layers.basemap && <p className="mt-1 text-[10.5px] leading-snug text-warn">{t("basemapNote")}</p>}
            </div>
          )}
        </div>
        <div role="group" aria-label={t("camera")} className="flex overflow-hidden rounded-[3px] border border-line-2 bg-panel/95">
          <button title={t("resetView")} aria-label={t("resetView")} onClick={() => cam("home")} className="grid h-7 w-7 place-items-center text-ink-2 hover:bg-panel-2"><Home className="h-3.5 w-3.5" /></button>
          <button title={t("fitArea")} aria-label={t("fitArea")} onClick={() => cam("fit")} className="grid h-7 w-7 place-items-center border-l border-line-2 text-ink-2 hover:bg-panel-2"><Expand className="h-3.5 w-3.5" /></button>
          <button title={t("rotate")} aria-label={t("rotate")} onClick={() => cam("rotate")} className="grid h-7 w-7 place-items-center border-l border-line-2 text-ink-2 hover:bg-panel-2"><RotateCw className="h-3.5 w-3.5" /></button>
        </div>
        {scenario && (
          <div className="flex items-center gap-1 rounded-[4px] bg-panel/95 p-0.5 shadow-lg">
            <span className={clsx("flex h-7 items-center gap-1.5 whitespace-nowrap rounded-[3px] border px-2 text-[11px] font-extrabold tracking-wider",
              modeKey === "LIVE" ? "border-ok/60 bg-ok/15 text-ok" : modeKey === "HISTORICAL" ? "border-accent/60 bg-accent/15 text-accent" : "border-sim/60 bg-sim/15 text-sim")}>
              <span className={clsx("h-2 w-2 rounded-full", modeKey === "LIVE" ? "animate-pulse bg-ok" : modeKey === "HISTORICAL" ? "bg-accent" : "bg-sim")} />{modeLabel}
            </span>
            <Badge tone={forecast ? "warn" : "info"}>{forecast ? tt("forecast") : tt("analysis")}</Badge>
          </div>
        )}
      </div>
      <div className="pointer-events-none absolute bottom-7 left-3 z-10 rounded-[4px] border border-line bg-panel/90 p-2 text-[10.5px]">
        <div className="mb-1 font-semibold uppercase tracking-wider text-muted">{t("depth")}</div>
        <div className="flex items-end gap-0.5">
          {DEPTH_STOPS.map((s) => (
            <div key={s.l} className="text-center">
              <div className="h-2.5 w-7" style={{ background: s.c }} />
              <div className="tabular text-muted">{s.l}</div>
            </div>
          ))}
        </div>
        <div className="mt-1.5 font-semibold uppercase tracking-wider text-muted">{t("roadStates")}</div>
        <div className="flex flex-wrap gap-x-2 gap-y-0.5">
          <span className="flex items-center gap-1"><i className="inline-block h-1 w-4 bg-[#8aa2b8]" />{tr("OPEN")}</span>
          <span className="flex items-center gap-1"><i className="inline-block h-1 w-4 bg-[#f59e2b]" />{tr("RESTRICTED")}</span>
          <span className="flex items-center gap-1"><i className="inline-block h-1 w-4 bg-[repeating-linear-gradient(90deg,#ef4d4d_0_4px,#ffe1e1_4px_7px)]" />{tr("CLOSED")}</span>
        </div>
        <div className="mt-1 flex items-center gap-1"><i className="inline-block h-2.5 w-2.5 bg-[#f59e2b]" />{t("buildingFlooded")}</div>
        {layers.waterFx && <div className="mt-1 max-w-[210px] text-[9.5px] leading-tight text-muted">{t("waterFxNote")}</div>}
      </div>
    </>
  );
}
