import type { NextConfig } from "next";

// The browser only talks to this Next.js server. API calls under /api/* are
// forwarded to the FastAPI service on the private network, so session cookies
// stay first-party and the API is never exposed directly.
const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
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
