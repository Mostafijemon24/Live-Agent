import type { AgentApi } from "./client";
import { HttpAgentApi } from "./http";
import { MockAgentApi } from "./mock";

/**
 * Demo mode is opt-in and isolated: it is only used when the build sets
 * NEXT_PUBLIC_DEMO_MODE=true. Production deployments leave it unset, so every
 * call goes to the real backend and real failures are shown as failures.
 */
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

let instance: AgentApi | null = null;
export function getApi(): AgentApi {
  if (!instance) instance = DEMO_MODE ? new MockAgentApi() : new HttpAgentApi();
  return instance;
}

export const api: AgentApi = new Proxy({} as AgentApi, {
  get(_t, prop) {
    const target = getApi() as unknown as Record<string | symbol, unknown>;
    const v = target[prop];
    return typeof v === "function" ? (v as (...a: unknown[]) => unknown).bind(target) : v;
  },
});

export * from "./client";
export type * from "./types";
