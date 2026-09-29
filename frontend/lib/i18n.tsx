"use client";

// Internationalisation: Kazakh (default), Russian, English. Messages live in /messages/*.json and are
// rendered with ICU MessageFormat via use-intl. The chosen locale persists (localStorage + cookie).
import { IntlProvider } from "use-intl";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import en from "@/messages/en.json";
import kk from "@/messages/kk.json";
import ru from "@/messages/ru.json";
import type { Locale } from "./types";

export const LOCALES: Locale[] = ["kk", "ru", "en"];
export const DEFAULT_LOCALE: Locale = "kk";
export const LOCALE_LABEL: Record<Locale, string> = { kk: "ҚАЗ", ru: "РУС", en: "ENG" };
const MESSAGES = { kk, ru, en } as const;
const KEY = "argus.locale";

interface LocaleCtx {
  locale: Locale;
  setLocale: (l: Locale) => void;
}

const Ctx = createContext<LocaleCtx>({ locale: DEFAULT_LOCALE, setLocale: () => {} });

export function useLocale(): LocaleCtx {
  return useContext(Ctx);
}

function readStored(): Locale | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v && (LOCALES as string[]).includes(v) ? (v as Locale) : null;
  } catch {
    return null;
  }
}

export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    const stored = readStored();
    if (stored && stored !== locale) setLocaleState(stored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      window.localStorage.setItem(KEY, l);
    } catch {
      /* ignore */
    }
    document.cookie = `argus_locale=${l}; path=/; max-age=31536000; samesite=lax`;
  }, []);

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return (
    <Ctx.Provider value={value}>
      <IntlProvider
        locale={locale}
        messages={MESSAGES[locale]}
        timeZone="Asia/Almaty"
        onError={(err) => {
          if (process.env.NODE_ENV !== "production") console.warn("[i18n]", err.message);
        }}
        getMessageFallback={({ namespace, key }) => `${namespace ? namespace + "." : ""}${key}`}
      >
        {children}
      </IntlProvider>
    </Ctx.Provider>
  );
}
