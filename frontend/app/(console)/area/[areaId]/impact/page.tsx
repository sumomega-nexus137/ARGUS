"use client";

import { Calculator, FileQuestion, ListChecks } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { SeriesChart } from "@/components/charts/SeriesChart";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Badge, Button, Dialog, ErrorState, InlineNote, Loading, Metric, Panel } from "@/components/ui/primitives";
import { moneyRangeM, num, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useImpact } from "@/lib/queries";
import { useUi } from "@/lib/store";

export default function ImpactPage() {
  const { areaId, t, nowMin, fmt, impactTl, clearOverlays, setOverlays } = useAreaCtx();
  const ti = useTranslations("impact");
  const tc = useTranslations("common");
  const tf = useTranslations("facilityType");
  const tt = useTranslations("timeline");
  const tu = useTranslations("units");
  const { locale } = useLocale();
  const cursor = useUi((s) => s.cursor);
  const imp = useImpact(areaId, cursor, false);
  const [dlg, setDlg] = useState<null | "calc" | "assump" | "method">(null);
  const calc = useImpact(areaId, cursor, dlg !== null);

  useEffect(() => clearOverlays(), [clearOverlays]);
  useEffect(() => {
    const exposed = imp.data?.facilities.filter((f) => f.exposed) ?? [];
    setOverlays({ points: exposed.map((f) => ({ id: f.id, lon: f.lon, lat: f.lat, label: `${num(f.depth_m, 2, locale)} ${tu("m")}`, sub: pickName(f.names, locale), tone: "info" as const })) });
  }, [imp.data, setOverlays, locale]);

  const d = imp.data;
  const kind = d?.kind === "FORECAST" ? tt("forecast") : tt("analysis");
  return (
    <div className="space-y-3 p-3">
      <ScreenHeader screen="impact" right={d && <Badge tone={d.kind === "FORECAST" ? "warn" : "info"}>{ti("atTime", { time: fmt(t), kind })}</Badge>} />
      {imp.isLoading && <Loading />}
      {imp.isError && <ErrorState error={imp.error} onRetry={() => imp.refetch()} />}
      {d && (
        <>
          <Panel>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Metric label={ti("buildingsAffected")} value={num(d.buildings.affected, 0, locale)} sub={`/ ${num(d.buildings.total, 0, locale)}`} tone={d.buildings.affected ? "warn" : undefined} />
              <Metric label={ti("populationExposed")} value={num(d.population.exposed, 0, locale)}
                sub={`${ti("vulnerable")}: ${d.population.vulnerable_exposed === null ? ti("notAvailable") : num(d.population.vulnerable_exposed, 0, locale)}`} tone={d.population.exposed ? "warn" : undefined} />
              <Metric label={ti("facilitiesExposed")} value={d.facilities_exposed} tone={d.facilities_exposed ? "crit" : undefined} />
              <Metric label={ti("roadsClosed")} value={`${num(d.roads.km_closed, 1, locale)} km`} sub={`${ti("roadsFlooded")}: ${num(d.roads.km_flooded, 1, locale)} km`} />
              {d.economic.asset_exposure ? (
                <>
                  <Metric label={`${ti("assetExposure")} · ${ti("currencyM")}`} value={moneyRangeM(d.economic.asset_exposure)} sub={ti("range")} />
                  <Metric label={`${ti("expectedDamage")} · ${ti("currencyM")}`} value={moneyRangeM(d.economic.expected_damage)} sub={ti("range")} />
                </>
              ) : (
                <>
                  <Metric label={ti("floorAreaExposed")} value={`${num(d.economic.floor_area_exposed_m2 ?? 0, 0, locale)} m²`} sub={ti("exposureOnly")} />
                  <Metric label={ti("expectedDamage")} value={<span className="text-sm">{ti("notAvailable")}</span>} sub={ti("noValuation")} />
                </>
              )}
            </div>
            {d.economic.asset_exposure
              ? <InlineNote tone="sim" className="mt-3">{ti("exposureNotDamage")} · {ti("demoAssumptions")}</InlineNote>
              : <InlineNote tone="info" className="mt-3">{ti("exposureOnlyNote")} · {ti("populationMethod")}</InlineNote>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Button size="sm" icon={Calculator} onClick={() => setDlg("calc")}>{tc("showCalculation")}</Button>
              <Button size="sm" icon={ListChecks} onClick={() => setDlg("assump")}>{tc("showAssumptions")}</Button>
              <Button size="sm" icon={FileQuestion} onClick={() => setDlg("method")}>{tc("showMethodology")}</Button>
            </div>
          </Panel>
          {impactTl && (
            <Panel title={ti("overTime")}>
              <SeriesChart xs={impactTl.frame_offsets_min} nowX={nowMin} cursorX={t} fmtX={(x) => fmt(x)}
                series={[{ values: impactTl.frames.map((f) => f.buildings_affected), color: "#f59e2b", label: ti("buildingsAffected"), fill: true },
                  { values: impactTl.frames.map((f) => f.population_exposed / 10), color: "#3fb3ff", label: ti("populationExposed") }]} />
              <div className="mt-1 flex gap-3 text-[10.5px] text-muted">
                <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-4 bg-warn" />{ti("buildingsAffected")}</span>
                <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-4 bg-accent" />{ti("populationExposed")} ÷ 10</span>
              </div>
            </Panel>
          )}
          <Panel title={ti("byDepth")}>
            <div className="space-y-1">
              {d.buildings.by_depth_class.map((c) => {
                const max = Math.max(1, ...d.buildings.by_depth_class.map((x) => x.buildings));
                return (
                  <div key={c.min_m} className="flex items-center gap-2 text-xs">
                    <span className="tabular w-20 text-ink-2">{c.max_m === null ? ti("depthClassOpen", { min: c.min_m }) : ti("depthClass", { min: c.min_m, max: c.max_m })}</span>
                    <div className="h-3 flex-1 rounded-sm bg-panel-2"><div className="h-3 rounded-sm bg-water" style={{ width: `${(c.buildings / max) * 100}%` }} /></div>
                    <span className="tabular w-12 text-right">{num(c.buildings, 0, locale)}</span>
                  </div>
                );
              })}
            </div>
          </Panel>
          <Panel title={ti("bySector")}>
            <table className="w-full text-xs">
              <tbody>
                {Object.entries(d.sectors).map(([code, s]) => (
                  <tr key={code} className="border-t border-line/60">
                    <td className="py-1">{pickName(s.names, locale)}</td>
                    <td className="tabular text-right">{num(s.buildings_affected, 0, locale)}</td>
                    <td className="tabular text-right text-ink-2">{num(s.population_exposed, 0, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10.5px] text-muted">{ti("aggregatedNote")}</p>
          </Panel>
          <Panel title={ti("facilitiesExposed")}>
            <ul className="space-y-1 text-xs">
              {d.facilities.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-2 border-t border-line/60 pt-1">
                  <span className="min-w-0 truncate">{pickName(f.names, locale)} <span className="text-muted">· {tf.has(f.type) ? tf(f.type) : f.type}</span></span>
                  {f.exposed ? <Badge tone="crit">{ti("facilityDepth", { d: num(f.depth_m, 2, locale) })}</Badge> : <span className="text-muted">—</span>}
                </li>
              ))}
            </ul>
          </Panel>
        </>
      )}
      <Dialog open={dlg !== null} onClose={() => setDlg(null)} wide
        title={dlg === "calc" ? tc("calculation") : dlg === "assump" ? tc("assumptions") : tc("methodology")}>
        {calc.isLoading && <Loading />}
        {calc.data?.calculation && dlg === "calc" && (
          <table className="w-full text-xs">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
              <tr><th className="py-1">{ti("byUse")}</th><th>#</th><th>{ti("floorArea")}</th><th>{ti("unitValue")}</th><th>{ti("assetExposure")}</th><th>{ti("damageFraction")}</th><th>{ti("expectedDamage")}</th></tr>
            </thead>
            <tbody>
              {calc.data.calculation.rows.map((r) => (
                <tr key={r.use} className="tabular border-t border-line/60">
                  <td className="py-1">{ti.has(`use.${r.use}`) ? ti(`use.${r.use}`) : r.use}</td>
                  <td>{num(r.buildings, 0, locale)}</td>
                  <td>{num(r.floor_area_m2, 0, locale)}</td>
                  <td>{num(r.unit_value_kzt_m2[0], 0, locale)}–{num(r.unit_value_kzt_m2[1], 0, locale)}</td>
                  <td>{moneyRangeM(r.exposure)}</td>
                  <td>{num(r.mean_damage_fraction, 2, locale)}</td>
                  <td>{moneyRangeM(r.expected_damage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {calc.data?.calculation && dlg === "assump" && (
          <div className="space-y-3 text-xs">
            <InlineNote tone="sim">{ti("demoAssumptions")}</InlineNote>
            <table className="w-full">
              <tbody>
                {Object.entries(calc.data.calculation.assumptions.unit_value_kzt_m2).map(([k, v]) => (
                  <tr key={k} className="border-t border-line/60"><td className="py-1">{ti.has(`use.${k}`) ? ti(`use.${k}`) : k}</td><td className="tabular">{num(v[0], 0, locale)}–{num(v[1], 0, locale)} KZT/m²</td></tr>
                ))}
              </tbody>
            </table>
            <div>
              <div className="mb-1 font-semibold">{ti("curve")}</div>
              <SeriesChart xs={calc.data.calculation.assumptions.damage_curve.map((p) => p[0])} nowX={null} cursorX={null} fmtX={(x) => `${x} ${tu("m")}`} height={110}
                series={[{ values: calc.data.calculation.assumptions.damage_curve.map((p) => p[1] * 100), color: "#f59e2b", label: "%", fill: true }]} />
            </div>
          </div>
        )}
        {calc.data?.calculation && dlg === "method" && (
          <div className="space-y-2 text-xs">
            {Object.entries(calc.data.calculation.assumptions.methodology).filter(([k]) => k !== "limitations" && k !== "status").map(([k, v]) => (
              <p key={k}><b className="uppercase text-muted">{k}</b> — {String(v)}</p>
            ))}
            <div className="font-semibold">{ti("limitations")}</div>
            <ul className="list-disc pl-5">{calc.data.calculation.assumptions.methodology.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </div>
        )}
      </Dialog>
    </div>
  );
}
