import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";

import type { Locale } from "@/lib/types";

import "@fontsource-variable/inter";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "ARGUS FloodOps",
  description: "Regional Flood Decision & Response System",
};

export const viewport: Viewport = { themeColor: "#2f63a0", width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // the static online demo has no server: the language comes from the browser (localStorage) after load
  const raw = process.env.ARGUS_STATIC_EXPORT === "1" ? undefined : (await cookies()).get("argus_locale")?.value;
  const locale: Locale = raw === "ru" || raw === "en" || raw === "kk" ? raw : "kk";
  return (
    <html lang={locale}>
      <body className="min-h-screen antialiased">
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
