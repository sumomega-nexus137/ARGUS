"use client";

import en from "@/messages/en.json";
import kk from "@/messages/kk.json";
import ru from "@/messages/ru.json";

import "./globals.css";

const MESSAGES = { kk, ru, en } as const;

function locale(): keyof typeof MESSAGES {
  try {
    const l = typeof window !== "undefined" ? window.localStorage.getItem("argus.locale") : null;
    return l === "ru" || l === "en" ? l : "kk";
  } catch {
    return "kk";
  }
}

/** Last-resort boundary (root layout failed): no providers are available here, so messages are read directly. */
export default function GlobalError({ error, retry, reset }: { error: Error & { digest?: string }; retry?: () => void; reset?: () => void }) {
  const l = locale();
  const t = MESSAGES[l].crash;
  const again = retry ?? reset;
  return (
    <html lang={l} className="dark">
      <body className="min-h-screen bg-bg text-ink antialiased">
        <div role="alert" className="mx-auto mt-16 max-w-xl rounded-[8px] border border-warn/40 bg-panel p-5">
          <h1 className="text-base font-bold">{t.title}</h1>
          <p className="mt-1 text-sm text-ink-2">{t.body}</p>
          <div className="mt-4 flex gap-2">
            {again && <button className="rounded-[3px] border border-accent-2 bg-accent-2 px-3 py-1 text-xs font-semibold text-white" onClick={again}>{t.retry}</button>}
            {/* a full document load on purpose: the router may be what failed */}
            <a className="rounded-[3px] border border-line-2 px-3 py-1 text-xs font-semibold" href="/overview">{t.overview}</a>
          </div>
          {error.digest && <p className="mt-3 font-mono text-[10.5px] text-muted">#{error.digest}</p>}
        </div>
      </body>
    </html>
  );
}
