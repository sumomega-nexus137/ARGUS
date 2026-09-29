"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { Badge, Button, ErrorState, InlineNote, Loading, Panel } from "@/components/ui/primitives";
import { api, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useHealth } from "@/lib/queries";

export default function AdminPage() {
  const ta = useTranslations("admin");
  const tn = useTranslations("nav");
  const tr = useTranslations("roles");
  const { can } = useAuth();
  const qc = useQueryClient();
  const health = useHealth();
  const [msg, setMsg] = useState<string | null>(null);
  const models = useQuery({ queryKey: ["models"], queryFn: () => api<{ id: string; component: string; version: string; description: string; active: boolean }[]>("/api/admin/model-versions") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<{ id: number; username: string; full_name: string; role: string; active: boolean }[]>("/api/admin/users"), enabled: can("user_admin") });
  const refresh = () => qc.invalidateQueries();
  const outage = useMutation({ mutationFn: (enabled: boolean) => post("/api/admin/providers/outage", { enabled }), onSuccess: refresh });
  const poll = useMutation({ mutationFn: () => post<{ results: unknown[] }>("/api/admin/providers/poll"), onSuccess: (r) => { setMsg(`${ta("poll")}: ${r.results.length}`); refresh(); } });
  const reset = useMutation({ mutationFn: () => post("/api/admin/demo/reset"), onSuccess: () => { setMsg(ta("resetDone")); refresh(); } });
  const offline = !!health.data?.external_offline;
  const err = outage.error || poll.error || reset.error;
  return (
    <div className="mx-auto max-w-5xl space-y-3 p-3">
      <h1 className="text-base font-bold tracking-wide">{tn("admin")}</h1>
      {err && <ErrorState error={err} />}
      {msg && <InlineNote tone="ok">{msg}</InlineNote>}
      <Panel title={ta("providers")}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={offline ? "offline" : "ok"}>{offline ? ta("outageOn") : ta("outageOff")}</Badge>
          {can("data_admin") && <Button size="sm" variant={offline ? "default" : "danger"} busy={outage.isPending} onClick={() => outage.mutate(!offline)}>{ta("outage")}</Button>}
          {can("data_admin") && <Button size="sm" busy={poll.isPending} onClick={() => poll.mutate()}>{ta("poll")}</Button>}
        </div>
      </Panel>
      {health.data?.demo_mode && can("user_admin") && (
        <Panel title={ta("demoReset")}>
          <p className="mb-2 text-[11px] text-ink-2">{ta("demoResetHint")}</p>
          <Button size="sm" variant="danger" busy={reset.isPending} onClick={() => { if (window.confirm(ta("demoResetConfirm"))) reset.mutate(); }}>{ta("demoReset")}</Button>
        </Panel>
      )}
      <Panel title={ta("models")}>
        {models.isLoading ? <Loading /> : (
          <table className="w-full text-xs [&_td]:px-1.5">
            <tbody>{(models.data || []).map((m) => (
              <tr key={m.id} className="border-t border-line/60"><td className="py-1 font-mono">{m.component}</td><td className="font-mono font-bold">{m.version}</td><td className="text-ink-2">{m.description}</td><td>{m.active && <Badge tone="ok" icon={false}>active</Badge>}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
      {can("user_admin") && (
        <Panel title={ta("users")}>
          <table className="w-full text-xs [&_td]:px-1.5">
            <tbody>{(users.data || []).map((u) => (
              <tr key={u.id} className="border-t border-line/60"><td className="py-1 font-mono">{u.username}</td><td>{u.full_name}</td><td>{tr.has(u.role) ? tr(u.role) : u.role}</td><td className="text-muted">{tr.has(`desc.${u.role}`) ? tr(`desc.${u.role}`) : ""}</td></tr>
            ))}</tbody>
          </table>
        </Panel>
      )}
    </div>
  );
}
