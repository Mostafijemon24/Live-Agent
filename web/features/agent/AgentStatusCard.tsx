"use client";

import type { AgentStatus, ComponentStatus } from "@/lib/api/types";
import { DEMO_MODE } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Icon, MonoTag, cx } from "@/components/ui";

const BADGE: Record<ComponentStatus, { label: string; dot: string; fg: string; bg: string }> = {
  not_connected: { label: "Not connected", dot: "#98A2B3", fg: "#475467", bg: "#F2F4F7" },
  not_configured: { label: "No AI model configured", dot: "#98A2B3", fg: "#475467", bg: "#F2F4F7" },
  degraded: { label: "Degraded", dot: "#B54708", fg: "#B54708", bg: "#FFF6ED" },
  ok: { label: "Ready", dot: "#16803C", fg: "#16803C", bg: "#ECFDF3" },
};

const WORKER_LABEL: Record<string, string> = {
  orchestrator: "Planner & orchestrator",
  tools: "Tool runner",
  deletion: "Deletion service",
  scheduler: "Scheduler",
};

/** Agent status: model provider (and what it receives), worker liveness, queue depth. Renders only what the API says. */
export function AgentStatusCard({ agent, compact = false }: { agent?: AgentStatus; compact?: boolean }) {
  const status = agent?.status ?? "not_connected";
  const b = BADGE[status];
  const p = agent?.provider;
  const depth = Object.values(agent?.queue_depth ?? {}).reduce((a, n) => a + n, 0);
  return (
    <section aria-labelledby="agent-status-h" className="rounded-[10px] border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-start gap-4">
        <div className="grid h-10 w-10 flex-none place-items-center rounded-[10px] bg-neutral-soft text-ink-3">
          <Icon name="bot" size={20} />
        </div>
        <div className="min-w-0 flex-[1_1_300px]">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 id="agent-status-h" className="font-semibold">
              Agent status
            </h2>
            <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium" style={{ color: b.fg, background: b.bg }}>
              <span className="h-[7px] w-[7px] rounded-full" style={{ background: b.dot }} />
              {b.label}
            </span>
            {DEMO_MODE && <MonoTag>DEMO DATA</MonoTag>}
          </div>
          <p className="mt-0.5 text-[13.5px] text-muted [text-wrap:pretty]">{agent?.message ?? "Loading agent status…"}</p>
        </div>
      </div>
      {agent && !compact && (
        <div className="mt-4 grid gap-4 border-t border-line pt-4 md:grid-cols-2">
          <div>
            <div className="text-[12.5px] font-medium uppercase tracking-[.04em] text-muted">AI model</div>
            {p && p.configured ? (
              <>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[13.5px]">
                  <span className="font-medium">{p.label}</span>
                  {p.model && <span className="font-mono text-[12.5px] text-muted">{p.model}</span>}
                  <span
                    className={cx(
                      "rounded-md px-1.5 py-px text-xs font-medium",
                      p.location === "external" ? "bg-warning-soft text-warning" : "bg-success-soft text-success",
                    )}
                  >
                    {p.location === "external" ? "External service" : "Your own infrastructure"}
                  </span>
                </div>
                <p className="mt-1 text-[13px] text-muted [text-wrap:pretty]">{p.data_disclosure}</p>
              </>
            ) : (
              <p className="mt-1 text-[13px] text-muted [text-wrap:pretty]">
                {p?.data_disclosure ?? "No AI model is configured. Tasks wait and nothing is sent anywhere."} An administrator configures the model on the server — API keys are never entered in the browser.
              </p>
            )}
            {agent.policy_version && <p className="mt-1 font-mono text-[11.5px] text-muted">Policy version {agent.policy_version}</p>}
          </div>
          <div>
            <div className="text-[12.5px] font-medium uppercase tracking-[.04em] text-muted">Background workers</div>
            <ul className="mt-1 space-y-1">
              {(agent.workers ?? []).map((w) => (
                <li key={w.kind} className="flex items-center gap-2 text-[13px]">
                  <span className={cx("h-[7px] w-[7px] rounded-full", w.alive ? "bg-success" : "bg-line-strong")} aria-hidden />
                  <span>{WORKER_LABEL[w.kind] ?? w.kind}</span>
                  <span className="text-muted">
                    {w.alive ? "running" : w.last_heartbeat ? `not responding since ${fmtDateTime(w.last_heartbeat)}` : "not running"}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[12.5px] text-muted">
              {depth === 0 ? "No queued work for this workspace." : `${depth} job${depth === 1 ? "" : "s"} queued or running for this workspace.`}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
