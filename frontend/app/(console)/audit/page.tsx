"use client";

import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { useTranslations } from "use-intl";

import { ScreenHelp } from "@/components/help/ScreenHelp";

import { Badge, ErrorState, inputCls, Loading } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useAreas } from "@/lib/queries";

interface Row { id: number; ts: string; op_time: string | null; username: string; role: string; action: string; entity_type: string; entity_id: string | null; area_id: string | null; summary: string; details: Record<string, unknown> | null; data_version: number | null; affects_results: boolean }

/** "Why did ARGUS change its result?" — every result-affecting change bumps the data version and is listed here. */
export default function AuditPage() {
  const ta = useTranslations("audit");
  const taa = useTranslations("auditAction");
  const tn = useTranslations("nav");
  const tq = useTranslations("questions");
  const tc = useTranslations("common");
  const { locale } = useLocale();
  const areas = useAreas();
  const [area, setArea] = useState("atbasar");
  const [only, setOnly] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const q = useQuery({
    queryKey: ["audit", area, only],
    queryFn: () => api<Row[]>(`/api/audit?limit=300${area ? `&area_id=${area}` : ""}${only ? "&affects_results=true" : ""}`),
    refetchInterval: 15_000,
  });
  const offset = areas.data?.find((a) => a.id === area)?.utc_offset_min ?? 300;
  const t = (iso: string | null) => (iso ? new Date(new Date(iso).getTime() + offset * 60000).toISOString().slice(0, 16).replace("T", " ") : "—");
  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3">
      <div>
        <div className="flex items-start justify-between gap-2"><h1 className="text-base font-bold tracking-wide">{tn("audit")}</h1><ScreenHelp screen="audit" /></div>
        <p className="text-[12.5px] text-accent">{tq("audit")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-1">{ta("area")}
          <select className={`${inputCls} w-56`} value={area} onChange={(e) => setArea(e.target.value)}>
            <option value="">{tc("all")}</option>
            {(areas.data || []).map((a) => <option key={a.id} value={a.id}>{pickName(a.names, locale)}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} />{ta("onlyResults")}</label>
      </div>
      {q.isLoading && <Loading />}
      {q.isError && <ErrorState error={q.error} />}
      <table className="w-full text-xs [&_td]:px-1.5 [&_th]:px-1.5">
        <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
          <tr><th>{ta("opTime")}</th><th>{ta("dataVersion")}</th><th>{ta("user")}</th><th>{ta("action")}</th><th>{ta("summary")}</th></tr>
        </thead>
        <tbody>
          {(q.data || []).map((r) => (
            <Fragment key={r.id}>
              <tr className="cursor-pointer border-t border-line/60 hover:bg-panel-2" onClick={() => setOpen(open === r.id ? null : r.id)}>
                <td className="py-1 tabular">{t(r.op_time || r.ts)}</td>
                <td className="tabular">{r.data_version ?? "—"}</td>
                <td>{r.username} <span className="text-muted">({r.role})</span></td>
                <td><Badge tone={r.affects_results ? "warn" : "muted"} icon={false} title={r.action}>{taa.has(r.action) ? taa(r.action) : r.action}</Badge></td>
                <td className="font-mono text-[10.5px] text-ink-2">{r.summary}</td>
              </tr>
              {open === r.id && r.details && (
                <tr><td colSpan={5} className="bg-panel-2 p-2"><pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[10.5px] text-ink-2">{JSON.stringify(r.details, null, 2)}</pre></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
