"use client";

import { BookOpen, CircleHelp, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

/** Which step-by-step recipes belong to which screen (keys of guide.howto / guide.addData). */
export const SCREEN_RECIPES: Record<string, { ns: "howto" | "addData"; key: string }[]> = {
  overview: [{ ns: "howto", key: "language" }],
  situation: [{ ns: "howto", key: "scenario" }, { ns: "howto", key: "offline" }],
  impact: [],
  windows: [{ ns: "howto", key: "checkPlan" }],
  bottlenecks: [],
  plan: [{ ns: "howto", key: "checkPlan" }, { ns: "howto", key: "stress" }, { ns: "howto", key: "alternatives" }],
  operations: [{ ns: "howto", key: "roadClosure" }, { ns: "howto", key: "approve" }],
  validation: [],
  report: [{ ns: "howto", key: "language" }],
  data: [{ ns: "addData", key: "import" }, { ns: "addData", key: "observation" }, { ns: "addData", key: "export" }, { ns: "addData", key: "roadEvent" }, { ns: "addData", key: "resource" }],
  audit: [],
  admin: [{ ns: "howto", key: "offline" }],
};

export function Steps({ steps }: { steps: string[] }) {
  return (
    <ol className="space-y-1.5">
      {steps.map((s, i) => (
        <li key={i} className="flex gap-2 text-[12.5px] leading-snug text-ink-2">
          <span className="tabular mt-[1px] grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full bg-accent/20 text-[10.5px] font-bold text-accent">{i + 1}</span>
          <span>{s}</span>
        </li>
      ))}
    </ol>
  );
}

/** "?" button that opens a side panel explaining the current screen in plain words. */
export function ScreenHelp({ screen }: { screen: string }) {
  const tg = useTranslations("guide");
  const tn = useTranslations("nav");
  const tq = useTranslations("questions");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const recipes = SCREEN_RECIPES[screen] ?? [];
  return (
    <>
      <button onClick={() => setOpen(true)} aria-label={tg("open")} title={tg("open")}
        className="flex h-7 shrink-0 items-center gap-1.5 rounded-[3px] border border-accent/40 bg-accent/10 px-2 text-[11.5px] font-semibold text-accent hover:bg-accent/20">
        <CircleHelp className="h-3.5 w-3.5" />{tg("open")}
      </button>
      {open && (
        <div className="fixed inset-0 z-[60] flex justify-end bg-black/40" onClick={() => setOpen(false)}>
          <aside role="dialog" aria-modal="true" aria-label={tg("onThisScreen")} onClick={(e) => e.stopPropagation()}
            className="flex h-full w-full max-w-[420px] flex-col border-l border-line-2 bg-panel shadow-2xl">
            <header className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
              <div>
                <div className="text-[10.5px] font-bold uppercase tracking-wider text-accent">{tg("onThisScreen")}</div>
                <h2 className="text-base font-bold">{tn.has(screen) ? tn(screen) : screen}</h2>
                {tq.has(screen) && <p className="text-[12.5px] text-ink-2">{tq(screen)}</p>}
              </div>
              <button onClick={() => setOpen(false)} aria-label={tg("close")} className="rounded p-1 text-muted hover:bg-panel-2 hover:text-ink"><X className="h-4 w-4" /></button>
            </header>
            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
              <section>
                <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wider text-muted">{tg("whatFor")}</h3>
                <p className="text-[13px] leading-snug">{tg(`screens.${screen}.what`)}</p>
              </section>
              <section>
                <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wider text-muted">{tg("howTo")}</h3>
                <p className="text-[13px] leading-snug">{tg(`screens.${screen}.how`)}</p>
              </section>
              {recipes.map((r) => (
                <section key={r.key} className="rounded-[4px] border border-line bg-panel-2 p-3">
                  <h3 className="mb-2 text-[12.5px] font-bold">{tg(`${r.ns}.${r.key}.title`)}</h3>
                  <Steps steps={tg.raw(`${r.ns}.${r.key}.steps`) as string[]} />
                </section>
              ))}
            </div>
            <footer className="border-t border-line px-4 py-3">
              <Link href="/help" onClick={() => setOpen(false)} className="flex items-center justify-center gap-2 rounded-[3px] border border-accent/50 bg-accent/15 px-3 py-2 text-[12.5px] font-semibold text-accent hover:bg-accent/25">
                <BookOpen className="h-4 w-4" />{tg("openFull")}
              </Link>
            </footer>
          </aside>
        </div>
      )}
    </>
  );
}
