"use client";

import { Gauge } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { LanguageSwitcher } from "@/components/shell/LanguageSwitcher";
import { Button, Field, inputCls, useErrorText } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

const LANDING: Record<Role, string> = {
  VIEWER: "/overview",
  OPERATOR: "/area/atbasar/operations",
  PLANNER: "/area/atbasar/plan",
  COMMANDER: "/overview",
  ADMIN: "/admin",
};

function LoginForm() {
  const t = useTranslations("auth");
  const ta = useTranslations("app");
  const tr = useTranslations("roles");
  const errText = useErrorText();
  const { login, user } = useAuth();
  const router = useRouter();
  const sp = useSearchParams();
  const [username, setUsername] = useState("planner");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<{ demo: boolean; password?: string; users: { username: string; role: Role; full_name: string }[] } | null>(null);

  useEffect(() => {
    api<typeof demo>("/api/auth/demo-users").then(setDemo).catch(() => setDemo(null));
  }, []);
  useEffect(() => {
    if (user) router.replace(sp.get("next") || LANDING[user.role]);
  }, [user, router, sp]);

  async function submit(u = username, p = password) {
    setBusy(true);
    setError(null);
    try {
      const me = await login(u, p);
      router.replace(sp.get("next") || LANDING[me.role]);
    } catch (e) {
      setError((e as { status?: number }).status === 401 ? t("invalid") : errText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(ellipse_at_top,#0f1b2a,#0a0e13_60%)] p-4">
      <div className="w-full max-w-md">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-[4px] bg-accent/20 text-accent"><Gauge className="h-5 w-5" /></span>
            <div>
              <div className="text-lg font-bold tracking-[0.16em]">ARGUS <span className="text-accent">FLOODOPS</span></div>
              <div className="text-[11px] text-muted">{ta("subtitle")}</div>
            </div>
          </div>
          <LanguageSwitcher />
        </div>
        <form
          className="space-y-3 rounded-[4px] border border-line bg-panel p-5"
          onSubmit={(e) => { e.preventDefault(); submit(); }}
        >
          <h1 className="text-sm font-semibold uppercase tracking-wider text-ink-2">{t("title")}</h1>
          <Field label={t("username")}>
            <input className={inputCls} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Field label={t("password")}>
            <input className={inputCls} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {error && <div role="alert" className="text-xs text-crit">{error}</div>}
          <Button type="submit" variant="primary" size="lg" className="w-full" busy={busy}>{busy ? t("signingIn") : t("signIn")}</Button>
          <p className="text-[11px] leading-snug text-muted">{t("humanInLoop")}</p>
        </form>
        {demo?.demo && (
          <div className="mt-3 rounded-[4px] border border-sim/30 bg-sim/5 p-3">
            <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-sim">
              <span>{t("demoAccounts")}</span>
              <span className="normal-case tracking-normal">{t("demoHint", { password: demo.password ?? "" })}</span>
            </div>
            <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
              {demo.users.map((u) => (
                <button key={u.username} type="button" onClick={() => { setUsername(u.username); setPassword(demo.password ?? ""); submit(u.username, demo.password ?? ""); }}
                  className="rounded-[3px] border border-line bg-panel px-2 py-1.5 text-left hover:border-accent/60">
                  <div className="text-xs font-semibold">{tr(u.role)} <span className="font-mono text-muted">· {u.username}</span></div>
                  <div className="text-[10.5px] leading-snug text-muted">{tr(`desc.${u.role}`)}</div>
                </button>
              ))}
            </div>
          </div>
        )}
        <p className="mt-4 text-center text-[11px] leading-snug text-muted">{ta("statement")}</p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
