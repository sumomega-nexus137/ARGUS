"use client";

import { useTranslations } from "use-intl";

import { TONE_HEX, toneOf } from "@/lib/status";
import type { TaskWindowRow } from "@/lib/types";

/** Action-window chart: per task, time from now until the window closes, with planned and latest safe departures. */
export function WindowGantt({ tasks, asOf, horizon, closures, fmt, onSelect, selected }: {
  tasks: TaskWindowRow[]; asOf: number; horizon: number; closures: Record<string, number>; fmt: (m: number) => string;
  onSelect: (code: string) => void; selected: string | null;
}) {
  const t = useTranslations("windows");
  const rows = tasks.filter((x) => x.deadline !== null || x.latest_departure !== null || x.planned_departure !== null);
  const end = Math.min(horizon, Math.max(asOf + 240, ...rows.map((r) => (r.deadline ?? asOf) + 30)));
  const W = 520;
  const rowH = 20;
  const P = { l: 44, r: 8, t: 18 };
  const H = P.t + rows.length * rowH + 16;
  const X = (m: number) => P.l + ((Math.min(Math.max(m, asOf), end) - asOf) / (end - asOf || 1)) * (W - P.l - P.r);
  const ticks: number[] = [];
  const stepM = end - asOf > 600 ? 120 : 60;
  for (let m = Math.ceil(asOf / stepM) * stepM; m <= end; m += stepM) ticks.push(m);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("gantt")}>
        {ticks.map((m) => (
          <g key={m}>
            <line x1={X(m)} x2={X(m)} y1={P.t - 4} y2={H - 14} stroke="#1c2836" />
            <text x={X(m)} y={P.t - 7} textAnchor="middle" fontSize={8.5} fill="#738396">{fmt(m)}</text>
          </g>
        ))}
        {Object.entries(closures).filter(([, m]) => m > asOf && m < end).map(([road, m]) => (
          <g key={road}>
            <line x1={X(m)} x2={X(m)} y1={P.t - 2} y2={H - 14} stroke="#ef4d4d" strokeDasharray="3 2" opacity={0.7} />
            <text x={X(m) + 2} y={H - 4} fontSize={8} fill="#ef4d4d">{road}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = P.t + i * rowH;
          const tone = toneOf(r.window_status || "NO_DEADLINE");
          const color = TONE_HEX[tone];
          return (
            <g key={r.code} onClick={() => onSelect(r.code)} style={{ cursor: "pointer" }}>
              {selected === r.code && <rect x={0} y={y} width={W} height={rowH} fill="#3fb3ff" opacity={0.08} />}
              <text x={4} y={y + 13} fontSize={10} fontWeight={700} fill="#dbe4ee">{r.code}</text>
              {r.deadline !== null && (
                <rect x={X(asOf)} y={y + 6} width={Math.max(1, X(r.deadline) - X(asOf))} height={8} fill={color} opacity={0.22} rx={1} />
              )}
              {r.latest_departure !== null && (
                <rect x={X(asOf)} y={y + 6} width={Math.max(1, X(r.latest_departure) - X(asOf))} height={8} fill={color} opacity={0.55} rx={1} />
              )}
              {r.deadline !== null && <rect x={X(r.deadline) - 1} y={y + 3} width={2.5} height={14} fill="#ef4d4d" />}
              {r.latest_departure !== null && <path d={`M${X(r.latest_departure)},${y + 3} l5,7 l-5,7 l-5,-7z`} fill={color} stroke="#0a0e13" strokeWidth={0.8} />}
              {r.planned_departure !== null && r.planned_departure >= asOf && (
                <circle cx={X(r.planned_departure)} cy={y + 10} r={4} fill="#0a0e13" stroke="#dbe4ee" strokeWidth={1.6} />
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-3 text-[10.5px] text-muted">
        <span className="flex items-center gap-1"><svg width="10" height="10"><circle cx="5" cy="5" r="3.5" fill="none" stroke="#dbe4ee" strokeWidth="1.5" /></svg>{t("legendPlanned")}</span>
        <span className="flex items-center gap-1"><svg width="10" height="12"><path d="M5,0 l5,6 l-5,6 l-5,-6z" fill="#f59e2b" /></svg>{t("legendLatest")}</span>
        <span className="flex items-center gap-1"><i className="inline-block h-3 w-0.5 bg-crit" />{t("legendDeadline")}</span>
      </figcaption>
    </figure>
  );
}
