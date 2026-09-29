"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider } from "@/lib/i18n";
import type { Locale } from "@/lib/types";

export function Providers({ locale, children }: { locale: Locale; children: ReactNode }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            // keep showing the last successful data while the server / network is unavailable (degraded mode)
            retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
            placeholderData: (prev: unknown) => prev,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <AuthProvider>{children}</AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
