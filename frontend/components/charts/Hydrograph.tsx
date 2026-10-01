"use client";

import { useTranslations } from "use-intl";

export interface HydroStation {
  station_id: string;
  thresholds: { bankfull: number | null; watch: number | null; warning: number | null; critical: number | null };
  observations: { id: string; t_min: number; stage_cm: number; effective: boolean; excluded: boolean; conflict: string | null; source_type: string; verification: string; authority: string; source: string; observed_at?: string; mode?: string; future?: boolean; quality?: string | null; notes?: string | null }[];
  scenario_station?: boolean;
  provider?: string;
  members: Record<string, [number, number][]>;
  active_member: string;
  envelope: string[];
  envelope_low: [number, number][] | null;
  envelope_high: [number, number][] | null;
}

const W = 400;
const H = 210;
const PAD = { l: 34, r: 8, t: 10, b: 20 };

/** Official gauges without a forecast series (other datum / date-precision reports): list, never plotted on the
 * scenario stage axis. Records after the exercise clock are shown as hindsight. */
function ObservationList({ st, dateFmt }: { st: HydroStation; dateFmt: (iso: string) => string }) {
  const t = useTranslations("scenario");
  if (!st.observations.length) return <p className="text-[11px] text-muted">{t("noObservations")}</p>;
  return (
    <table className="w-full text-[11px] [&_td]:px-1">
      <tbody>
        {st.observations.map((o) => (
          <tr key={o.id} className={o.future ? "text-muted" : ""} title={o.notes || undefined}>
            <td className="tabular py-0.5">{o.observed_at ? dateFmt(o.observed_at) : "—"}</td>
            <td className="tabular font-semibold">{o.stage_cm} cm</td>
            <td className="truncate">{o.quality || o.source_type}</td>
            <td>{o.future ? t("hindsight") : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Hydrograph({ st, nowMin, cursor, fmt, dateFmt }: { st: HydroStation; nowMin: number; cursor: number; fmt: (m: number) => string; dateFmt?: (iso: string) => string }) {
  const t = useTranslations("scenario");
  const tt = useTranslations("timeline");
  const active = st.members[st.active_member] || [];
  const all = Object.values(st.members).flat();
  if (!all.length) return <ObservationList st={st} dateFmt={dateFmt || ((x) => x)} />;
  const xs = all.map((p) => p[0]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const inWin = st.observations.filter((o) => o.t_min >= Math.min(...xs) && o.t_min <= Math.max(...xs));
  const ys = [...all.map((p) => p[1]), ...inWin.map((o) => o.stage_cm), ...(st.thresholds.bankfull !== null ? [st.thresholds.bankfull] : [])];
  const y0 = Math.floor((Math.min(...ys) - 10) / 20) * 20;
  const y1 = Math.ceil((Math.max(...ys) + 10) / 20) * 20;
  const X = (m: number) => PAD.l + ((m - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => H - PAD.b - ((v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
  const path = (pts: [number, number][]) => pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
  const past = active.filter((p) => p[0] <= nowMin);
  const future = active.filter((p) => p[0] >= nowMin);
  const band = st.envelope_low && st.envelope_high
    ? `${path(st.envelope_high)}L${[...st.envelope_low].reverse().map((p) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("L")}Z`
    : null;
  const thr: [keyof HydroStation["thresholds"], string][] = [["bankfull", "#7aa2c7"], ["watch", "#e2c541"], ["warning", "#f59e2b"], ["critical", "#ef4d4d"]];
  const yTicks: number[] = [];
  for (let v = y0; v <= y1; v += (y1 - y0) > 200 ? 50 : 20) yTicks.push(v);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("hydrograph")}>
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} stroke="#1c2836" strokeWidth={1} />
            <text x={PAD.l - 4} y={Y(v) + 3} textAnchor="end" fontSize={8.5} fill="#738396">{v}</text>
          </g>
        ))}
        {[...new Set(active.map((p) => p[0]).filter((m) => Math.abs(m % 360) < 1e-6))].map((m) => (
          <text key={m} x={X(m)} y={H - 6} textAnchor="middle" fontSize={8.5} fill="#738396">{fmt(m)}</text>
        ))}
        <rect x={X(nowMin)} y={PAD.t} width={Math.max(0, X(x1) - X(nowMin))} height={H - PAD.t - PAD.b} fill="#f59e2b" opacity={0.05} />
        {thr.map(([k, c]) => {
          const v = st.thresholds[k];
          if (v === null || v < y0 || v > y1) return null;
          return (
            <g key={k}>
              <line x1={PAD.l} x2={W - PAD.r} y1={Y(v)} y2={Y(v)} stroke={c} strokeDasharray="4 3" strokeWidth={1} opacity={0.8} />
              <text x={W - PAD.r - 2} y={Y(v) - 2} textAnchor="end" fontSize={8} fill={c}>{t(`thresholds.${k}`)} {v}</text>
            </g>
          );
        })}
        {band && <path d={band} fill="#3fb3ff" opacity={0.13} />}
        {Object.entries(st.members).filter(([m]) => m !== st.active_member).map(([m, pts]) => (
          <path key={m} d={path(pts)} fill="none" stroke="#6c7f94" strokeWidth={0.8} opacity={0.45} />
        ))}
        <path d={path(past)} fill="none" stroke="#3fb3ff" strokeWidth={2} />
        <path d={path(future)} fill="none" stroke="#f59e2b" strokeWidth={2} strokeDasharray="5 3" />
        {inWin.map((o) => (
          <g key={o.id}>
            <circle cx={X(o.t_min)} cy={Y(o.stage_cm)} r={3.2}
              fill={o.effective ? (o.authority === "VERIFIED_FIELD" ? "#34c38f" : "#dbe4ee") : "none"}
              stroke={o.conflict ? "#f59e2b" : o.effective ? "#0a0e13" : "#a9b6c4"} strokeWidth={o.conflict ? 1.8 : 1}>
              <title>{`${fmt(o.t_min)} · ${o.stage_cm} cm · ${o.source} · ${o.verification}${o.excluded ? ` · ${t("excluded")}` : ""}`}</title>
            </circle>
          </g>
        ))}
        <line x1={X(nowMin)} x2={X(nowMin)} y1={PAD.t - 4} y2={H - PAD.b} stroke="#dbe4ee" strokeWidth={1.2} />
        <text x={X(nowMin) + 3} y={PAD.t + 3} fontSize={8.5} fontWeight={800} fill="#dbe4ee">{tt("now")}</text>
        {Math.abs(cursor - nowMin) > 0.5 && <line x1={X(cursor)} x2={X(cursor)} y1={PAD.t} y2={H - PAD.b} stroke="#f59e2b" strokeWidth={1} strokeDasharray="2 2" />}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted">
        <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-4 bg-accent" />{tt("analysis")}</span>
        <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-4 bg-[repeating-linear-gradient(90deg,#f59e2b_0_4px,transparent_4px_6px)]" />{tt("forecast")} · {st.active_member}</span>
        <span className="flex items-center gap-1"><i className="inline-block h-2 w-4 bg-accent/20" />{t("envelope")} ({st.envelope.join(", ") || "—"})</span>
        <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-full border border-warn" />{t("openConflict").split("—")[0]}</span>
      </figcaption>
    </figure>
  );
}
