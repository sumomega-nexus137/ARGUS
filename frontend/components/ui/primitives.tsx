"use client";

import clsx from "clsx";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Clock,
  FlaskConical,
  Info,
  Loader2,
  Radio,
  WifiOff,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useTranslations } from "use-intl";

import { ApiError } from "@/lib/api";
import { TONE_CLASS, TONE_TEXT, toneOf, type Tone } from "@/lib/status";

const TONE_ICON: Record<Tone, LucideIcon> = {
  ok: CheckCircle2, watch: AlertTriangle, warn: AlertTriangle, crit: AlertOctagon, info: Info, sim: FlaskConical,
  muted: CircleDashed, live: Radio, stale: Clock, offline: WifiOff,
};

export function Badge({ tone = "muted", icon = true, children, className, title }: {
  tone?: Tone; icon?: boolean; children: ReactNode; className?: string; title?: string;
}) {
  const Icon = TONE_ICON[tone];
  return (
    <span title={title} className={clsx("inline-flex items-center gap-1 rounded-[3px] border px-1.5 py-[1px] text-[10.5px] font-semibold uppercase tracking-wide whitespace-nowrap", TONE_CLASS[tone], className)}>
      {icon && <Icon aria-hidden className="h-3 w-3 shrink-0" />}
      {children}
    </span>
  );
}

/** Status badge: translates the code via the given namespace and picks the semantic tone. */
export function StatusBadge({ ns, code, className, icon = true }: { ns: string; code: string | null | undefined; className?: string; icon?: boolean }) {
  const t = useTranslations();
  if (!code) return null;
  const key = `${ns}.${code}`;
  return <Badge tone={toneOf(code)} className={className} icon={icon}>{t.has(key) ? t(key) : code}</Badge>;
}

export function Panel({ title, right, children, className, bodyClass, id }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; id?: string;
}) {
  return (
    <section id={id} className={clsx("rounded-[4px] border border-line bg-panel/95", className)}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-1.5">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-2">{title}</h2>
          {right}
        </header>
      )}
      <div className={clsx("p-3", bodyClass)}>{children}</div>
    </section>
  );
}

type BtnVariant = "primary" | "default" | "danger" | "ghost" | "accent";

export function Button({ variant = "default", size = "md", busy, icon: Icon, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant; size?: "sm" | "md" | "lg"; busy?: boolean; icon?: LucideIcon;
}) {
  const v: Record<BtnVariant, string> = {
    primary: "bg-accent-2 text-white hover:bg-accent border-accent-2",
    accent: "bg-accent/15 text-accent border-accent/50 hover:bg-accent/25",
    default: "bg-panel-2 text-ink border-line-2 hover:bg-panel-3",
    danger: "bg-crit/15 text-crit border-crit/50 hover:bg-crit/25",
    ghost: "bg-transparent text-ink-2 border-transparent hover:bg-panel-2",
  };
  const s = { sm: "h-6 px-2 text-[11px]", md: "h-7 px-2.5 text-xs", lg: "h-9 px-4 text-sm" }[size];
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={clsx("inline-flex items-center justify-center gap-1.5 rounded-[3px] border font-semibold tracking-wide transition-colors disabled:cursor-not-allowed disabled:opacity-50", v[variant], s, className)}
    >
      {busy ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : Icon ? <Icon aria-hidden className="h-3.5 w-3.5" /> : null}
      {children}
    </button>
  );
}

export function Metric({ label, value, sub, tone, big }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: Tone; big?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[10.5px] uppercase tracking-wider text-muted">{label}</div>
      <div className={clsx("tabular font-semibold leading-tight", big ? "text-2xl" : "text-lg", tone ? TONE_TEXT[tone] : "text-ink")}>{value}</div>
      {sub && <div className="truncate text-[11px] text-ink-2">{sub}</div>}
    </div>
  );
}

export function Loading({ label }: { label?: string }) {
  const t = useTranslations("common");
  return (
    <div role="status" className="flex items-center gap-2 p-3 text-xs text-muted">
      <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> {label ?? t("loading")}
    </div>
  );
}

export function Empty({ children }: { children?: ReactNode }) {
  const t = useTranslations("common");
  return <div className="p-3 text-xs text-muted">{children ?? t("noData")}</div>;
}

export function useErrorText() {
  const t = useTranslations("errors");
  return (err: unknown): string => {
    if (err instanceof ApiError) {
      if (t.has(err.code)) return t(err.code);
      return t("generic", { code: err.code });
    }
    return t("generic", { code: "client" });
  };
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const text = useErrorText();
  const tc = useTranslations("common");
  return (
    <div role="alert" className="flex items-center justify-between gap-2 rounded-[3px] border border-crit/40 bg-crit/10 p-2 text-xs text-crit">
      <span className="flex items-center gap-1.5"><AlertOctagon aria-hidden className="h-4 w-4" />{text(error)}</span>
      {onRetry && <Button size="sm" onClick={onRetry}>{tc("retry")}</Button>}
    </div>
  );
}

export function InlineNote({ tone = "info", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  const Icon = TONE_ICON[tone];
  return (
    <div className={clsx("flex items-start gap-1.5 rounded-[3px] border px-2 py-1.5 text-[11.5px] leading-snug", TONE_CLASS[tone], className)}>
      <Icon aria-hidden className="mt-[1px] h-3.5 w-3.5 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, className }: {
  tabs: { id: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; className?: string;
}) {
  return (
    <div role="tablist" className={clsx("flex flex-wrap gap-0.5 border-b border-line", className)}>
      {tabs.map((tb) => (
        <button
          key={tb.id}
          role="tab"
          aria-selected={value === tb.id}
          onClick={() => onChange(tb.id)}
          className={clsx(
            "-mb-px border-b-2 px-3 py-1.5 text-xs font-semibold tracking-wide",
            value === tb.id ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink-2",
          )}
        >
          {tb.label}
        </button>
      ))}
    </div>
  );
}

export function Dialog({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const tc = useTranslations("common");
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={clsx("max-h-[88vh] w-full overflow-auto rounded-[4px] border border-line-2 bg-panel shadow-2xl outline-none", wide ? "max-w-4xl" : "max-w-xl")}
      >
        <div className="sticky top-0 flex items-center justify-between border-b border-line bg-panel px-4 py-2">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button aria-label={tc("close")} onClick={onClose} className="rounded p-1 text-muted hover:bg-panel-2 hover:text-ink"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: ReactNode; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block text-xs">
      <span className="mb-0.5 block text-[10.5px] font-semibold uppercase tracking-wider text-muted">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-[10.5px] text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls = "h-7 w-full rounded-[3px] border border-line-2 bg-bg px-2 text-xs text-ink placeholder:text-muted focus:border-accent";

export function KeyValue({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
