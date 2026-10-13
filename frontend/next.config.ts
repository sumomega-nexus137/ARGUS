import type { NextConfig } from "next";

// Two builds from one code base:
//  * server (default): the console proxies /api → FastAPI (the frontend never talks to external providers);
//  * static online demo (ARGUS_STATIC_EXPORT=1): plain files for GitHub Pages / any static host, answering API
//    calls from the recorded snapshot in public/demo-data (see lib/staticDemo.ts, scripts/static_demo/record.py).
const API_URL = process.env.ARGUS_API_URL || "http://127.0.0.1:8000";
const STATIC = process.env.ARGUS_STATIC_EXPORT === "1";
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

const serverConfig: NextConfig = {
  output: process.env.ARGUS_STANDALONE === "1" ? "standalone" : undefined,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  experimental: {
    // optimizer / stress-test / recompute calls can exceed the 30 s proxy default on a modest laptop
    proxyTimeout: 300_000,
  },
};

const staticConfig: NextConfig = {
  output: "export",
  basePath: BASE_PATH || undefined,
  trailingSlash: true,
  images: { unoptimized: true },
};

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(STATIC ? staticConfig : serverConfig),
};

export default nextConfig;
