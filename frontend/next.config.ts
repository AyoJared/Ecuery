import type { NextConfig } from "next";

// The FastAPI backend (backend/main.py). The browser talks to it through /api/ecuery/*, which
// Next proxies, so the backend needs no CORS setup and the frontend never hardcodes its address.
const ECUERY_API_URL = process.env.ECUERY_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/ecuery/:path*", destination: `${ECUERY_API_URL}/:path*` }];
  },
  experimental: {
    // An answer can take a while: Gemini twice, both databases, and up to ~30 s of Solana confirmation.
    proxyTimeout: 120_000,
  },
};

export default nextConfig;
