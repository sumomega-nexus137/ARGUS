"use client";

import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { ScreenHelp } from "@/components/help/ScreenHelp";
import { pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";

/** ONE SCREEN = ONE QUESTION: every screen states the question it answers. */
export function ScreenHeader({ screen, right }: { screen: string; right?: React.ReactNode }) {
  const tn = useTranslations("nav");
  const tq = useTranslations("questions");
  const { area } = useAreaCtx();
  const { locale } = useLocale();
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-[14rem] flex-1">
        <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-muted">{area ? pickName(area.names, locale) : ""}</div>
        <h1 className="display mt-0.5 text-[17px] text-ink">{tn(screen)}</h1>
        <p className="mt-0.5 text-[13px] text-accent">{tq(screen)}</p>
      </div>
      <div className="flex max-w-full flex-wrap items-start justify-end gap-2">
        {right}
        <ScreenHelp screen={screen} />
      </div>
    </div>
  );
}
