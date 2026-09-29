import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";

import type { Locale } from "@/lib/types";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "ARGUS FloodOps",
  description: "Regional Flood Decision & Response System",
};

export const viewport: Viewport = { themeColor: "#0a0e13", width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const c = await cookies();
  const raw = c.get("argus_locale")?.value;
  const locale: Locale = raw === "ru" || raw === "en" || raw === "kk" ? raw : "kk";
  return (
    <html lang={locale} className="dark">
      <body className="min-h-screen antialiased">
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
