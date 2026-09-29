"use client";

import clsx from "clsx";
import { Box, Layers, Square } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { Badge } from "@/components/ui/primitives";
import { useUi, type LayerToggles } from "@/lib/store";

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
  const { scenario, t: time, nowMin } = useAreaCtx();
  const tt = useTranslations("timeline");
  const mapMode = useUi((s) => s.mapMode);
  const setMapMode = useUi((s) => s.setMapMode);
  const layers = useUi((s) => s.layers);
  const toggle = useUi((s) => s.toggleLayer);
  const [open, setOpen] = useState(false);
  const forecast = time !== null && nowMin !== null && time > nowMin + 0.5;
  const items: (keyof LayerToggles)[] = ["flood", "extent", "buildings", "roads", "facilities", "sites", "sectors", "labels", "hillshade", "waterFx", "basemap"];
  return (
    <>
      <div className="absolute left-3 top-3 z-10 flex items-start gap-2">
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
            <div className="absolute left-0 top-8 w-60 rounded-[4px] border border-line-2 bg-panel p-2 shadow-xl">
              {items.map((k) => (
                <label key={k} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-panel-2">
                  <input type="checkbox" checked={layers[k]} onChange={() => toggle(k)} className="accent-[var(--color-accent)]" />
                  <span>{t(k)}</span>
                  {k === "waterFx" && <span className="ml-auto text-[10px] text-muted">{t("fx")}</span>}
                </label>
              ))}
              <p className="mt-1 border-t border-line pt-1.5 text-[10.5px] leading-snug text-muted">{t("waterFxNote")}</p>
              {layers.basemap && <p className="mt-1 text-[10.5px] leading-snug text-warn">{t("basemapNote")}</p>}
            </div>
          )}
        </div>
        {scenario && (
          <div className="flex items-center gap-1">
            <Badge tone="sim">{tm.has(scenario.mode) ? tm(scenario.mode) : scenario.mode}</Badge>
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
