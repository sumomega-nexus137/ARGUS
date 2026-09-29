"use client";

import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import { useTranslations } from "use-intl";

import { TONE_CLASS } from "@/lib/status";
import type { CausalChain as Chain, ChainNode } from "@/lib/types";

const TIME_KEYS = new Set(["from", "to", "at", "departure", "deadline", "latest_departure", "completion"]);

export function useChainText(fmt: (m: number | null | undefined) => string, siteName?: (id: string) => string) {
  const t = useTranslations("causal");
  return (n: ChainNode): string => {
    const params: Record<string, string | number> = {};
    for (const [k, v] of Object.entries(n.params || {})) {
      if (TIME_KEYS.has(k)) params[k] = typeof v === "number" ? fmt(v) : "—";
      else if (k === "site" && typeof v === "string") params[k] = siteName ? siteName(v) : v;
      else if (typeof v === "number") params[k] = Math.round(v * 10) / 10;
      else if (v === null || v === undefined) params[k] = "—";
      else params[k] = typeof v === "string" ? v : JSON.stringify(v);
    }
    // fill placeholders that may be absent in params
    for (const k of ["road", "resource", "task", "site", "minutes", "from_member", "to_member", "extra_min", "slack_min", "at", "from", "to"]) {
      if (params[k] === undefined) params[k] = "—";
    }
    return t.has(n.type) ? t(n.type, params) : n.type;
  };
}

export function CausalChainView({ chain, fmt, siteName, compact }: { chain: Chain; fmt: (m: number | null | undefined) => string; siteName?: (id: string) => string; compact?: boolean }) {
  const text = useChainText(fmt, siteName);
  return (
    <ol className={clsx("flex flex-wrap items-stretch gap-1", compact ? "text-[10.5px]" : "text-[11.5px]")} aria-label={chain.task}>
      {chain.nodes.map((n, i) => (
        <li key={i} className="flex items-center gap-1">
          <span className={clsx("rounded-[3px] border px-2 py-1 font-semibold leading-tight tracking-wide", TONE_CLASS[n.severity === "critical" ? "crit" : n.severity === "warning" ? "warn" : "info"])}>
            {text(n)}
          </span>
          {i < chain.nodes.length - 1 && <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted" />}
        </li>
      ))}
    </ol>
  );
}
