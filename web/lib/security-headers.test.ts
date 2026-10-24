import { describe, expect, it, vi } from "vitest";

describe("web security headers (SR-11)", () => {
  it("sends a restrictive CSP in production builds", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.resetModules();
    const cfg = (await import("../next.config")).default;
    const rules = await cfg.headers!();
    const all = Object.fromEntries(rules[0].headers.map((h) => [h.key, h.value]));
    const csp = all["Content-Security-Policy"];
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'none'");
    expect(csp).not.toMatch(/https?:/);
    expect(all["X-Frame-Options"]).toBe("DENY");
    vi.unstubAllEnvs();
  });
});
