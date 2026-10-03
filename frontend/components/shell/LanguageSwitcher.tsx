"use client";

import clsx from "clsx";

import { LOCALE_LABEL, LOCALES, useLocale } from "@/lib/i18n";

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useLocale();
  return (
    <div role="group" aria-label="Language / Тіл / Язык" /* i18n-ignore: deliberately trilingual */ className={clsx("flex items-center overflow-hidden rounded-[3px] border border-line-2", className)}>
      {LOCALES.map((l, i) => (
        <button
          key={l}
          lang={l}
          aria-pressed={locale === l}
          onClick={() => setLocale(l)}
          className={clsx(
            "h-6 px-2 text-[11px] font-bold tracking-wider",
            i > 0 && "border-l border-line-2",
            locale === l ? "bg-accent/20 text-accent" : "text-muted hover:bg-panel-2 hover:text-ink",
          )}
        >
          {LOCALE_LABEL[l]}
        </button>
      ))}
    </div>
  );
}
