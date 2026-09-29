import type { NextConfig } from "next";

// The frontend never talks to external data providers: every request goes to the ARGUS backend
// through this same-origin proxy (/api → FastAPI).
const API_URL = process.env.ARGUS_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: process.env.ARGUS_STANDALONE === "1" ? "standalone" : undefined,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  poweredByHeader: false,
};

export default nextConfig;
