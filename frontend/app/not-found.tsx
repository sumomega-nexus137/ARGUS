"use client";

import { Compass } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "use-intl";

export default function NotFound() {
  const t = useTranslations("crash");
  return (
    <div className="mx-auto mt-16 max-w-md p-4 text-center">
      <Compass className="mx-auto mb-2 h-8 w-8 text-accent" />
      <h1 className="text-lg font-bold">{t("notFoundTitle")}</h1>
      <p className="mt-1 text-sm text-ink-2">{t("notFoundBody")}</p>
      <Link href="/overview" className="mt-4 inline-flex h-8 items-center rounded-[3px] border border-accent-2 bg-accent-2 px-4 text-xs font-semibold text-white">{t("overview")}</Link>
    </div>
  );
}
