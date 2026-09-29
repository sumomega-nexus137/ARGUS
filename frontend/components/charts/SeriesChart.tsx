"use client";

/** Minimal SVG time-series chart (area + line), with NOW and cursor markers. */
export function SeriesChart({ xs, series, nowX, cursorX, fmtX, height = 120, yLabel }: {
  xs: number[];
  series: { values: number[]; color: string; label: string; fill?: boolean }[];
  nowX: number | null;
  cursorX: number | null;
  fmtX: (x: number) => string;
  height?: number;
  yLabel?: string;
}) {
  const W = 400;
  const H = height;
  const P = { l: 36, r: 6, t: 8, b: 18 };
  if (!xs.length) return null;
  const x0 = xs[0];
  const x1 = xs[xs.length - 1];
  const maxY = Math.max(1, ...series.flatMap((s) => s.values));
  const X = (x: number) => P.l + ((x - x0) / (x1 - x0 || 1)) * (W - P.l - P.r);
  const Y = (y: number) => H - P.b - (y / maxY) * (H - P.t - P.b);
  const ticks = [0, maxY / 2, maxY];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={yLabel}>
      {ticks.map((v, i) => (
        <g key={i}>
          <line x1={P.l} x2={W - P.r} y1={Y(v)} y2={Y(v)} stroke="#1c2836" />
          <text x={P.l - 4} y={Y(v) + 3} fontSize={8.5} textAnchor="end" fill="#738396">{Math.round(v).toLocaleString()}</text>
        </g>
      ))}
      {xs.filter((_, i) => i % 6 === 0).map((x) => <text key={x} x={X(x)} y={H - 5} fontSize={8.5} textAnchor="middle" fill="#738396">{fmtX(x)}</text>)}
      {series.map((s) => {
        const d = s.values.map((v, i) => `${i ? "L" : "M"}${X(xs[i]).toFixed(1)},${Y(v).toFixed(1)}`).join("");
        return (
          <g key={s.label}>
            {s.fill && <path d={`${d}L${X(x1)},${Y(0)}L${X(x0)},${Y(0)}Z`} fill={s.color} opacity={0.15} />}
            <path d={d} fill="none" stroke={s.color} strokeWidth={1.6} />
          </g>
        );
      })}
      {nowX !== null && <line x1={X(nowX)} x2={X(nowX)} y1={P.t} y2={H - P.b} stroke="#dbe4ee" strokeWidth={1.2} />}
      {cursorX !== null && nowX !== null && Math.abs(cursorX - nowX) > 0.5 && <line x1={X(cursorX)} x2={X(cursorX)} y1={P.t} y2={H - P.b} stroke="#f59e2b" strokeDasharray="2 2" />}
    </svg>
  );
}
