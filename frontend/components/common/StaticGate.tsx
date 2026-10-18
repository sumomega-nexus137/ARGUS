"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useTranslations } from "use-intl";

import { IS_STATIC, loadManifest } from "@/lib/staticDemo";

/** Static online demo: render the console only after the snapshot index is loaded (map sources resolve synchronously). */
export function StaticGate({ children }: { children: ReactNode }) {
  const t = useTranslations("app");
  const [state, setState] = useState<"loading" | "ready" | "error">(IS_STATIC ? "loading" : "ready");
  useEffect(() => {
    if (!IS_STATIC) return;
    loadManifest().then(() => setState("ready")).catch(() => setState("error"));
  }, []);
  if (state === "ready") return <>{children}</>;
  return (
    <div className="flex h-screen items-center justify-center p-6 text-center text-sm text-muted">
      {state === "loading" ? t("loading") : t("staticLoadFailed")}
    </div>
  );
}
