"use client";

import {
  Activity, BarChart3, BookOpen, ClipboardCheck, Database, FileText, GitBranch, History, Keyboard, LayoutGrid, ListChecks,
  Map as MapIcon, MessageCircleQuestion, PlayCircle, Rocket, Settings, ShieldCheck, Tags, Timer, Upload, Users, Waypoints,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { type ReactNode } from "react";
import { useTranslations } from "use-intl";

import { Steps } from "@/components/help/ScreenHelp";
import { useAreas } from "@/lib/queries";

const SECTIONS: { id: string; icon: LucideIcon }[] = [
  { id: "start", icon: Rocket }, { id: "modes", icon: Tags }, { id: "map", icon: MapIcon }, { id: "timeline", icon: PlayCircle },
  { id: "screens", icon: LayoutGrid }, { id: "howto", icon: ListChecks }, { id: "addData", icon: Upload }, { id: "roles", icon: Users },
  { id: "honesty", icon: ShieldCheck }, { id: "keys", icon: Keyboard }, { id: "faq", icon: MessageCircleQuestion },
];
const SCREENS: { id: string; icon: LucideIcon; area: boolean }[] = [
  { id: "overview", icon: LayoutGrid, area: false }, { id: "situation", icon: MapIcon, area: true }, { id: "impact", icon: BarChart3, area: true },
  { id: "windows", icon: Timer, area: true }, { id: "bottlenecks", icon: Waypoints, area: true }, { id: "plan", icon: GitBranch, area: true },
  { id: "operations", icon: Activity, area: true }, { id: "validation", icon: ClipboardCheck, area: true }, { id: "report", icon: FileText, area: true },
  { id: "data", icon: Database, area: true }, { id: "audit", icon: History, area: false }, { id: "admin", icon: Settings, area: false },
];
const RECIPES = ["checkPlan", "stress", "alternatives", "approve", "roadClosure", "scenario", "language", "offline"];
const DATA = ["observation", "import", "roadEvent", "export", "resource", "facility", "realdata"];
const MODES: { k: string; cls: string }[] = [
  { k: "LIVE", cls: "border-ok/60 bg-ok/15 text-ok" }, { k: "HISTORICAL", cls: "border-accent/60 bg-accent/15 text-accent" },
  { k: "SIMULATION", cls: "border-sim/60 bg-sim/15 text-sim" }, { k: "CACHED", cls: "border-warn/50 bg-warn/10 text-warn" },
  { k: "NOT_CONFIGURED", cls: "border-line-2 bg-panel-2 text-muted" }, { k: "VISUALIZATION", cls: "border-line-2 bg-panel-2 text-ink-2" },
];
const ACCOUNTS = ["viewer", "operator", "planner", "commander", "admin"];

function Section({ id, icon: Icon, title, children }: { id: string; icon: LucideIcon; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-4 rounded-[6px] border border-line bg-panel p-5">
      <h2 className="mb-3 flex items-center gap-2 text-[15px] font-bold"><span className="grid h-7 w-7 place-items-center rounded-[5px] bg-accent/15 text-accent"><Icon className="h-4 w-4" /></span>{title}</h2>
      {children}
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((s, i) => (
        <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-ink-2"><span aria-hidden className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />{s}</li>
      ))}
    </ul>
  );
}

export default function HelpPage() {
  const tg = useTranslations("guide");
  const tn = useTranslations("nav");
  const tq = useTranslations("questions");
  const tm = useTranslations("mode");
  const ta = useTranslations("app");
  const tmap = useTranslations("map");
  const tr = useTranslations("roles");
  const areas = useAreas();
  const areaId = areas.data?.[0]?.id ?? "atbasar";
  const modeLabel = (k: string) =>
    k === "HISTORICAL" ? ta("historicalClock") : k === "CACHED" ? `${tm("CACHED")} · ${tm("STALE")} · ${tm("OFFLINE")}` : k === "VISUALIZATION" ? tmap("fx") : tm(k);
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-[1180px] gap-6 p-4 lg:p-6">
        <nav aria-label={tg("title")} className="sticky top-4 hidden h-fit w-56 shrink-0 rounded-[6px] border border-line bg-panel p-2 lg:block">
          {SECTIONS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="flex items-center gap-2 rounded-[3px] px-2 py-1.5 text-[12.5px] text-ink-2 hover:bg-panel-2 hover:text-ink">
              <s.icon className="h-3.5 w-3.5 shrink-0 text-muted" />{tg(`toc.${s.id}`)}
            </a>
          ))}
        </nav>
        <main className="min-w-0 flex-1 space-y-4">
          <header className="rounded-[6px] border border-accent/30 bg-[linear-gradient(135deg,rgba(63,179,255,.16),rgba(63,179,255,.02))] p-5">
            <div className="flex items-center gap-2 text-accent"><BookOpen className="h-5 w-5" /><h1 className="text-xl font-bold text-ink">{tg("title")}</h1></div>
            <p className="mt-1 text-[13.5px] text-ink-2">{tg("subtitle")}</p>
          </header>

          <Section id="start" icon={Rocket} title={tg("toc.start")}>
            <p className="mb-3 text-[13.5px] leading-relaxed">{tg("start.intro")}</p>
            <Steps steps={tg.raw("start.steps") as string[]} />
          </Section>

          <Section id="modes" icon={Tags} title={tg("toc.modes")}>
            <p className="mb-3 text-[13px] text-ink-2">{tg("modes.intro")}</p>
            <div className="grid gap-2 md:grid-cols-2">
              {MODES.map((m) => (
                <div key={m.k} className="rounded-[4px] border border-line bg-panel-2 p-3">
                  <span className={`inline-flex rounded-[3px] border px-2 py-0.5 text-[11px] font-extrabold uppercase tracking-wider ${m.cls}`}>{modeLabel(m.k)}</span>
                  <p className="mt-1.5 text-[12.5px] leading-snug text-ink-2">{tg(`modes.items.${m.k}`)}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="map" icon={MapIcon} title={tg("toc.map")}><Bullets items={tg.raw("map.items") as string[]} /></Section>
          <Section id="timeline" icon={PlayCircle} title={tg("toc.timeline")}><Bullets items={tg.raw("timeline.items") as string[]} /></Section>

          <Section id="screens" icon={LayoutGrid} title={tg("toc.screens")}>
            <div className="grid gap-2 md:grid-cols-2">
              {SCREENS.map((s) => (
                <Link key={s.id} href={s.area ? `/area/${areaId}/${s.id}` : `/${s.id}`} className="group rounded-[4px] border border-line bg-panel-2 p-3 hover:border-accent/50">
                  <div className="flex items-center gap-2 text-[13px] font-bold"><s.icon className="h-4 w-4 text-accent" />{tn(s.id)}</div>
                  <div className="text-[11.5px] text-accent">{tq(s.id)}</div>
                  <p className="mt-1 text-[12.5px] leading-snug text-ink-2">{tg(`screens.${s.id}.what`)}</p>
                  <p className="mt-1 text-[12px] leading-snug text-muted">→ {tg(`screens.${s.id}.how`)}</p>
                </Link>
              ))}
            </div>
          </Section>

          <Section id="howto" icon={ListChecks} title={tg("toc.howto")}>
            <div className="grid gap-3 md:grid-cols-2">
              {RECIPES.map((r) => (
                <div key={r} className="rounded-[4px] border border-line bg-panel-2 p-3">
                  <h3 className="mb-2 text-[13px] font-bold">{tg(`howto.${r}.title`)}</h3>
                  <Steps steps={tg.raw(`howto.${r}.steps`) as string[]} />
                </div>
              ))}
            </div>
          </Section>

          <Section id="addData" icon={Upload} title={tg("toc.addData")}>
            <p className="mb-3 text-[13px] text-ink-2">{tg("addData.intro")}</p>
            <div className="grid gap-3 md:grid-cols-2">
              {DATA.map((r) => (
                <div key={r} className="rounded-[4px] border border-line bg-panel-2 p-3">
                  <h3 className="mb-2 text-[13px] font-bold">{tg(`addData.${r}.title`)}</h3>
                  <Steps steps={tg.raw(`addData.${r}.steps`) as string[]} />
                </div>
              ))}
            </div>
          </Section>

          <Section id="roles" icon={Users} title={tg("toc.roles")}>
            <p className="mb-3 text-[13px] text-ink-2">{tg("roles.intro")}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead className="text-left text-[10.5px] uppercase tracking-wider text-muted">
                  <tr><th className="py-1 pr-3">{tg("roles.account")}</th><th className="py-1 pr-3">{tg("roles.role")}</th><th className="py-1">{tg("roles.can")}</th></tr>
                </thead>
                <tbody>
                  {ACCOUNTS.map((a) => (
                    <tr key={a} className="border-t border-line/70">
                      <td className="py-1.5 pr-3 font-mono text-accent">{a}</td>
                      <td className="py-1.5 pr-3 font-semibold">{tr(a.toUpperCase())}</td>
                      <td className="py-1.5 text-ink-2">{tr(`desc.${a.toUpperCase()}`)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="honesty" icon={ShieldCheck} title={tg("toc.honesty")}><Bullets items={tg.raw("honesty.items") as string[]} /></Section>
          <Section id="keys" icon={Keyboard} title={tg("toc.keys")}><Bullets items={tg.raw("keys.items") as string[]} /></Section>

          <Section id="faq" icon={MessageCircleQuestion} title={tg("toc.faq")}>
            <div className="space-y-2">
              {(tg.raw("faq.items") as { q: string; a: string }[]).map((f, i) => (
                <details key={i} className="group rounded-[4px] border border-line bg-panel-2 px-3 py-2 open:border-accent/40">
                  <summary className="cursor-pointer list-none text-[13px] font-semibold marker:hidden">
                    <span className="mr-2 text-accent group-open:rotate-90">›</span>{f.q}
                  </summary>
                  <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">{f.a}</p>
                </details>
              ))}
            </div>
          </Section>
        </main>
      </div>
    </div>
  );
}
