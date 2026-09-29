"use client";

import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { ScreenHeader } from "@/components/common/ScreenHeader";
import { Button, ErrorState, Loading } from "@/components/ui/primitives";
import { getToken } from "@/lib/api";
import { LOCALE_LABEL, LOCALES, useLocale } from "@/lib/i18n";
import type { Locale } from "@/lib/types";

/** Operational briefing. The report language is independent of the UI language. */
export default function ReportPage() {
  const { areaId, area } = useAreaCtx();
  const tr = useTranslations("report");
  const { locale } = useLocale();
  const [lang, setLang] = useState<Locale>(locale);
  const frame = useRef<HTMLIFrameElement>(null);
  const q = useQuery({
    queryKey: ["report", areaId, area?.data_version, lang],
    queryFn: async () => {
      const r = await fetch(`/api/areas/${areaId}/report.html?lang=${lang}`, { headers: { Authorization: `Bearer ${getToken() || ""}` } });
      if (!r.ok) throw new Error(String(r.status));
      return r.text();
    },
  });
  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <ScreenHeader screen="report" right={
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted">{tr("language")}</span>
          <div role="radiogroup" aria-label={tr("language")} className="flex overflow-hidden rounded-[3px] border border-line-2">
            {LOCALES.map((l) => (
              <button key={l} role="radio" aria-checked={lang === l} onClick={() => setLang(l)}
                className={`px-2 py-1 text-[11px] font-bold ${lang === l ? "bg-accent/20 text-accent" : "text-ink-2"}`}>{LOCALE_LABEL[l]}</button>
            ))}
          </div>
          <Button size="sm" icon={Printer} onClick={() => frame.current?.contentWindow?.print()}>{tr("print")}</Button>
        </div>
      } />
      {q.isLoading && <Loading />}
      {q.isError && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && <iframe ref={frame} title={tr("title")} srcDoc={q.data} className="min-h-[70vh] w-full flex-1 rounded-[4px] border border-line bg-white" />}
    </div>
  );
}
