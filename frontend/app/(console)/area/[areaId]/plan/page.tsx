"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Cpu, GitBranch, PackagePlus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx, type PointOverlay } from "@/components/area/AreaContext";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { AlternativesView, OptimizerControls, type Policy, type Weights } from "@/components/plan/AlternativesPanel";
import { ConstraintsPanel, constraintKey, ResourcePool, type HumanConstraint } from "@/components/plan/ConstraintsPanel";
import { GapPanel } from "@/components/plan/GapPanel";
import { HealthBanner } from "@/components/plan/HealthBanner";
import { StressPanel } from "@/components/plan/StressPanel";
import { TaskTable } from "@/components/plan/TaskTable";
import { Badge, Button, Empty, ErrorState, InlineNote, inputCls, Loading, Panel, StatusBadge, Tabs } from "@/components/ui/primitives";
import { api, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useInvalidateArea, usePlanHealth, usePlans, usePlanVersion, useResources } from "@/lib/queries";
import { toneOf } from "@/lib/status";
import type { GapResult, OptimizationResult, PlanVersion, StressResult } from "@/lib/types";
import { useNames } from "@/lib/useNames";

type Tab = "tasks" | "stress" | "alternatives" | "gap" | "constraints";
type RunRow = { id: string; kind: string; plan_version_id: string; data_version: number };

const LIFECYCLE: Record<string, { target: string; perm: string; label: string; variant: "primary" | "default" | "danger" | "ghost" }[]> = {
  DRAFT: [{ target: "REVIEWED", perm: "plan_review", label: "toReviewed", variant: "primary" }, { target: "REJECTED", perm: "plan_review", label: "toRejected", variant: "ghost" }],
  REVIEWED: [{ target: "APPROVED", perm: "plan_approve", label: "toApproved", variant: "primary" }, { target: "DRAFT", perm: "plan_edit", label: "toDraft", variant: "ghost" }, { target: "REJECTED", perm: "plan_approve", label: "toRejected", variant: "ghost" }],
  APPROVED: [{ target: "ACTIVE", perm: "plan_approve", label: "toActive", variant: "primary" }],
};

export default function PlanPage() {
  const { areaId, area, scenario, fmt, layers, setOverlays, clearOverlays } = useAreaCtx();
  const tp = useTranslations("plan");
  const tn = useTranslations("nav");
  const tst = useTranslations("stress");
  const to = useTranslations("optimizer");
  const tg = useTranslations("gap");
  const tor = useTranslations("origin");
  const tps = useTranslations("planStatus");
  const tpol = useTranslations("policy");
  const { locale } = useLocale();
  const { can } = useAuth();
  const names = useNames(areaId);
  const qc = useQueryClient();
  const invalidate = useInvalidateArea();
  const dv = area?.data_version;

  const plans = usePlans(areaId);
  const versions = useMemo(() => (plans.data || []).flatMap((p) => p.versions), [plans.data]);
  const [vid, setVid] = useState<string | null>(null);
  useEffect(() => {
    if (!plans.data || (vid && versions.some((v) => v.id === vid))) return;
    const qp = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("v") : null;
    const pick = versions.find((v) => v.id === qp) || versions.find((v) => v.status === "ACTIVE") || versions[versions.length - 1];
    setVid(pick?.id ?? null);
  }, [plans.data, versions, vid]);

  const pv = usePlanVersion(vid, dv);
  const health = usePlanHealth(vid, dv);
  const resources = useResources(areaId);
  const version = pv.data;

  const [tab, setTab] = useState<Tab>("tasks");
  const [policy, setPolicy] = useState<Policy>("BALANCED");
  const [weights, setWeights] = useState<Weights>({ life: 40, infra: 35, economic: 25 });
  const [whatIf, setWhatIf] = useState<string[]>([]);
  const [session, setSession] = useState<HumanConstraint[]>([]);
  const [selTask, setSelTask] = useState<string | null>(null);
  const [selAlt, setSelAlt] = useState<string | null>(null);
  const [selAltTask, setSelAltTask] = useState<string | null>(null);
  const [fresh, setFresh] = useState<{ alt?: string; gap?: string }>({});
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => { setSelTask(null); setSelAlt(null); setSelAltTask(null); setFresh({}); setSession([]); }, [vid]);

  const policiesQ = useQuery({ queryKey: ["policies"], queryFn: () => api<{ policies: Record<Policy, Weights> }>("/api/policies"), staleTime: Infinity });
  const choosePolicy = (p: Policy) => {
    setPolicy(p);
    const w = policiesQ.data?.policies[p];
    if (w) setWeights({ life: w.life, infra: w.infra, economic: w.economic });
  };

  // latest stored results for this version (so a reload keeps the last analysis, flagged when outdated)
  const stressQ = useQuery({
    queryKey: ["stressLatest", vid],
    queryFn: async () => {
      const l = await api<{ id: string }[]>(`/api/plan-versions/${vid}/stress-tests`);
      return l[0] ? api<StressResult & { data_version: number }>(`/api/stress-tests/${l[0].id}`) : null;
    },
    enabled: !!vid,
  });
  const runsQ = useQuery({ queryKey: ["optRuns", areaId, dv], queryFn: () => api<RunRow[]>(`/api/areas/${areaId}/optimization-runs`), enabled: dv !== undefined });
  const altId = fresh.alt || runsQ.data?.find((r) => r.plan_version_id === vid && r.kind === "ALTERNATIVES")?.id;
  const gapId = fresh.gap || runsQ.data?.find((r) => r.plan_version_id === vid && r.kind === "RESOURCE_GAP")?.id;
  const altQ = useQuery({ queryKey: ["optRun", altId], queryFn: () => api<OptimizationResult & { data_version: number }>(`/api/optimization-runs/${altId}`), enabled: !!altId, staleTime: Infinity });
  const gapQ = useQuery({ queryKey: ["optRun", gapId], queryFn: () => api<GapResult & { data_version: number }>(`/api/optimization-runs/${gapId}`), enabled: !!gapId, staleTime: Infinity });

  const optBody = () => ({
    policy, weights, what_if_unavailable: whatIf,
    extra_constraints: session.filter((c) => !(version?.constraints || []).some((p) => constraintKey(p as HumanConstraint) === constraintKey(c))).map(({ author: _a, ...c }) => c),
  });
  const stressM = useMutation({
    mutationFn: () => post<StressResult & { data_version: number }>(`/api/plan-versions/${vid}/stress-test`),
    onSuccess: (r) => { qc.setQueryData(["stressLatest", vid], r); setTab("stress"); qc.invalidateQueries({ queryKey: ["audit", areaId] }); },
  });
  const altM = useMutation({
    mutationFn: () => post<OptimizationResult & { data_version: number }>(`/api/plan-versions/${vid}/alternatives`, optBody()),
    onSuccess: (r) => {
      qc.setQueryData(["optRun", r.id], r); setFresh((f) => ({ ...f, alt: r.id })); setSelAlt(r.alternatives[0]?.id ?? null); setSelAltTask(null);
      setTab("alternatives"); qc.invalidateQueries({ queryKey: ["optRuns", areaId] });
    },
  });
  const gapM = useMutation({
    mutationFn: () => post<GapResult & { data_version: number }>(`/api/plan-versions/${vid}/resource-gap`, optBody()),
    onSuccess: (r) => { qc.setQueryData(["optRun", r.id], r); setFresh((f) => ({ ...f, gap: r.id })); setTab("gap"); qc.invalidateQueries({ queryKey: ["optRuns", areaId] }); },
  });
  const adoptM = useMutation({
    mutationFn: (altIdToAdopt: string) => post<PlanVersion>(`/api/optimization-runs/${altId}/adopt`, { alternative_id: altIdToAdopt }),
    onSuccess: (v) => { setNotice(tp("adopted", { v: v.version })); invalidate(areaId); setVid(v.id); setTab("tasks"); },
  });
  const transitionM = useMutation({
    mutationFn: (target: string) => post<PlanVersion>(`/api/plan-versions/${vid}/transition`, { target }),
    onSuccess: () => { setNotice(null); invalidate(areaId); },
  });
  const forkM = useMutation({
    mutationFn: () => post<PlanVersion>(`/api/plan-versions/${vid}/versions`, {}),
    onSuccess: (v) => { setNotice(tp("forked", { v: v.version })); invalidate(areaId); setVid(v.id); },
  });
  const tasksM = useMutation({
    mutationFn: (tasks: object[]) => put<PlanVersion>(`/api/plan-versions/${vid}/tasks`, { tasks }),
    onSuccess: () => invalidate(areaId),
  });
  const exerciseScenarioM = useMutation({
    mutationFn: (member: "BASE" | "HIGH") => post(`/api/areas/${areaId}/scenario/select-member`, {
      member_id: member,
      note: member === "HIGH"
        ? "Competition exercise escalation BASE → HIGH"
        : "Competition exercise reset HIGH → BASE",
      lock: false,
    }),
    onSuccess: () => {
      setFresh({});
      qc.invalidateQueries({ queryKey: ["stressLatest", vid] });
      qc.invalidateQueries({ queryKey: ["optRuns", areaId] });
      invalidate(areaId);
    },
  });

  // map: plan task sites coloured by evaluation; selected task (plan or alternative) route highlighted
  const evalTasks = health.data?.evaluation.tasks;
  const alt = altQ.data?.alternatives.find((a) => a.id === selAlt) || altQ.data?.alternatives[0];
  useEffect(() => () => clearOverlays(), [clearOverlays]);
  useEffect(() => {
    const showAlt = tab === "alternatives" && alt;
    const pts: PointOverlay[] = [];
    const src = showAlt
      ? alt.evaluation.tasks.map((t) => ({ code: t.code, site: t.site_id, status: t.status }))
      : (evalTasks || []).map((t) => ({ code: t.code, site: t.site_id, status: t.status }));
    for (const x of src) {
      const s = names.siteObj(x.site);
      if (!s) continue;
      pts.push({ id: `pt-${x.code}`, lon: s.lon, lat: s.lat, label: x.code, sub: names.site(x.site), tone: toneOf(x.status) as PointOverlay["tone"] });
    }
    const code = showAlt ? selAltTask : selTask;
    const segs = showAlt ? alt.tasks.find((t) => t.code === code)?.route_segments || [] : evalTasks?.find((t) => t.code === code)?.route_segments || [];
    const focusSite = code ? names.siteObj(src.find((x) => x.code === code)?.site || "") : undefined;
    setOverlays({
      points: pts, highlightSegments: [],
      routes: segs.length ? [{ id: "task-route", segments: segs, color: "#38bdf8", width: 5 }] : [],
      focus: focusSite ? { lon: focusSite.lon, lat: focusSite.lat } : null,
    });
  }, [tab, alt, evalTasks, selTask, selAltTask, names, setOverlays]);

  const facilityName = (id: string) => {
    const f = layers.facilities?.features.find((x) => x.properties.id === id);
    return f ? pickName(f.properties.names as never, locale, id) : id;
  };
  const sectors = (layers.sectors?.features || []).map((f) => ({ id: String(f.properties.id), name: pickName(f.properties.names as never, locale, String(f.properties.id)) }));
  const sectorName = (id: string) => sectors.find((s) => s.id === id)?.name || id;

  if (plans.isLoading) return <div className="p-3"><ScreenHeader screen="plan" /><Loading /></div>;
  if (plans.isError) return <div className="p-3"><ScreenHeader screen="plan" /><ErrorState error={plans.error} onRetry={() => plans.refetch()} /></div>;
  if (!versions.length) return <div className="p-3"><ScreenHeader screen="plan" /><Empty>{tp("noPlan")}</Empty></div>;

  const canEdit = can("plan_edit");
  const busy = stressM.isPending || altM.isPending || gapM.isPending || exerciseScenarioM.isPending;
  const lifecycle = version ? LIFECYCLE[version.status] || [] : [];
  const stress = stressQ.data;
  const taskCodes = Array.from(new Set([...(version?.tasks || []).map((t) => t.code), ...(altQ.data?.candidates || []).map((c) => c.code)])).sort();
  const mutErr = stressM.error || altM.error || gapM.error || adoptM.error || transitionM.error || forkM.error || tasksM.error || exerciseScenarioM.error;

  return (
    <div className="space-y-3 p-3">
      <ScreenHeader screen="plan" right={
        <label className="flex items-center gap-1.5 text-[11px]">
          <span className="text-muted">{tp("selectVersion")}</span>
          <select className={`${inputCls} w-64`} value={vid || ""} onChange={(e) => setVid(e.target.value)}>
            {(plans.data || []).map((p) => (
              <optgroup key={p.id} label={p.name}>
                {p.versions.map((v) => <option key={v.id} value={v.id}>{p.name} v{v.version} · {tps.has(v.status) ? tps(v.status) : v.status}{v.origin !== "HUMAN" ? ` · ${tor.has(v.origin) ? tor(v.origin) : v.origin}` : ""}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
      } />

      {version && (
        <div className="flex flex-wrap items-center gap-2 rounded-[4px] border border-line bg-panel px-3 py-2 text-[11px]">
          <span className="text-sm font-bold">{version.plan_name} v{version.version}</span>
          <StatusBadge ns="planStatus" code={version.status} />
          <Badge tone={version.origin === "HUMAN" ? "muted" : "info"} icon={false}>{tor.has(version.origin) ? tor(version.origin) : version.origin}</Badge>
          {version.policy && <Badge tone="muted" icon={false}>{tpol.has(version.policy) ? tpol(version.policy) : version.policy}</Badge>}
          <span className="text-muted">{tp("createdBy")}: {version.created_by || "—"} · {area ? dateTime(version.created_at, area.utc_offset_min) : ""}</span>
          {version.approved_by && <span className="text-muted">· {tp("approvedBy")}: {version.approved_by}</span>}
          <span className="ml-auto flex flex-wrap items-center gap-1">
            {lifecycle.filter((l) => can(l.perm)).map((l) => (
              <Button key={l.target} size="sm" variant={l.variant} busy={transitionM.isPending && transitionM.variables === l.target} onClick={() => transitionM.mutate(l.target)}>{tp(l.label)}</Button>
            ))}
            {version.status === "REVIEWED" && !can("plan_approve") && <span className="text-[10.5px] text-muted">{tp("onlyCommander")}</span>}
            {version.status !== "DRAFT" && canEdit && <Button size="sm" variant="ghost" icon={GitBranch} busy={forkM.isPending} onClick={() => forkM.mutate()}>{tp("newVersion")}</Button>}
          </span>
        </div>
      )}
      {version && Object.keys(version.change_summary || {}).length > 0 && version.origin !== "HUMAN" && <ChangeSummary summary={version.change_summary} />}
      {notice && <InlineNote tone="ok">{notice}</InlineNote>}
      {mutErr && <ErrorState error={mutErr} />}

      {health.data ? (
        <HealthBanner health={health.data} fmt={fmt} siteName={names.site} planLabel={`${version?.plan_name || ""} v${version?.version ?? ""}`} defaultOpen={health.data.status !== "PLAN_VALID"} />
      ) : health.isError ? <ErrorState error={health.error} onRetry={() => health.refetch()} /> : <Loading />}

      <div className="flex flex-wrap items-center gap-2">
        {canEdit ? (
          <>
            <Button variant={health.data?.status === "PLAN_AT_RISK" ? "danger" : "default"} icon={Activity} busy={stressM.isPending} disabled={busy || !vid} onClick={() => stressM.mutate()}>{tp("stressTest")}</Button>
            <Button variant="primary" icon={Cpu} busy={altM.isPending} disabled={busy || !vid} onClick={() => altM.mutate()}>{tp("generate")}</Button>
            <Button icon={PackagePlus} busy={gapM.isPending} disabled={busy || !vid} onClick={() => gapM.mutate()}>{tp("gap")}</Button>
            {areaId === "atbasar" && scenario?.active_member === "BASE" && (
              <Button variant="danger" busy={exerciseScenarioM.isPending} disabled={busy}
                onClick={() => exerciseScenarioM.mutate("HIGH")}>{tp("exerciseHigh")}</Button>
            )}
            {areaId === "atbasar" && scenario?.active_member === "HIGH" && (
              <Button variant="ghost" busy={exerciseScenarioM.isPending} disabled={busy}
                onClick={() => exerciseScenarioM.mutate("BASE")}>{tp("exerciseBase")}</Button>
            )}
          </>
        ) : <InlineNote tone="info">{tp("readOnly")}</InlineNote>}
        {busy && <span className="text-[11px] text-muted">{altM.isPending || gapM.isPending ? tp("runningSolver") : tp("running")}</span>}
      </div>

      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { id: "tasks", label: tp("tasks") },
        { id: "stress", label: tst("title"), badge: stress ? `${stress.n_feasible}/${stress.n_scenarios}` : undefined },
        { id: "alternatives", label: to("title"), badge: altQ.data ? String(altQ.data.alternatives.length) : undefined },
        { id: "gap", label: tg("title") },
        { id: "constraints", label: tp("constraints"), badge: (version?.constraints.length || 0) + session.length ? String((version?.constraints.length || 0) + session.length) : undefined },
      ]} />

      {tab === "tasks" && version && (
        <Panel title={health.data ? tp("evaluationAt", { time: fmt(health.data.as_of), v: health.data.scenario.version, member: health.data.scenario.member }) : tp("tasks")}>
          {version.status !== "DRAFT" && canEdit && <p className="mb-2 text-[10.5px] text-muted">{tp("draftOnly")}</p>}
          <TaskTable areaId={areaId} version={version} evalTasks={evalTasks || []} fmt={fmt} utcOffset={area?.utc_offset_min ?? 0}
            referenceTime={health.data?.reference_time || scenario?.reference_time || version.created_at} editable={canEdit && version.status === "DRAFT"}
            onSave={(t) => tasksM.mutate(t)} saving={tasksM.isPending} selected={selTask} onSelect={setSelTask} />
          {selTask && <TaskDetail code={selTask} health={health.data} fmt={fmt} />}
        </Panel>
      )}

      {tab === "stress" && (stress ? (
        <StressPanel result={stress} outdated={stress.data_version !== dv} fmt={fmt} siteName={names.site} />
      ) : stressQ.isLoading ? <Loading /> : <Empty>{tst("notRun")}</Empty>)}

      {tab === "alternatives" && (
        <div className="space-y-3">
          <Panel title={tp("optimizerInputs")}>
            <OptimizerControls policy={policy} weights={weights} onPolicy={choosePolicy} onWeights={setWeights} whatIf={whatIf} onWhatIf={setWhatIf}
              resources={resources.data || []}
              pool={<ResourcePool areaId={areaId} resources={resources.data || []} editable={canEdit} onDone={() => invalidate(areaId)} />} />
          </Panel>
          {altQ.data ? (
            <AlternativesView run={altQ.data} areaId={areaId} fmt={fmt} selected={selAlt} onSelect={(id) => { setSelAlt(id); setSelAltTask(null); }}
              selectedTask={selAltTask} onSelectTask={setSelAltTask} onAdopt={(id) => adoptM.mutate(id)} adopting={adoptM.isPending} canAdopt={canEdit}
              outdated={altQ.data.data_version !== dv} facilityName={facilityName} sectorName={sectorName} />
          ) : altQ.isLoading ? <Loading /> : <Empty>{to("notRun")}</Empty>}
        </div>
      )}

      {tab === "gap" && (gapQ.data ? <GapPanel result={gapQ.data} outdated={gapQ.data.data_version !== dv} /> : gapQ.isLoading ? <Loading /> : <Empty>{tg("notRun")}</Empty>)}

      {tab === "constraints" && version && (
        <div className="space-y-3">
          <Panel title={tp("constraints")}>
            <ConstraintsPanel version={version} editable={canEdit} resources={resources.data || []} sectors={sectors} taskCodes={taskCodes}
              session={session} onSession={setSession} onSaved={() => invalidate(areaId)} />
          </Panel>
          <Panel title={tp("resourcePool")}>
            <div className="flex flex-wrap gap-2">
              {(["PUMP", "CREW", "VEHICLE", "EQUIPMENT"] as const).map((type) => (
                <ResourcePool key={type} areaId={areaId} resources={resources.data || []} type={type} editable={canEdit} onDone={() => invalidate(areaId)} />
              ))}
            </div>
            <p className="mt-2 text-[10.5px] text-muted">{tp("poolHint")}</p>
          </Panel>
        </div>
      )}
      <p className="text-[10px] text-muted">{tn("plan")} · {tp("humanDecides")}</p>
    </div>
  );
}

function ChangeSummary({ summary }: { summary: Record<string, unknown> }) {
  const tp = useTranslations("plan");
  const to = useTranslations("optimizer");
  const d = (summary.diff || summary) as { added?: string[]; removed?: string[]; reassigned?: { task: string }[]; retimed?: { task: string }[] };
  const parts: string[] = [];
  if (d.added?.length) parts.push(`${to("added")}: ${d.added.join(", ")}`);
  if (d.removed?.length) parts.push(`${to("removed")}: ${d.removed.join(", ")}`);
  if (d.reassigned?.length) parts.push(`${to("reassigned")}: ${d.reassigned.map((r) => r.task).join(", ")}`);
  if (d.retimed?.length) parts.push(`${to("retimed")}: ${d.retimed.map((r) => r.task).join(", ")}`);
  if (!parts.length) return null;
  return <InlineNote tone="info">{tp("changeSummary")}: {parts.join(" · ")}</InlineNote>;
}

function TaskDetail({ code, health, fmt }: { code: string; health?: { evaluation: { tasks: import("@/lib/types").TaskResult[] }; chains: import("@/lib/types").CausalChain[] }; fmt: (m: number | null | undefined) => string }) {
  const tp = useTranslations("plan");
  const tw = useTranslations("windows");
  const ti = useTranslations("issues");
  const t = health?.evaluation.tasks.find((x) => x.code === code);
  if (!t) return null;
  const comps = Object.entries(t.deadline_components || {}).filter(([, v]) => v !== null);
  return (
    <div className="mt-2 grid grid-cols-1 gap-2 rounded-[3px] border border-accent/40 bg-accent/5 p-2 text-[11.5px] md:grid-cols-3">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">{tp("route")}</div>
        <div className="font-mono">{t.route_roads.join(" → ") || "—"}</div>
        <div className="text-muted">{tp(`vehicleClass.${t.vehicle_class}`)}{t.crew_id ? ` · ${t.crew_id}` : ""}</div>
      </div>
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">{tw("deadline")}</div>
        <div className="font-semibold">{fmt(t.deadline)} · {tw.has(`reason.${t.deadline_reason}`) ? tw(`reason.${t.deadline_reason}`) : t.deadline_reason}</div>
        {comps.map(([k, v]) => <div key={k} className="text-muted">{tw.has(`reason.${k.toUpperCase()}`) ? tw(`reason.${k.toUpperCase()}`) : k}: {fmt(v)}</div>)}
        <div className="mt-0.5 text-[10.5px] text-muted">{tw("formula")}</div>
      </div>
      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-muted">{tp("issues")}</div>
        {t.issues.length === 0 ? <div className="text-ok">—</div> : t.issues.map((i, k) => (
          <div key={k} className={i.blocking ? "text-crit" : "text-warn"}>{ti.has(i.type) ? ti(i.type) : i.type}</div>
        ))}
      </div>
    </div>
  );
}
