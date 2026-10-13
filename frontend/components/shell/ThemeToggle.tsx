"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import { useTranslations } from "use-intl";

import { useTheme } from "@/lib/theme";

export function ThemeToggle() {
  const t = useTranslations("app");
  const theme = useTheme((s) => s.theme);
  const setTheme = useTheme((s) => s.setTheme);
  const sync = useTheme((s) => s.sync);
  useEffect(() => sync(), [sync]);
  const next = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? t("themeDark") : t("themeLight");
  return (
    <button onClick={() => setTheme(next)} title={label} aria-label={label}
      className="grid h-7 w-7 place-items-center rounded-[4px] border border-line-2 text-ink-2 hover:bg-panel-2 hover:text-ink">
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
