"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { Hydrograph, type HydroStation } from "@/components/charts/Hydrograph";
import { FreshnessTable } from "@/components/common/Freshness";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Badge, Button, ErrorState, Field, InlineNote, inputCls, KeyValue, Loading, Metric, Panel, useErrorText } from "@/components/ui/primitives";
import { api, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, num, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useInvalidateArea } from "@/lib/queries";
import type { Freshness } from "@/lib/types";

export default function SituationPage() {
  const { areaId, scenario, area, t, nowMin, fmt, clearOverlays } = useAreaCtx();
  const ts = useTranslations("scenario");
  const tf = useTranslations("freshness");
  const tc = useTranslations("common");
  const tm = useTranslations("mode");
  const { locale } = useLocale();
  const { can } = useAuth();
  const errText = useErrorText();
  const invalidate = useInvalidateArea();
  const [member, setMember] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => clearOverlays(), [clearOverlays]);

  const hydro = useQuery({
    queryKey: ["hydro", areaId, area?.data_version],
    queryFn: () => api<{ stations: (HydroStation & { names: Record<string, string> })[]; now_min: number }>(`/api/areas/${areaId}/hydrograph`),
    enabled: !!area,
  });
  const fresh = useQuery({
    queryKey: ["freshness", areaId, area?.data_version],
    queryFn: () => api<{ sources: Freshness[] }>(`/api/areas/${areaId}/freshness`),
    enabled: !!area,
  });
  const stats = useQuery({
    queryKey: ["stats", scenario?.id, scenario?.active_member],
    queryFn: () => api<{ frames: { offset_min: number; flooded_km2: number; max_depth_m: number; gauge_stage_cm: number | null }[] }>(`/api/scenarios/${scenario!.id}/stats`),
    enabled: !!scenario,
  });
  const select = useMutation({
    mutationFn: () => post(`/api/areas/${areaId}/scenario/select-member`, { member_id: member, note, lock: false }),
    onSuccess: () => { invalidate(areaId); setNote(""); },
  });
  const condition = useMutation({ mutationFn: () => post(`/api/areas/${areaId}/scenario/condition`), onSuccess: () => invalidate(areaId) });

  const frame = stats.data?.frames.reduce((a, b) => (t !== null && Math.abs(b.offset_min - t) < Math.abs(a.offset_min - t) ? b : a), stats.data.frames[0]);
  const sel = scenario?.selection;
  return (
    <div className="space-y-3 p-3">
      <ScreenHeader screen="situation" />
      {!scenario && <Loading />}
      {scenario && (
        <>
          <Panel title={ts("title")} right={<Badge tone="sim">{tm.has(scenario.mode) ? tm(scenario.mode) : scenario.mode}</Badge>}>
            <div className="grid grid-cols-3 gap-3">
              <Metric label={ts("gauge")} value={frame?.gauge_stage_cm != null ? `${num(frame.gauge_stage_cm, 0, locale)} cm` : "—"} sub={fmt(t)} />
              <Metric label={ts("flooded")} value={frame ? `${num(frame.flooded_km2, 2, locale)} km²` : "—"} />
              <Metric label={ts("maxDepth")} value={frame ? `${num(frame.max_depth_m, 1, locale)} m` : "—"} />
            </div>
            <div className="mt-3">
              <KeyValue rows={[
                [ts("version"), `${scenario.name}`],
                [ts("member"), <span key="m">{scenario.active_member} · {scenario.members.find((m) => m.id === scenario.active_member)?.label}</span>],
                [ts("selection"), sel?.method ? ts(`method.${sel.method}`) : "—"],
                [ts("referenceTime"), dateTime(scenario.reference_time, area?.utc_offset_min ?? 300)],
                [ts("provider"), <span key="p" className="text-ink-2">{scenario.provider_note}</span>],
                [tc("modelVersion"), scenario.model_version],
              ]} />
            </div>
            <InlineNote tone="sim" className="mt-2">{ts("notHydrodynamic")}</InlineNote>
            {sel?.open_conflicts && sel.open_conflicts.length > 0 && <InlineNote tone="warn" className="mt-2">{ts("openConflict")}</InlineNote>}
          </Panel>

          <Panel title={ts("hydrograph")}>
            {hydro.isLoading && <Loading />}
            {hydro.isError && <ErrorState error={hydro.error} onRetry={() => hydro.refetch()} />}
            {hydro.data?.stations.map((st) => (
              <div key={st.station_id}>
                <div className="mb-1 text-xs font-semibold">{pickName(st.names, locale)}</div>
                {nowMin !== null && t !== null && <Hydrograph st={st} nowMin={nowMin} cursor={t} fmt={(m) => fmt(m)} />}
              </div>
            ))}
          </Panel>

          {sel?.scores && sel.scores.length > 0 && (
            <Panel title={ts("selection")}>
              <table className="w-full text-xs">
                <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
                  <tr><th className="py-1">{ts("member")}</th><th>{ts("rmse")}</th><th>{ts("envelope")}</th></tr>
                </thead>
                <tbody>
                  {sel.scores.map((s) => (
                    <tr key={s.member} className="border-t border-line/60">
                      <td className="py-1">{s.member} <span className="text-muted">{s.label}</span> {s.member === scenario.active_member && <Badge tone="live">{ts("active")}</Badge>}</td>
                      <td className="tabular">{num(s.weighted_rmse_cm, 1, locale)}</td>
                      <td>{sel.envelope?.includes(s.member) ? "✓" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}

          {can("plan_edit") && (
            <Panel title={ts("selectMember")}>
              <div className="grid grid-cols-2 gap-2">
                <Field label={ts("member")}>
                  <select className={inputCls} value={member} onChange={(e) => setMember(e.target.value)}>
                    <option value="">—</option>
                    {scenario.members_order.map((m) => <option key={m} value={m} disabled={m === scenario.active_member}>{m} · {scenario.members.find((x) => x.id === m)?.label}</option>)}
                  </select>
                </Field>
                <Field label={ts("selectNote")}>
                  <input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} />
                </Field>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="accent" disabled={!member} busy={select.isPending} onClick={() => select.mutate()}>{ts("selectMember")}</Button>
                <Button busy={condition.isPending} onClick={() => condition.mutate()}>{ts("conditionNow")}</Button>
              </div>
              {(select.error || condition.error) && <div className="mt-2 text-xs text-crit">{errText(select.error || condition.error)}</div>}
            </Panel>
          )}

          <Panel title={tf("title")}>
            {fresh.data ? <FreshnessTable rows={fresh.data.sources} utcOffset={area?.utc_offset_min ?? 300} compact /> : <Loading />}
          </Panel>
        </>
      )}
    </div>
  );
}
