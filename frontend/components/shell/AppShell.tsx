"use client";

import clsx from "clsx";
import {
  Activity,
  BarChart3,
  BookOpen,
  ClipboardCheck,
  Database,
  FileText,
  Gauge,
  GitBranch,
  History,
  LayoutGrid,
  LogOut,
  Map as MapIcon,
  Settings,
  Timer,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useTranslations } from "use-intl";

import { Badge } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";
import { dateOnly, hhmm, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { useArea, useAreas, useHealth } from "@/lib/queries";
import { getManifest, IS_STATIC, REPO_URL } from "@/lib/staticDemo";

import { LanguageSwitcher } from "./LanguageSwitcher";

const AREA_NAV: { id: string; icon: LucideIcon; perm?: string }[] = [
  { id: "situation", icon: MapIcon },
  { id: "impact", icon: BarChart3 },
  { id: "windows", icon: Timer },
  { id: "bottlenecks", icon: Waypoints },
  { id: "plan", icon: GitBranch },
  { id: "operations", icon: Activity },
  { id: "validation", icon: ClipboardCheck },
  { id: "report", icon: FileText },
  { id: "data", icon: Database },
];

function NavItem({ href, icon: Icon, label, active }: { href: string; icon: LucideIcon; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "group relative flex items-center gap-2.5 rounded-[9px] px-2.5 py-[7px] text-[13px] font-medium transition-colors duration-200",
        active ? "bg-panel font-semibold text-ink shadow-[var(--shadow-card)] before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-accent" : "text-ink-2 hover:bg-panel/70 hover:text-ink",
      )}
    >
      <Icon aria-hidden className={clsx("h-4 w-4 shrink-0 transition-colors", active ? "text-accent" : "text-muted group-hover:text-accent")} />
      <span className="truncate">{label}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, ready, logout, can } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams<{ areaId?: string }>();
  const areaId = params?.areaId || null;
  const t = useTranslations("nav");
  const ta = useTranslations("app");
  const tr = useTranslations("roles");
  const tf = useTranslations("freshness");
  const { locale } = useLocale();
  const health = useHealth();
  const areas = useAreas();
  const area = useArea(areaId || "__none__");
  const areaInfo = areaId ? area.data : undefined;

  useEffect(() => {
    if (ready && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [ready, user, router, pathname]);

  if (!ready || !user) {
    return <div className="flex h-screen items-center justify-center text-xs text-muted">{ta("loading")}</div>;
  }

  const serverDown = health.isError || (health.data && health.data.database !== "ok");
  const extOffline = health.data?.external_offline;
  const currentArea = areaId || areas.data?.[0]?.id || "atbasar";
  const section = pathname.split("/")[3] || "";

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[100] focus:bg-panel focus:p-2">{ta("skipToContent")}</a>
      {/* top bar */}
      <header className="chrome chrome-bar flex h-[52px] shrink-0 items-center gap-3 px-3 shadow-[0_1px_0_rgba(15,34,56,0.12),0_4px_14px_-6px_rgba(15,34,56,0.35)] lg:px-4">
        <Link href="/overview" className="flex items-center gap-2">
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-[9px] bg-white/18 text-white ring-1 ring-white/25"><Gauge className="h-4 w-4" /></span>
          <span className="leading-tight">
            <span className="display block text-[14px]">ARGUS <span className="text-accent">FloodOps</span></span>
            <span className="hidden text-[10px] text-muted lg:block">{ta("subtitle")}</span>
          </span>
        </Link>
        {areas.data && areas.data.length > 0 && (
          <nav aria-label={t("switchArea")} className="ml-2 hidden items-center gap-1 md:flex">
            {areas.data.map((a) => {
              const active = a.id === areaId;
              const target = `/area/${a.id}/${section && areaId ? section : "situation"}`;
              return (
                <Link key={a.id} href={target} aria-current={active ? "true" : undefined}
                  className={clsx("rounded-full border px-3 py-1 text-[12px] font-semibold transition-colors", active ? "border-white bg-white text-[#1d4f8c]" : "border-line-2 text-ink-2 hover:border-white/70 hover:text-ink")}>
                  {pickName(a.names, locale)}
                </Link>
              );
            })}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-2">
          {serverDown && <Badge tone="offline">{tf("serverOffline")}</Badge>}
          {!serverDown && extOffline && <Badge tone="offline">{tf("externalOffline")}</Badge>}
          {areaInfo && (
            <div className="flex items-center gap-1.5 rounded-full border border-line-2 bg-white/10 py-0.5 pl-3 pr-1" title={areaInfo.clock_mode}>
              {areaInfo.clock_mode === "HISTORICAL" && <span className="tabular text-[11px] text-ink-2">{dateOnly(areaInfo.now, areaInfo.utc_offset_min)}</span>}
              <span className="tabular text-[15px] font-bold">{hhmm(areaInfo.now, areaInfo.utc_offset_min)}</span>
              <Badge tone={areaInfo.clock_mode === "LIVE" ? "live" : areaInfo.clock_mode === "HISTORICAL" ? "info" : "sim"}>
                {areaInfo.clock_mode === "LIVE" ? ta("liveClock") : areaInfo.clock_mode === "HISTORICAL" ? ta("historicalClock") : ta("simClock")}
              </Badge>
            </div>
          )}
          <LanguageSwitcher />
          <div className="hidden items-center gap-2 border-l border-line pl-2 sm:flex">
            <div className="text-right leading-tight">
              <div className="text-[11.5px] font-semibold">{IS_STATIC ? ta("staticUser") : user.full_name}</div>
              <div className="text-[10px] uppercase tracking-wider text-accent">{tr(user.role)}</div>
            </div>
            {!IS_STATIC && (
              <button onClick={() => { logout(); router.replace("/login"); }} title={ta("signOut")} aria-label={ta("signOut")}
                className="rounded p-1 text-muted hover:bg-panel-2 hover:text-ink"><LogOut className="h-4 w-4" /></button>
            )}
          </div>
        </div>
      </header>
      {IS_STATIC && (
        <div className="shrink-0 border-b border-accent/30 bg-accent/10 px-3 py-1 text-center text-[11px] text-ink-2">
          <b className="text-accent">{ta("staticBadge")}</b> — {ta("staticBanner", { date: dateOnly(getManifest()?.created ?? null, 300) })}
          {REPO_URL && <> · <a className="font-semibold text-accent underline" href={`${REPO_URL}#run-the-full-version`} target="_blank" rel="noreferrer">{ta("staticFull")}</a></>}
        </div>
      )}
      {areaInfo?.is_demo && (
        <div className="shrink-0 border-b border-sim/30 bg-sim/10 px-3 py-0.5 text-center text-[10.5px] font-semibold tracking-wider text-sim">{ta("demoBanner")}</div>
      )}
      {areaInfo && !areaInfo.is_demo && areaInfo.data_profile === "historical" && (
        <div className="shrink-0 border-b border-accent/30 bg-accent/5 px-3 py-0.5 text-center text-[10.5px] font-semibold tracking-wider text-accent">
          {areaInfo.role === "PORTABILITY_AND_BOTTLENECK_PILOT" ? ta("historicalBannerKok") : ta("historicalBanner")}
        </div>
      )}
      {serverDown && (
        <div role="alert" className="shrink-0 border-b border-offline/40 bg-offline/10 px-3 py-1 text-[11.5px] text-offline">
          <b>{tf("serverOffline")}</b> — {tf("serverOfflineDesc")}
        </div>
      )}
      {!serverDown && extOffline && (
        <div role="status" className="shrink-0 border-b border-offline/30 bg-offline/5 px-3 py-1 text-[11.5px] text-ink-2">
          <b className="text-offline">{tf("externalOffline")}</b> — {tf("externalOfflineDesc")}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <nav aria-label={ta("mainNav")} className="hidden w-60 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-line bg-panel-2 px-2.5 py-3 lg:flex">
          <NavItem href="/overview" icon={LayoutGrid} label={t("overview")} active={pathname.startsWith("/overview")} />
          <div className="mt-4 mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{t("areaSection")}</div>
          {AREA_NAV.map((n) => (
            <NavItem key={n.id} href={`/area/${currentArea}/${n.id}`} icon={n.icon} label={t(n.id)} active={!!areaId && section === n.id} />
          ))}
          <div className="mt-4 mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{t("systemSection")}</div>
          <NavItem href="/audit" icon={History} label={t("audit")} active={pathname.startsWith("/audit")} />
          <NavItem href="/help" icon={BookOpen} label={t("help")} active={pathname.startsWith("/help")} />
          {(can("data_admin") || can("user_admin")) && <NavItem href="/admin" icon={Settings} label={t("admin")} active={pathname.startsWith("/admin")} />}
          <div className="mt-auto border-t border-line px-2.5 pt-3 text-[10.5px] leading-snug text-muted">{ta("statement")}</div>
        </nav>
        {/* compact nav for tablets */}
        <nav aria-label={ta("mainNav")} className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-line bg-panel-2 py-2 lg:hidden">
          <Link href="/overview" title={t("overview")} className="rounded-[8px] p-2 text-muted hover:text-accent"><LayoutGrid className="h-4 w-4" /></Link>
          {AREA_NAV.map((n) => (
            <Link key={n.id} href={`/area/${currentArea}/${n.id}`} title={t(n.id)} aria-label={t(n.id)}
              className={clsx("rounded-[8px] p-2", section === n.id ? "bg-panel text-accent shadow-[var(--shadow-card)]" : "text-muted hover:text-accent")}><n.icon className="h-4 w-4" /></Link>
          ))}
          <Link href="/audit" title={t("audit")} className="rounded-[8px] p-2 text-muted hover:text-accent"><History className="h-4 w-4" /></Link>
          <Link href="/help" title={t("help")} aria-label={t("help")} className="rounded-[8px] p-2 text-muted hover:text-accent"><BookOpen className="h-4 w-4" /></Link>
        </nav>
        <main id="main" className="min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
