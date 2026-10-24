import type { NextConfig } from "next";

// The browser only talks to this Next.js server. API calls under /api/* are
// forwarded to the FastAPI service on the private network, so session cookies
// stay first-party and the API is never exposed directly.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

// Content-Security-Policy (production builds only; `next dev` needs eval for hot reload).
// 'unsafe-inline' for scripts is required by Next.js without per-request nonces; everything
// else is locked to this origin: no external scripts, plugins, framing or <base> hijacking.
export const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
].join("; ");

const securityHeaders = [
  ...(process.env.NODE_ENV === "production" ? [{ key: "Content-Security-Policy", value: CSP }] : []),
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // The /api rewrite buffers request bodies and silently truncates them at 10 MB by default, which
  // broke uploads above 10 MB (API limit 25 MB). Match the Caddy cap; the API enforces its own limits.
  experimental: { proxyClientMaxBodySize: "30mb" },
  // Always defined so it is inlined at build time; "false" lets the bundler drop
  // the demo adapter and its sample data from production builds entirely.
  env: { NEXT_PUBLIC_DEMO_MODE: process.env.NEXT_PUBLIC_DEMO_MODE === "true" ? "true" : "false" },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
