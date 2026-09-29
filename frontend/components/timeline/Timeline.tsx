"use client";

import clsx from "clsx";
import { ChevronLeft, ChevronRight, Crosshair, Pause, Play, RotateCcw, TimerReset } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { Badge } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { offsetLabel } from "@/lib/format";
import { useInvalidateArea } from "@/lib/queries";
import { useUi } from "@/lib/store";

export function Timeline() {
  const tt = useTranslations("timeline");
  const { areaId, scenario, t, nowMin, fmt, accessTl, access, area } = useAreaCtx();
  const setCursor = useUi((s) => s.setCursor);
  const playing = useUi((s) => s.playing);
  const setPlaying = useUi((s) => s.setPlaying);
  const speed = useUi((s) => s.speed);
  const setSpeed = useUi((s) => s.setSpeed);
  const { can } = useAuth();
  const invalidate = useInvalidateArea();
  const track = useRef<HTMLDivElement>(null);
  const frames = useMemo(() => scenario?.frame_offsets_min ?? [], [scenario]);
  const start = frames[0] ?? 0;
  const end = frames[frames.length - 1] ?? 1;
  const pos = (m: number) => `${((m - start) / (end - start)) * 100}%`;

  const step = useCallback((dir: 1 | -1) => {
    if (!frames.length || t === null) return;
    const idx = frames.findIndex((f) => f > t + 0.5);
    let i = dir === 1 ? (idx === -1 ? frames.length - 1 : idx) : [...frames].reverse().findIndex((f) => f < t - 0.5);
    if (dir === -1) i = i === -1 ? 0 : frames.length - 1 - i;
    setCursor(frames[Math.max(0, Math.min(frames.length - 1, i))]);
  }, [frames, t, setCursor]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const cur = useUi.getState().cursor ?? nowMin ?? start;
      const next = frames.find((f) => f > cur + 0.5);
      if (next === undefined) { setPlaying(false); return; }
      setCursor(next);
    }, 1400 / speed);
    return () => clearInterval(id);
  }, [playing, speed, frames, nowMin, start, setCursor, setPlaying]);

  const fromPointer = (clientX: number) => {
    const r = track.current?.getBoundingClientRect();
    if (!r || !frames.length) return;
    const m = start + ((clientX - r.left) / r.width) * (end - start);
    const nearest = frames.reduce((a, b) => (Math.abs(b - m) < Math.abs(a - m) ? b : a), frames[0]);
    setCursor(nearest);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    if (e.key === "Home") setCursor(start);
    if (e.key === "End") setCursor(end);
    if (e.key === " ") { e.preventDefault(); setPlaying(!playing); }
  };

  const clock = async (body: object) => {
    await post(`/api/areas/${areaId}/clock`, body);
    setCursor(null);
    invalidate(areaId);
  };

  if (!scenario || t === null || nowMin === null) return <div className="h-[74px] border-t border-line bg-panel" />;
  const forecast = t > nowMin + 0.5;
  const closures = Object.entries(accessTl?.road_closures ?? {}).filter(([, m]) => m >= start && m <= end);
  const decisions = (access?.tasks ?? []).filter((x) => x.latest_departure !== null && x.latest_departure >= start && x.latest_departure <= end);

  return (
    <div className="shrink-0 border-t border-line bg-panel px-3 pb-2 pt-1.5" aria-label={tt("cursor")}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-0.5">
          <button aria-label={tt("prev")} title={tt("prev")} onClick={() => step(-1)} className="rounded p-1 text-ink-2 hover:bg-panel-2"><ChevronLeft className="h-4 w-4" /></button>
          <button aria-label={playing ? tt("pause") : tt("play")} title={playing ? tt("pause") : tt("play")} onClick={() => setPlaying(!playing)}
            className="rounded border border-accent/50 bg-accent/15 p-1 text-accent hover:bg-accent/25">{playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button>
          <button aria-label={tt("next")} title={tt("next")} onClick={() => step(1)} className="rounded p-1 text-ink-2 hover:bg-panel-2"><ChevronRight className="h-4 w-4" /></button>
          <button onClick={() => setCursor(null)} className="ml-1 flex items-center gap-1 rounded border border-line-2 px-1.5 py-0.5 text-[11px] font-semibold text-ink-2 hover:bg-panel-2">
            <Crosshair className="h-3.5 w-3.5" />{tt("followNow")}
          </button>
          <label className="ml-1 flex items-center gap-1 text-[11px] text-muted">
            {tt("speed")}
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="h-6 rounded border border-line-2 bg-bg px-1 text-[11px] text-ink">
              {[0.5, 1, 2, 4].map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
          </label>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="tabular text-xl font-bold">{fmt(t)}</span>
          <span className="tabular text-xs text-muted">{offsetLabel(t - nowMin)}</span>
          <Badge tone={forecast ? "warn" : "info"}>{forecast ? tt("forecast") : Math.abs(t - nowMin) < 0.5 ? tt("now") : tt("analysis")}</Badge>
          {forecast && <span className="hidden text-[10.5px] text-muted xl:inline">{tt("forecastNote")}</span>}
        </div>
        {area?.clock_mode !== "LIVE" && can("plan_edit") && (
          <div className="ml-auto flex items-center gap-1" title={tt("clockHint")}>
            <span className="hidden text-[10.5px] uppercase tracking-wider text-sim 2xl:inline">{tt("clockHint")}</span>
            <button onClick={() => clock({ advance_min: 30 })} className="flex items-center gap-1 rounded border border-sim/40 px-1.5 py-0.5 text-[11px] font-semibold text-sim hover:bg-sim/10">
              <TimerReset className="h-3.5 w-3.5" />{tt("advanceClock")}
            </button>
            <button onClick={() => clock({ reset: true })} aria-label={tt("resetClock")} title={tt("resetClock")} className="rounded border border-line-2 p-1 text-muted hover:bg-panel-2">
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
      <div
        ref={track}
        role="slider"
        tabIndex={0}
        aria-label={tt("cursor")}
        aria-valuemin={start}
        aria-valuemax={end}
        aria-valuenow={t}
        aria-valuetext={`${fmt(t)} ${forecast ? tt("forecast") : tt("analysis")}`}
        onKeyDown={onKey}
        onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); fromPointer(e.clientX); }}
        onPointerMove={(e) => { if (e.buttons === 1) fromPointer(e.clientX); }}
        className="relative mt-1.5 h-9 cursor-pointer select-none"
      >
        {/* observed / analysis part */}
        <div className="absolute top-3 h-2 rounded-l-[2px] bg-accent/35" style={{ left: 0, width: pos(nowMin) }} />
        {/* forecast part */}
        <div className="absolute top-3 h-2 rounded-r-[2px] bg-[repeating-linear-gradient(90deg,rgba(245,158,43,.45)_0_6px,transparent_6px_10px)]" style={{ left: pos(nowMin), right: 0 }} />
        <div className="absolute left-0 top-[-2px] text-[9.5px] font-bold tracking-wider text-accent">{tt("observed")} / {tt("analysis")}</div>
        <div className="absolute right-0 top-[-2px] text-[9.5px] font-bold tracking-wider text-warn">{tt("forecast")}</div>
        {frames.map((f) => (
          <div key={f} className="absolute top-5 h-1.5 w-px bg-line-2" style={{ left: pos(f) }}>
            {f % 180 === 0 && <span className="tabular absolute left-1/2 top-1.5 -translate-x-1/2 text-[9.5px] text-muted">{fmt(f)}</span>}
          </div>
        ))}
        {closures.map(([road, m]) => (
          <div key={road} title={tt("roadClosure", { road })} className="absolute top-1 -translate-x-1/2" style={{ left: pos(m) }}>
            <div className="h-0 w-0 border-x-[4px] border-t-[6px] border-x-transparent border-t-crit" />
          </div>
        ))}
        {decisions.map((d) => (
          <div key={d.code} title={`${d.code} ${fmt(d.latest_departure)}`} className="absolute top-2.5 h-3 w-[2px] -translate-x-1/2 bg-warn" style={{ left: pos(d.latest_departure as number) }} />
        ))}
        <div className="absolute top-0 h-7 w-[2px] -translate-x-1/2 bg-ink" style={{ left: pos(nowMin) }}>
          <span className="absolute -top-0.5 left-1 whitespace-nowrap text-[9.5px] font-extrabold tracking-wider text-ink">{tt("now")}</span>
        </div>
        <div className={clsx("absolute top-[7px] h-5 w-3 -translate-x-1/2 rounded-[2px] border-2 shadow", forecast ? "border-warn bg-warn/40" : "border-accent bg-accent/40")} style={{ left: pos(t) }} />
      </div>
    </div>
  );
}
