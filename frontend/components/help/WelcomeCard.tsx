"use client";

import { BookOpen, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

const KEY = "argus.welcome.v1";

/** First-visit welcome: three steps to get going and a link to the guide. Dismissed once per browser. */
export function WelcomeCard() {
  const tg = useTranslations("guide");
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (!localStorage.getItem(KEY)) setShow(true);
    } catch { /* private mode: never block the UI */ }
  }, []);
  const close = () => {
    setShow(false);
    try { localStorage.setItem(KEY, "1"); } catch { /* ignore */ }
  };
  if (!show) return null;
  const steps = tg.raw("welcome.steps") as string[];
  return (
    <div className="relative overflow-hidden rounded-[4px] border border-accent/40 bg-[linear-gradient(135deg,rgba(63,179,255,.14),rgba(63,179,255,.03))] p-4">
      <button onClick={close} aria-label={tg("close")} className="absolute right-2 top-2 rounded p-1 text-muted hover:bg-panel-2 hover:text-ink"><X className="h-4 w-4" /></button>
      <div className="flex items-center gap-2 text-accent"><Sparkles className="h-4 w-4" /><h2 className="text-[15px] font-bold text-ink">{tg("welcome.title")}</h2></div>
      <p className="mt-1 max-w-[640px] text-[12.5px] leading-snug text-ink-2">{tg("welcome.body")}</p>
      <ol className="mt-3 grid gap-2 sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 rounded-[3px] border border-line bg-panel/70 p-2 text-[12px] leading-snug">
            <span className="tabular grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent text-[11px] font-bold text-bg">{i + 1}</span>{s}
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link href="/help" onClick={close} className="flex items-center gap-1.5 rounded-[3px] border border-accent/60 bg-accent/20 px-3 py-1.5 text-[12px] font-semibold text-accent hover:bg-accent/30">
          <BookOpen className="h-3.5 w-3.5" />{tg("welcome.guide")}
        </Link>
        <button onClick={close} className="rounded-[3px] border border-line-2 px-3 py-1.5 text-[12px] font-semibold text-ink-2 hover:bg-panel-2">{tg("welcome.start")}</button>
      </div>
    </div>
  );
}
