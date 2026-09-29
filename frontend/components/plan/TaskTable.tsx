"use client";

import clsx from "clsx";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Badge, Button, inputCls, StatusBadge } from "@/components/ui/primitives";
import { countdown, hhmm } from "@/lib/format";
import type { PlanTaskRow, PlanVersion, TaskResult } from "@/lib/types";
import { useNames } from "@/lib/useNames";

export interface EditTask {
  code: string;
  template_id: string;
  site_id: string;
  resource_ids: string;
  departure: string; // HH:MM local
  dependencies: string;
}

export function toLocalIso(referenceIso: string, hm: string, offsetMin: number): string | null {
  if (!/^\d{1,2}:\d{2}$/.test(hm)) return null;
  const [h, m] = hm.split(":").map(Number);
  const ref = new Date(referenceIso);
  const local = new Date(ref.getTime() + offsetMin * 60000);
  const utcMs = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate(), h, m) - offsetMin * 60000;
  return new Date(utcMs).toISOString();
}

export function TaskTable({ areaId, version, evalTasks, fmt, utcOffset, referenceTime, editable, onSave, saving, selected, onSelect }: {
  areaId: string; version: PlanVersion; evalTasks: TaskResult[]; fmt: (m: number | null | undefined) => string; utcOffset: number;
  referenceTime: string; editable: boolean; onSave: (tasks: object[]) => void; saving: boolean; selected: string | null; onSelect: (c: string | null) => void;
}) {
  const tp = useTranslations("plan");
  const ti = useTranslations("issues");
  const tc = useTranslations("common");
  const names = useNames(areaId);
  const byCode = new Map(evalTasks.map((x) => [x.code, x]));
  const [edit, setEdit] = useState<EditTask[] | null>(null);

  useEffect(() => setEdit(null), [version.id]);

  const startEdit = () => setEdit((version.tasks || []).map((r: PlanTaskRow) => ({
    code: r.code, template_id: r.template_id, site_id: r.site_id, resource_ids: r.resource_ids.join(", "),
    departure: r.planned_departure ? hhmm(r.planned_departure, utcOffset) : "", dependencies: r.dependencies.join(", "),
  })));

  const save = () => {
    if (!edit) return;
    onSave(edit.map((e) => ({
      code: e.code.trim(), template_id: e.template_id, site_id: e.site_id,
      resource_ids: e.resource_ids.split(/[,\s]+/).filter(Boolean),
      planned_departure: e.departure ? toLocalIso(referenceTime, e.departure, utcOffset) : null,
      dependencies: e.dependencies.split(/[,\s]+/).filter(Boolean),
    })));
    setEdit(null);
  };

  if (edit) {
    const upd = (i: number, k: keyof EditTask, v: string) => setEdit(edit.map((e, j) => (j === i ? { ...e, [k]: v } : e)));
    return (
      <div className="space-y-2">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-xs">
            <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
              <tr><th className="py-1">{tp("task")}</th><th>{tp("template")}</th><th>{tp("site")}</th><th>{tp("resources")}</th><th>{tp("plannedDeparture")}</th><th>{tp("dependencies")}</th><th /></tr>
            </thead>
            <tbody>
              {edit.map((e, i) => (
                <tr key={i} className="border-t border-line/60">
                  <td className="py-1 pr-1"><input className={clsx(inputCls, "w-14")} value={e.code} onChange={(ev) => upd(i, "code", ev.target.value)} /></td>
                  <td className="pr-1">
                    <select className={inputCls} value={e.template_id} onChange={(ev) => upd(i, "template_id", ev.target.value)}>
                      {names.actions.map((a) => <option key={a.id} value={a.id}>{names.action(a.id)}</option>)}
                    </select>
                  </td>
                  <td className="pr-1">
                    <select className={inputCls} value={e.site_id} onChange={(ev) => upd(i, "site_id", ev.target.value)}>
                      {names.sites.map((s) => <option key={s.id} value={s.id}>{names.site(s.id)}</option>)}
                    </select>
                  </td>
                  <td className="pr-1"><input className={inputCls} value={e.resource_ids} onChange={(ev) => upd(i, "resource_ids", ev.target.value)} placeholder="C3, V1, P05" /></td>
                  <td className="pr-1"><input className={clsx(inputCls, "w-20")} value={e.departure} onChange={(ev) => upd(i, "departure", ev.target.value)} placeholder="HH:MM" /></td>
                  <td className="pr-1"><input className={clsx(inputCls, "w-20")} value={e.dependencies} onChange={(ev) => upd(i, "dependencies", ev.target.value)} /></td>
                  <td><button aria-label={tc("remove")} onClick={() => setEdit(edit.filter((_, j) => j !== i))} className="p-1 text-muted hover:text-crit"><Trash2 className="h-3.5 w-3.5" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex gap-2">
          <Button size="sm" icon={Plus} onClick={() => setEdit([...edit, { code: `T${edit.length + 1}`, template_id: names.actions[0]?.id || "", site_id: names.sites[0]?.id || "", resource_ids: "", departure: "", dependencies: "" }])}>{tp("addTask")}</Button>
          <Button size="sm" variant="primary" busy={saving} onClick={save}>{tp("saveTasks")}</Button>
          <Button size="sm" variant="ghost" onClick={() => setEdit(null)}>{tc("cancel")}</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-xs">
          <thead className="text-left text-[10px] uppercase tracking-wider text-muted">
            <tr>
              <th className="py-1">{tp("task")}</th><th>{tp("template")} · {tp("site")}</th><th>{tp("resources")}</th>
              <th>{tp("plannedDeparture")}</th><th>{tp("arrival")}</th><th>{tp("end")}</th><th>{tp("deadline")}</th>
              <th>{tp("latestDeparture")}</th><th>{tp("slack")}</th><th>{tp("status")}</th>
            </tr>
          </thead>
          <tbody>
            {(version.tasks || []).map((r) => {
              const ev = byCode.get(r.code);
              const late = ev && ev.planned_departure !== null && ev.latest_departure !== null && ev.planned_departure > ev.latest_departure;
              return (
                <tr key={r.id} onClick={() => onSelect(selected === r.code ? null : r.code)}
                  className={clsx("cursor-pointer border-t border-line/60 align-top", selected === r.code ? "bg-accent/10" : "hover:bg-panel-2", ev?.status === "INFEASIBLE" && "bg-crit/5")}>
                  <td className="py-1.5 font-mono font-bold">{r.code}</td>
                  <td className="max-w-[200px]"><div className="truncate font-semibold">{names.action(r.template_id)}</div><div className="truncate text-[10.5px] text-muted">{names.site(r.site_id)}</div></td>
                  <td className="font-mono text-[10.5px] text-ink-2">{r.resource_ids.join(" ")}</td>
                  <td className={clsx("tabular", late && "font-bold text-crit")}>{r.planned_departure ? hhmm(r.planned_departure, utcOffset) : "—"}</td>
                  <td className="tabular">{fmt(ev?.arrival)}</td>
                  <td className="tabular">{fmt(ev?.end)}</td>
                  <td className="tabular">{fmt(ev?.deadline)}</td>
                  <td className="tabular font-semibold">{fmt(ev?.latest_departure)}</td>
                  <td className={clsx("tabular", ev?.slack_min != null && ev.slack_min < 20 && "text-warn")}>{ev?.slack_min != null ? countdown(ev.slack_min) : "—"}</td>
                  <td>
                    <StatusBadge ns="evalStatus" code={ev?.status || r.status} />
                    <div className="mt-0.5 flex flex-wrap gap-0.5">
                      {ev?.issues.filter((i) => i.blocking || i.type === "LOW_SLACK").map((i, k) => <Badge key={k} tone={i.blocking ? "crit" : "warn"} icon={false}>{ti.has(i.type) ? ti(i.type) : i.type}</Badge>)}
                      {r.status !== "PENDING" && <StatusBadge ns="taskStatus" code={r.status} icon={false} />}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {editable && <Button size="sm" onClick={startEdit}>{tp("editTasks")}</Button>}
    </div>
  );
}
