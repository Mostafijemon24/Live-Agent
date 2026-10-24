"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, DEMO_MODE, type Artifact, type EventLevel, type Task } from "@/lib/api";
import {
  ACTIVITY_ICON,
  ACTIVITY_LABEL,
  APPROVAL_CATEGORY,
  APPROVAL_STATUS,
  MODE_LABEL,
  RISK_STEP,
  STEP_STATE,
  TASK_NEXT,
  TASK_TYPE_LABEL,
} from "@/lib/labels";
import { fmtDateTime, fmtTime, fmtTimeSec } from "@/lib/format";
import { useUi } from "@/lib/session";
import { Banner, Badge, ErrorState, Icon, Skeleton } from "@/components/ui";
import { integrationLabel, waitingLabel } from "./shared";

const card = "rounded-[10px] border border-line bg-surface";

/** Shown wherever a plan would be, while the Phase 3 planner is not installed. */
export function PlannerBanner() {
  return (
    <Banner tone="info" icon="hourglass" title="Waiting for the planning service">
      The AI planner isn&apos;t installed yet (Phase 3). This task is saved and queued; nothing has run.
    </Banner>
  );
}

function stepCounts(task: Task) {
  const steps = task.plan?.steps ?? [];
  return { done: steps.filter((s) => s.state === "done").length, total: steps.length };
}

function Field({ label, children, mb }: { label: string; children: ReactNode; mb?: boolean }) {
  return (
    <div>
      <div className={mb ? "mb-1.5 text-[12.5px] text-muted" : "text-[12.5px] text-muted"}>{label}</div>
      {children}
    </div>
  );
}

// ------------------------------------------------------------------ Summary
export function SummaryTab({ task, onAnswer, onCopyError }: { task: Task; onAnswer?: () => void; onCopyError: () => void }) {
  const { done, total } = stepCounts(task);
  const waiting = waitingLabel(task.waiting_for);
  const meta: [string, ReactNode][] = [
    ["Progress", task.plan ? `${done} of ${total} steps done` : "No plan yet"],
    ["Mode", MODE_LABEL[task.mode]],
    ["Priority", task.priority === "high" ? "High" : "Normal"],
    ["Type", TASK_TYPE_LABEL[task.type]],
    ["Integration", integrationLabel(task.integration_key)],
    ["Created", fmtDateTime(task.created_at)],
    ["Updated", fmtDateTime(task.updated_at)],
    ["Next action", waiting ?? TASK_NEXT[task.status]],
  ];
  return (
    <div className="flex flex-wrap items-start gap-4">
      <div className="flex min-w-0 flex-[2_1_480px] flex-col gap-4">
        {task.waiting_for === "planning_service" && <PlannerBanner />}
        {task.error_message && (
          <div role="alert" className="flex items-start gap-3 rounded-[10px] border border-danger-line bg-danger-soft p-4">
            <Icon name="circle-x" size={18} className="mt-px text-danger" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-danger">What went wrong</div>
              <div className="mt-1 text-ink-2 [text-wrap:pretty]">{task.error_message}</div>
              <button
                type="button"
                onClick={onCopyError}
                className="mt-2.5 inline-flex h-8 items-center gap-1.5 rounded-[7px] border border-danger-line bg-surface px-2.5 text-[13px] font-medium hover:bg-subtle"
              >
                <Icon name="copy" size={14} />
                Copy error details
              </button>
            </div>
          </div>
        )}
        {task.question && (
          <div className="flex items-start gap-3 rounded-[10px] border border-warning-line bg-warning-soft p-4">
            <Icon name="message-circle" size={18} className="mt-px text-warning" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-warning">The Agent needs your input</div>
              <div className="mt-1 text-ink-2">{task.question}</div>
              {onAnswer && (
                <button
                  type="button"
                  onClick={onAnswer}
                  className="mt-2.5 h-8 rounded-[7px] border-0 bg-primary px-3 text-[13px] font-medium text-white hover:bg-primary-hover"
                >
                  Answer
                </button>
              )}
            </div>
          </div>
        )}
        <section className={`${card} px-5 py-[18px]`}>
          <h2 className="mb-2 text-[15px] font-semibold">Request</h2>
          <p className="whitespace-pre-wrap text-ink-2 [text-wrap:pretty]">{task.prompt}</p>
        </section>
        {task.report && (
          <section className={`${card} flex flex-col gap-3 px-5 py-[18px]`}>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-semibold">Result</h2>
              <span className="rounded-[5px] bg-warning-soft px-[7px] py-px text-[11.5px] font-medium text-warning">
                AI-generated summary{DEMO_MODE ? " · sample" : ""}
              </span>
            </div>
            <Field label="Outcome">
              <div>{task.report.summary || "—"}</div>
            </Field>
            <Field label="Unresolved">
              <div>{task.report.open_issues || "—"}</div>
            </Field>
            <Field label="Suggested next step">
              <div>{task.report.next_step || "—"}</div>
            </Field>
          </section>
        )}
      </div>
      <section aria-label="Task details" className={`${card} grid min-w-0 flex-[1_1_280px] grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 px-5 py-[18px] text-[13.5px]`}>
        {meta.map(([k, v]) => (
          <div key={k} className="contents">
            <span className="text-muted">{k}</span>
            <span className="min-w-0">{v}</span>
          </div>
        ))}
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ Plan
export function PlanTab({ task }: { task: Task }) {
  if (!task.plan) {
    return task.waiting_for === "planning_service" || !DEMO_MODE ? (
      <PlannerBanner />
    ) : (
      <section className={`${card} px-5 py-8 text-center text-muted`}>No plan has been prepared for this task yet.</section>
    );
  }
  const { done, total } = stepCounts(task);
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <section className={card}>
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3.5">
        <h2 className="flex-1 text-[15px] font-semibold">Plan &amp; steps</h2>
        <div
          role="progressbar"
          aria-label="Steps done"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          className="h-1.5 w-40 overflow-hidden rounded-[3px] bg-track"
        >
          <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-[12.5px] text-muted">
          {done} of {total} steps done
        </span>
      </div>
      {total === 0 ? (
        <div className="px-5 py-8 text-center text-muted">This plan has no steps.</div>
      ) : (
        <ol className="m-0 list-none px-5 pb-3 pt-2">
          {task.plan.steps.map((st) => {
            const sm = STEP_STATE[st.state];
            const risk = RISK_STEP[st.risk];
            const time = st.finished_at ? `Finished ${fmtTime(st.finished_at)}` : st.started_at ? `Started ${fmtTime(st.started_at)}` : "—";
            return (
              <li key={st.id} className="flex gap-3.5 border-b border-line-soft py-3 last:border-b-0">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full" style={{ background: sm.bg, color: sm.fg }}>
                  <Icon name={sm.icon} size={14} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted">{String(st.position).padStart(2, "0")}</span>
                    <span className="font-medium">{st.title}</span>
                    <span className="text-xs font-medium" style={{ color: sm.fg }}>
                      {sm.label}
                    </span>
                    <span className="rounded-md px-2 py-px text-xs font-medium" style={{ color: risk.fg, background: risk.bg }}>
                      {risk.label}
                    </span>
                    {st.requires_approval && (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-warning">
                        <Icon name="shield-alert" size={13} />
                        Separate approval at run time
                      </span>
                    )}
                    {!st.selected && <span className="text-xs text-muted">Not selected</span>}
                  </div>
                  <div className="mt-0.5 text-[12.5px] text-muted">
                    {st.tool} · {time}
                  </div>
                  {st.description && <div className="mt-0.5 text-[12.5px] text-muted [text-wrap:pretty]">{st.description}</div>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Inputs
export function InputsTab({ task }: { task: Task }) {
  const sources = task.plan?.data_sources ?? [];
  return (
    <section className={`${card} flex flex-col gap-3.5 px-5 py-[18px]`}>
      <Field label="Prompt">
        <div className="whitespace-pre-wrap [text-wrap:pretty]">{task.prompt}</div>
      </Field>
      <Field label="Attachments" mb>
        {task.attachments.length ? (
          <ul className="m-0 list-none p-0">
            {task.attachments.map((a) => (
              <li key={a.file_id} className="flex items-center gap-2 py-1.5">
                <Icon name="paperclip" size={14} className="text-muted" />
                <Link href={`/files?q=${encodeURIComponent(a.name)}`}>{a.name}</Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-muted">No files attached.</div>
        )}
      </Field>
      <Field label="Data the plan reads" mb>
        {task.plan ? (
          sources.length || task.attachments.length ? (
            <ul className="m-0 list-none p-0">
              {sources.map((s) => (
                <li key={s} className="py-0.5">
                  {s}
                </li>
              ))}
              {task.attachments.map((a) => (
                <li key={a.file_id} className="py-0.5">
                  Attached: {a.name}
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-muted">This plan doesn&apos;t read any data.</div>
          )
        ) : (
          <div className="text-muted">Listed here once a plan is prepared.</div>
        )}
      </Field>
      {task.plan?.destination && (
        <Field label="External destination" mb>
          <div className="flex gap-2 text-[13.5px]">
            <Icon name="send" size={14} className="mt-[3px] text-warning" />
            {task.plan.destination}
          </div>
        </Field>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Approvals
export function ApprovalsTab({ task }: { task: Task }) {
  const q = useQuery({ queryKey: ["approvals", "all"], queryFn: () => api.listApprovals("all") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  const items = (q.data?.items ?? []).filter((a) => a.task_id === task.id);
  return (
    <section className={card}>
      {items.length === 0 ? (
        <div className="px-5 py-8 text-center text-muted">No approval requests for this task yet.</div>
      ) : (
        items.map((a) => (
          <div key={a.id} className="flex flex-wrap items-center gap-3 border-b border-line-soft px-5 py-3.5 last:border-b-0">
            <div className="min-w-0 flex-[1_1_240px]">
              <div className="font-medium">{a.title}</div>
              <div className="text-[12.5px] text-muted">
                <span className="font-mono">{a.ref}</span> · {APPROVAL_CATEGORY[a.category].label} ·{" "}
                {a.decided_at ? `Decided ${fmtDateTime(a.decided_at)}` : `Requested ${fmtDateTime(a.requested_at)}`}
              </div>
            </div>
            <Badge meta={APPROVAL_STATUS[a.status]} />
            <Link href={`/approvals?id=${a.id}&filter=${a.status === "pending" ? "pending" : "decided"}`} className="text-[13.5px] font-medium">
              Open
            </Link>
          </div>
        ))
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Run logs
const LEVEL_COLOR: Record<EventLevel, string> = { error: "#B42318", warn: "#B54708", note: "#3448C5", info: "#667085" };

export function LogsTab({ task, onCopy }: { task: Task; onCopy: () => void }) {
  const q = useQuery({ queryKey: ["task-events", task.id], queryFn: () => api.listTaskEvents(task.id) });
  return (
    <section className={`${card} overflow-hidden`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <span className="text-[13px] text-muted">Times in your local time · tokens and passwords are redacted</span>
        <button
          type="button"
          onClick={onCopy}
          className="inline-flex h-[30px] items-center gap-1.5 rounded-[7px] border border-line-strong bg-surface px-2.5 text-[12.5px] font-medium hover:bg-subtle"
        >
          <Icon name="copy" size={13} />
          Copy details
        </button>
      </div>
      {q.isLoading ? (
        <Loading bare />
      ) : q.error ? (
        <div className="p-4">
          <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} title="We couldn't load the run log" />
        </div>
      ) : !q.data?.items.length ? (
        <div className="px-5 py-8 text-center text-muted">No log entries yet.</div>
      ) : (
        <div className="overflow-x-auto py-2.5 font-mono text-[12.5px]">
          {q.data.items.map((e) => (
            <div key={e.id} className="flex gap-3.5 whitespace-nowrap px-4 py-[3px]">
              <time dateTime={e.created_at} title={fmtDateTime(e.created_at)} className="text-faint">
                {fmtTimeSec(e.created_at)}
              </time>
              <span className="w-11 shrink-0" style={{ color: LEVEL_COLOR[e.level] }}>
                {e.level.toUpperCase()}
              </span>
              <span className="whitespace-normal text-ink-2">{e.message}</span>
            </div>
          ))}
          {q.data.total > q.data.items.length && (
            <div className="px-4 pt-2 font-sans text-[12.5px] text-muted">
              Showing the latest {q.data.items.length} of {q.data.total} entries.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Outputs
const PROVENANCE: Record<Artifact["provenance"], { label: string; fg: string; bg: string }> = {
  ai_generated: { label: "AI-generated summary", fg: "#B54708", bg: "#FFF6ED" },
  verified_result: { label: "Verified execution result", fg: "#16803C", bg: "#ECFDF3" },
};

export function OutputsTab({ task }: { task: Task }) {
  const { notice } = useUi();
  const q = useQuery({ queryKey: ["reports"], queryFn: () => api.listReports() });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  const arts = (q.data?.artifacts ?? []).filter((a) => a.task_id === task.id);
  const download = () =>
    notice(
      "Downloads arrive with the execution engine",
      DEMO_MODE
        ? "Artifacts are stored in private storage and served through short-lived signed links once the backend exists. This sample file has no content."
        : "Outputs are kept in private storage and served through short-lived signed links. Artifact storage arrives with the execution engine (Phase 3), so there is no file to download yet.",
    );
  return (
    <section className={card}>
      {arts.length === 0 ? (
        <div className="px-5 py-9 text-center text-muted">
          <Icon name="inbox" size={22} className="mx-auto mb-1.5 block" />
          No outputs yet. Reports and files appear here when steps finish.
        </div>
      ) : (
        arts.map((a) => {
          const p = PROVENANCE[a.provenance];
          return (
            <div key={a.id} className="flex flex-wrap items-center gap-3 border-b border-line-soft px-5 py-3.5 last:border-b-0">
              <Icon name="file-text" size={18} className="text-muted" />
              <div className="min-w-0 flex-[1_1_200px]">
                <div className="font-medium">{a.name}</div>
                <div className="text-[12.5px] text-muted">{a.kind}</div>
              </div>
              <span className="rounded-md px-2 py-0.5 text-xs font-medium" style={{ color: p.fg, background: p.bg }}>
                {p.label}
              </span>
              <button
                type="button"
                onClick={download}
                aria-label={`Download ${a.name}`}
                className="grid h-8 w-8 place-items-center rounded-[7px] border border-line-strong bg-surface hover:bg-subtle"
              >
                <Icon name="download" size={14} />
              </button>
            </div>
          );
        })
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Audit
export function AuditTab({ task }: { task: Task }) {
  const q = useQuery({ queryKey: ["activity", undefined], queryFn: () => api.listActivity() });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  const items = (q.data?.items ?? []).filter((a) => a.task_id === task.id);
  return (
    <section className={`${card} px-5 py-2`}>
      {items.length === 0 ? (
        <div className="py-7 text-center text-muted">No audit events recorded for this task.</div>
      ) : (
        items.map((a) => (
          <div key={a.id} className="flex gap-3 border-b border-line-soft py-2.5 last:border-b-0">
            <Icon name={ACTIVITY_ICON[a.type] ?? "activity"} size={15} className="mt-[3px] text-muted" />
            <div className="min-w-0">
              <div>{a.message}</div>
              <div className="text-xs text-muted">
                {fmtDateTime(a.created_at)} · {ACTIVITY_LABEL[a.type] ?? a.type}
                {a.actor ? ` · ${a.actor}` : ""}
              </div>
            </div>
          </div>
        ))
      )}
    </section>
  );
}

function Loading({ bare }: { bare?: boolean }) {
  return bare ? <Skeleton className="p-5" /> : <Skeleton className={`${card} p-5`} />;
}
