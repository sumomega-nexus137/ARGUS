"use client";

import { Gauge } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useTranslations } from "use-intl";

import { ValleyCanvas } from "@/components/brand/ValleyCanvas";
import { LanguageSwitcher } from "@/components/shell/LanguageSwitcher";
import { Button, Field, inputCls, useErrorText } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { IS_STATIC } from "@/lib/staticDemo";
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
  const ti = useTranslations("auth.intro");
  const valley = useMemo(() => ({
    closesIn: ti("closesIn"), closed: ti("closed"), open: ti("open"), level: ti("level"), site: ti("site"),
  }), [ti]);
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
    if (user) router.replace(sp.get("next") || (IS_STATIC ? "/overview" : LANDING[user.role]));
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
    <div className="min-h-screen bg-[radial-gradient(ellipse_80%_60%_at_100%_0%,color-mix(in_srgb,var(--color-accent)_12%,var(--color-bg)),var(--color-bg)_70%)]">
      <div className="mx-auto grid min-h-screen max-w-[1240px] grid-cols-1 items-center gap-10 px-5 py-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-16 lg:px-10">
        <section className="order-2 lg:order-1">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[11px] bg-accent-2 text-white shadow-[var(--shadow-card)]"><Gauge className="h-5 w-5" /></span>
            <div className="display text-[18px]">ARGUS <span className="text-accent">FloodOps</span></div>
          </div>
          <p className="mt-8 text-[11.5px] font-semibold uppercase tracking-[0.16em] text-accent">{ti("eyebrow")}</p>
          <h2 className="display mt-3 max-w-[22ch] text-[clamp(1.6rem,2.8vw,2.5rem)] text-ink">
            {ti("title")} <span className="text-accent">{ti("titleAccent")}</span>
          </h2>
          <p className="mt-4 max-w-[60ch] text-[14.5px] leading-relaxed text-ink-2">{ti("lead")}</p>
          <figure className="mt-8 hidden sm:block">
            <ValleyCanvas labels={valley} />
            <figcaption className="mt-2.5 flex flex-wrap justify-between gap-2 text-[11.5px] tracking-wide text-muted">
              <span>{ti("caption")}</span>
              <span className="tabular">{ti("coords")}</span>
            </figcaption>
          </figure>
        </section>

        <section className="order-1 w-full max-w-md justify-self-center lg:order-2">
          <div className="mb-4 flex justify-end"><LanguageSwitcher /></div>
          <form
            className="rise space-y-3.5 rounded-[16px] border border-line bg-panel p-6 shadow-[var(--shadow-lift)]"
            onSubmit={(e) => { e.preventDefault(); submit(); }}
          >
            <h1 className="display text-[20px]">{t("title")}</h1>
            <p className="text-[12px] text-muted">{ta("subtitle")}</p>
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
            <div className="rise mt-3 rounded-[14px] border border-sim/25 bg-sim/5 p-3.5">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-1 text-[11px] font-semibold uppercase tracking-wider text-sim">
                <span>{t("demoAccounts")}</span>
                <span className="normal-case tracking-normal">{t("demoHint", { password: demo.password ?? "" })}</span>
              </div>
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {demo.users.map((u) => (
                  <button key={u.username} type="button" onClick={() => { setUsername(u.username); setPassword(demo.password ?? ""); submit(u.username, demo.password ?? ""); }}
                    className="lift rounded-[10px] border border-line bg-panel px-2.5 py-2 text-left hover:border-accent/60">
                    <div className="text-xs font-semibold">{tr(u.role)} <span className="font-normal text-muted">· {u.username}</span></div>
                    <div className="text-[10.5px] leading-snug text-muted">{tr(`desc.${u.role}`)}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
          <p className="mt-4 text-center text-[11px] leading-snug text-muted">{ta("statement")}</p>
        </section>
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
