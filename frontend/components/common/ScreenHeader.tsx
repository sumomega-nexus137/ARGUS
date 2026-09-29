"use client";

import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";

/** ONE SCREEN = ONE QUESTION: every screen states the question it answers. */
export function ScreenHeader({ screen, right }: { screen: string; right?: React.ReactNode }) {
  const tn = useTranslations("nav");
  const tq = useTranslations("questions");
  const { area } = useAreaCtx();
  const { locale } = useLocale();
  return (
    <div className="flex items-start justify-between gap-2">
      <div>
        <div className="text-[10.5px] font-semibold uppercase tracking-wider text-muted">{area ? pickName(area.names, locale) : ""}</div>
        <h1 className="text-base font-bold tracking-wide">{tn(screen)}</h1>
        <p className="text-[12.5px] text-accent">{tq(screen)}</p>
      </div>
      {right}
    </div>
  );
}
