"use client";

import { AlertTriangle, Home, RefreshCw, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/ui/primitives";

/** Friendly, localized replacement for a crashed screen: nothing was changed, try again or go elsewhere. */
export function CrashCard({ error, retry, compact }: { error: Error & { digest?: string }; retry?: () => void; compact?: boolean }) {
  const t = useTranslations("crash");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    console.error("[ARGUS] screen error:", error);
  }, [error]);
  if (compact) {
    return (
      <div role="alert" className="grid h-full w-full place-items-center bg-bg/80 p-4">
        <div className="max-w-sm rounded-[6px] border border-warn/40 bg-panel p-3 text-center text-xs">
          <AlertTriangle className="mx-auto mb-1 h-5 w-5 text-warn" />
          <div className="font-semibold">{t("widgetTitle")}</div>
          <p className="mt-1 text-ink-2">{t("widgetBody")}</p>
          {retry && <Button size="sm" className="mt-2" icon={RotateCcw} onClick={retry}>{t("retry")}</Button>}
        </div>
      </div>
    );
  }
  return (
    <div role="alert" className="mx-auto mt-10 max-w-xl p-4">
      <div className="rounded-[8px] border border-warn/40 bg-panel/95 p-5 shadow-xl">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-warn/15 text-warn"><AlertTriangle className="h-5 w-5" /></div>
          <div className="min-w-0">
            <h1 className="text-base font-bold">{t("title")}</h1>
            <p className="mt-1 text-sm leading-relaxed text-ink-2">{t("body")}</p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {retry && <Button variant="primary" icon={RotateCcw} onClick={retry}>{t("retry")}</Button>}
          <Button icon={RefreshCw} onClick={() => window.location.reload()}>{t("reload")}</Button>
          <Link href="/overview" className="inline-flex h-7 items-center gap-1.5 rounded-[3px] border border-line-2 px-2.5 text-xs font-semibold hover:bg-panel-2"><Home className="h-3.5 w-3.5" />{t("overview")}</Link>
        </div>
        <button onClick={() => setOpen((o) => !o)} className="mt-4 text-[11px] text-muted underline">{t("details")}</button>
        {open && (
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-[3px] border border-line bg-bg p-2 font-mono text-[10.5px] text-ink-2">
            {error.message || "—"}{error.digest ? `\n#${error.digest}` : ""}
          </pre>
        )}
      </div>
    </div>
  );
}
