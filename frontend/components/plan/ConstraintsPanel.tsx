"use client";

import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Badge, Button, ErrorState, Field, InlineNote, inputCls } from "@/components/ui/primitives";
import { post, put } from "@/lib/api";
import type { PlanVersion, ResourceRow } from "@/lib/types";

export interface HumanConstraint {
  kind: "FORBID_RESOURCE_SECTOR" | "FORBID_RESOURCE_TASK" | "REQUIRE_TASK" | "EXCLUDE_TASK";
  resource_id?: string | null;
  sector?: string | null;
  task_code?: string | null;
  note?: string | null;
  author?: string | null;
}

const KINDS: HumanConstraint["kind"][] = ["FORBID_RESOURCE_SECTOR", "FORBID_RESOURCE_TASK", "REQUIRE_TASK", "EXCLUDE_TASK"];
export const constraintKey = (c: HumanConstraint) => `${c.kind}|${c.resource_id || ""}|${c.sector || ""}|${c.task_code || ""}`;

/**
 * Human constraints. Persisted constraints belong to a DRAFT version; for any other version they are applied to the
 * next optimizer run only ("session constraints") so an approved plan is never changed silently.
 */
export function ConstraintsPanel({ version, editable, resources, sectors, taskCodes, session, onSession, onSaved }: {
  version: PlanVersion; editable: boolean; resources: ResourceRow[]; sectors: { id: string; name: string }[]; taskCodes: string[];
  session: HumanConstraint[]; onSession: (c: HumanConstraint[]) => void; onSaved: () => void;
}) {
  const tp = useTranslations("plan");
  const tc = useTranslations("common");
  const persisted = (version.constraints || []) as HumanConstraint[];
  const isDraft = version.status === "DRAFT";
  const [draft, setDraft] = useState<HumanConstraint>({ kind: "FORBID_RESOURCE_SECTOR" });
  const [list, setList] = useState<HumanConstraint[]>(persisted);
  useEffect(() => setList((version.constraints || []) as HumanConstraint[]), [version.id, version.constraints]);

  const save = useMutation({
    mutationFn: (cs: HumanConstraint[]) => put(`/api/plan-versions/${version.id}/constraints`, { constraints: cs.map(({ author: _a, ...c }) => c) }),
    onSuccess: onSaved,
  });

  const needsResource = draft.kind === "FORBID_RESOURCE_SECTOR" || draft.kind === "FORBID_RESOURCE_TASK";
  const needsSector = draft.kind === "FORBID_RESOURCE_SECTOR";
  const needsTask = draft.kind !== "FORBID_RESOURCE_SECTOR";
  const valid = (!needsResource || !!draft.resource_id) && (!needsSector || !!draft.sector) && (!needsTask || !!draft.task_code);

  const add = () => {
    if (!valid) return;
    const c: HumanConstraint = { kind: draft.kind, resource_id: needsResource ? draft.resource_id : null, sector: needsSector ? draft.sector : null,
      task_code: needsTask ? draft.task_code : null, note: draft.note || null };
    if (isDraft && editable) setList([...list, c]);
    else onSession([...session, c]);
    setDraft({ kind: draft.kind });
  };

  const describe = (c: HumanConstraint) => [c.resource_id, c.sector && (sectors.find((s) => s.id === c.sector)?.name || c.sector), c.task_code].filter(Boolean).join(" · ");
  const dirty = JSON.stringify(list.map(constraintKey)) !== JSON.stringify(persisted.map(constraintKey));

  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{tp("versionConstraints", { v: version.version })}</div>
        {(isDraft ? list : persisted).length === 0 && <div className="text-xs text-muted">{tc("none")}</div>}
        <ul className="space-y-1">
          {(isDraft ? list : persisted).map((c, i) => (
            <li key={`${constraintKey(c)}-${i}`} className="flex items-center justify-between gap-2 rounded-[3px] border border-line bg-panel px-2 py-1 text-xs">
              <span><span className="font-semibold">{tp(`constraintKinds.${c.kind}`)}</span> <span className="font-mono text-ink-2">{describe(c)}</span>
                {c.author && <span className="text-muted"> · {c.author}</span>}{c.note && <span className="text-muted"> — {c.note}</span>}</span>
              {isDraft && editable && <button aria-label={tc("remove")} onClick={() => setList(list.filter((_, j) => j !== i))} className="p-1 text-muted hover:text-crit"><Trash2 className="h-3.5 w-3.5" /></button>}
            </li>
          ))}
        </ul>
        {isDraft && editable && dirty && (
          <Button size="sm" variant="primary" className="mt-2" busy={save.isPending} onClick={() => save.mutate(list)}>{tp("saveConstraints")}</Button>
        )}
        {save.isError && <ErrorState error={save.error} />}
      </div>

      {!isDraft && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{tp("sessionConstraints")}</div>
          <InlineNote tone="info">{tp("sessionConstraintsHint")}</InlineNote>
          <ul className="mt-1 space-y-1">
            {session.map((c, i) => (
              <li key={`${constraintKey(c)}-${i}`} className="flex items-center justify-between gap-2 rounded-[3px] border border-accent/40 bg-accent/5 px-2 py-1 text-xs">
                <span><span className="font-semibold">{tp(`constraintKinds.${c.kind}`)}</span> <span className="font-mono text-ink-2">{describe(c)}</span></span>
                <button aria-label={tc("remove")} onClick={() => onSession(session.filter((_, j) => j !== i))} className="p-1 text-muted hover:text-crit"><Trash2 className="h-3.5 w-3.5" /></button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {editable && (
        <div className="rounded-[4px] border border-line bg-panel p-2">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{tp("addConstraint")}</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field label={tp("constraintKind")}>
              <select className={inputCls} value={draft.kind} onChange={(e) => setDraft({ kind: e.target.value as HumanConstraint["kind"] })}>
                {KINDS.map((k) => <option key={k} value={k}>{tp(`constraintKinds.${k}`)}</option>)}
              </select>
            </Field>
            {needsResource && (
              <Field label={tp("resources")}>
                <select className={inputCls} value={draft.resource_id || ""} onChange={(e) => setDraft({ ...draft, resource_id: e.target.value || null })}>
                  <option value="">—</option>
                  {resources.filter((r) => r.resource_type === "CREW" || r.resource_type === "VEHICLE").map((r) => <option key={r.id} value={r.id}>{r.id}</option>)}
                </select>
              </Field>
            )}
            {needsSector && (
              <Field label={tp("sector")}>
                <select className={inputCls} value={draft.sector || ""} onChange={(e) => setDraft({ ...draft, sector: e.target.value || null })}>
                  <option value="">—</option>
                  {sectors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
            )}
            {needsTask && (
              <Field label={tp("task")}>
                <select className={inputCls} value={draft.task_code || ""} onChange={(e) => setDraft({ ...draft, task_code: e.target.value || null })}>
                  <option value="">—</option>
                  {taskCodes.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
            )}
            <Field label={tc("notes")}>
              <input className={inputCls} value={draft.note || ""} maxLength={300} onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
            </Field>
          </div>
          <Button size="sm" icon={Plus} className={clsx("mt-2")} disabled={!valid} onClick={add}>{tc("add")}</Button>
        </div>
      )}
    </div>
  );
}

/** AVAILABLE PUMPS 16 → 8: changes the resource pool for every computation (audited, triggers the pipeline). */
export function ResourcePool({ areaId, resources, type = "PUMP", editable, onDone }: {
  areaId: string; resources: ResourceRow[]; type?: string; editable: boolean; onDone: () => void;
}) {
  const tp = useTranslations("plan");
  const tt = useTranslations("resourceType");
  const units = resources.filter((r) => r.resource_type === type);
  const available = units.filter((r) => r.status === "AVAILABLE").length;
  const [n, setN] = useState<string>(String(available));
  useEffect(() => setN(String(available)), [available]);
  const m = useMutation({ mutationFn: (count: number) => post(`/api/areas/${areaId}/resources/pool`, { resource_type: type, count }), onSuccess: onDone });
  const val = Number(n);
  const ok = Number.isInteger(val) && val >= 0 && val <= units.length && val !== available;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 rounded-[3px] border border-line-2 bg-bg px-2 py-0.5 text-[11px]">
      <span className="font-semibold text-ink-2">{tp("availableOf", { type: tt.has(type) ? tt(type) : type })}</span>
      <Badge tone={available < units.length ? "warn" : "muted"} icon={false}>{available}/{units.length}</Badge>
      {editable && (
        <>
          <input type="number" min={0} max={units.length} value={n} onChange={(e) => setN(e.target.value)} aria-label={tp("availablePumps")} className={clsx(inputCls, "h-6 w-14")} />
          <Button size="sm" disabled={!ok} busy={m.isPending} onClick={() => m.mutate(val)}>{tp("setPool")}</Button>
        </>
      )}
      {m.isError && <span className="text-crit">!</span>}
    </span>
  );
}
