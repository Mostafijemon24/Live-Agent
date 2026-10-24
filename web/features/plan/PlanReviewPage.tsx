"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, DEMO_MODE, isApiError } from "@/lib/api";
import type { Task, TaskPlan } from "@/lib/api/types";
import { fmtDateTime } from "@/lib/format";
import { MODE_LABEL, RISK_STEP, TASK_STATUS, TASK_TYPE_LABEL } from "@/lib/labels";
import { Button, DefList, ErrorState, Icon, Skeleton, cx } from "@/components/ui";
import { PlanModal, type PlanModalKind } from "./PlanModals";
import { StepPolicy } from "./StepPolicy";

const card = "rounded-[10px] border border-line bg-surface";
const pad2 = (n: number) => String(n).padStart(2, "0");

export function PlanReviewPage() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery({
    queryKey: ["task", id],
    queryFn: () => api.getTask(id),
    refetchInterval: (query) => (query.state.data?.status === "planning" ? 2000 : false),
  });

  const back = (
    <Link href="/tasks" className="inline-flex items-center gap-1.5 self-start text-[13.5px] text-ink-3 hover:text-ink-3">
      <Icon name="arrow-left" size={15} />
      Tasks
    </Link>
  );

  if (q.isLoading) {
    return (
      <div className="flex flex-col gap-5">
        {back}
        <div className={cx(card, "p-6")}>
          <Skeleton />
        </div>
      </div>
    );
  }
  if (q.error && isApiError(q.error) && (q.error.status === 404 || q.error.status === 403)) {
    return (
      <div className="flex flex-col gap-5">
        {back}
        <NotFound />
      </div>
    );
  }
  if (q.error || !q.data) {
    return (
      <div className="flex flex-col gap-5">
        {back}
        <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
      </div>
    );
  }

  const t = q.data;
  const s = TASK_STATUS[t.status];
  return (
    <div className="flex flex-col gap-5">
      {back}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-[1_1_400px]">
          <div className="font-mono text-[12.5px] text-muted">{t.ref} · Plan review</div>
          <h1 className="mt-0.5 text-2xl font-semibold tracking-[-.015em] [text-wrap:balance]">{t.title}</h1>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium" style={{ color: s.fg, background: s.bg }}>
          <Icon name={s.icon} size={14} spin={t.status === "planning"} />
          {s.label}
        </span>
      </div>
      <PlanBody task={t} />
    </div>
  );
}

function PlanBody({ task: t }: { task: Task }) {
  if (t.status === "planning") return <Planning />;
  if (t.status === "awaiting_approval" && t.plan) return <Review key={t.id} task={t} plan={t.plan} />;
  if (!t.plan && (t.waiting_for === "planning_service" || t.waiting_for === "approval")) return <WaitingForPlanner task={t} />;
  return (
    <div className={cx(card, "flex flex-wrap items-center gap-3 px-4 py-3")}>
      <Icon name="info" size={17} className="text-primary" />
      <span className="flex-1">
        {t.plan ? "This plan has already been decided." : "There is no plan to review for this task."} The task is now <strong>{TASK_STATUS[t.status].label}</strong>.
      </span>
      <LinkButton href={`/tasks/${t.id}`}>Open task details</LinkButton>
    </div>
  );
}

function LinkButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex h-[34px] items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-[13.5px] font-medium text-ink hover:bg-subtle hover:text-ink hover:no-underline"
    >
      {children}
    </Link>
  );
}

function NotFound() {
  return (
    <div role="alert" className={cx(card, "flex flex-col items-start gap-2 p-[18px]")}>
      <div className="font-mono text-xs text-muted">NOT FOUND</div>
      <Icon name="lock" size={20} className="text-warning" />
      <div className="font-semibold">We can&apos;t show this task</div>
      <div className="text-[13.5px] text-muted">It doesn&apos;t exist, or it belongs to a workspace you don&apos;t have access to. Ask a workspace admin if you think this is a mistake.</div>
      <div className="flex flex-wrap gap-2">
        <LinkButton href="/tasks">Back to tasks</LinkButton>
        <LinkButton href="/overview">Back to overview</LinkButton>
      </div>
    </div>
  );
}

function Planning() {
  return (
    <div aria-busy="true" className={cx(card, "flex flex-col gap-3.5 p-6")}>
      <div className="flex items-center gap-2.5 font-medium">
        <Icon name="loader" size={17} spin className="text-primary" />
        Preparing a plan…{DEMO_MODE ? " (simulated)" : ""}
      </div>
      {["60%", "85%", "72%", "40%"].map((w) => (
        <div key={w} className="h-3 animate-pulse-soft rounded bg-track" style={{ width: w }} />
      ))}
    </div>
  );
}

function Goal({ prompt, children }: { prompt: string; children?: ReactNode }) {
  return (
    <section className={cx(card, "px-5 py-[18px]")}>
      <h2 className="mb-2 text-[15px] font-semibold">Goal and interpretation</h2>
      <p className="text-ink-2 [text-wrap:pretty]">“{prompt}”</p>
      {children}
    </section>
  );
}

function WaitingForPlanner({ task: t }: { task: Task }) {
  const [modal, setModal] = useState<PlanModalKind | null>(null);
  const canCancel = t.allowed_actions.includes("cancel");
  return (
    <div className="flex flex-wrap items-start gap-4">
      <div className="flex min-w-0 flex-[2_1_520px] flex-col gap-4">
        <Goal prompt={t.prompt} />
        <section role="status" className={cx(card, "flex gap-3 px-5 py-[18px]")}>
          <span className="grid h-10 w-10 flex-none place-items-center rounded-[10px] bg-warning-soft text-warning">
            <Icon name="server" size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[15px] font-semibold">{t.waiting_for === "approval" ? "Waiting for your approval to plan" : "Waiting to be planned"}</h2>
            <p className="mt-1 text-[13.5px] text-ink-3 [text-wrap:pretty]">
              {t.waiting_for === "approval"
                ? "The configured AI model is an external service, so sending the task text to it needs a one-time approval. Nothing has been sent yet."
                : "Your task is queued for the planner. If no AI model is configured, it waits here and nothing is sent anywhere. Nothing has run."}
            </p>
            {t.waiting_for === "approval" && (
              <Link href="/approvals" className="mt-2 inline-block text-[13.5px] font-medium">
                Review the approval request
              </Link>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <LinkButton href={`/tasks/${t.id}`}>View task</LinkButton>
              {canCancel && (
                <Button size="sm" variant="danger" onClick={() => setModal("cancelTask")}>
                  Cancel task
                </Button>
              )}
            </div>
          </div>
        </section>
      </div>
      <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
        <section className={cx(card, "px-5 py-[18px]")}>
          <h2 className="mb-3 text-[15px] font-semibold">Task summary</h2>
          <DefList
            items={[
              ["Type", TASK_TYPE_LABEL[t.type]],
              ["Priority", t.priority === "high" ? "High" : "Normal"],
              ["Mode", MODE_LABEL[t.mode]],
              ["Created", fmtDateTime(t.created_at)],
              ["Attachments", t.attachments.length ? t.attachments.map((a) => a.name).join(", ") : "None"],
            ]}
          />
        </section>
      </div>
      {modal && <PlanModal kind={modal} task={t} selectedIds={[]} total={0} onClose={() => setModal(null)} />}
    </div>
  );
}

function Review({ task: t, plan }: { task: Task; plan: TaskPlan }) {
  const steps = [...plan.steps].sort((a, b) => a.position - b.position);
  const isBlocked = (st: (typeof steps)[number]) => st.state === "blocked" || st.policy?.outcome === "deny";
  const [sel, setSel] = useState<Record<string, boolean>>(() => Object.fromEntries(steps.map((s) => [s.id, s.selected && !isBlocked(s)])));
  const blocked = steps.filter(isBlocked);
  const [modal, setModal] = useState<PlanModalKind | null>(null);
  const selectedIds = steps.filter((s) => sel[s.id]).map((s) => s.id);
  const tools = [...new Set(steps.map((s) => s.tool))];
  const irrev = steps.filter((s) => s.requires_approval && !isBlocked(s));
  const dests = [...new Set(steps.filter((s) => !isBlocked(s)).flatMap((s) => s.destinations ?? []))];
  const sources = [...plan.data_sources, ...t.attachments.map((a) => `Attached: ${a.name}`)];
  const can = (a: Task["allowed_actions"][number]) => t.allowed_actions.includes(a);
  const canApprove = can("approve_plan");
  const canRevise = can("revise_plan");
  const canReject = can("reject_plan");
  // Questions are allowed whenever the plan is open for review (no dedicated action in the state machine).
  const canAsk = canApprove || canRevise || canReject;

  return (
    <div className="flex flex-wrap items-start gap-4">
      <div className="flex min-w-0 flex-[2_1_520px] flex-col gap-4">
        <Goal prompt={t.prompt}>
          {plan.summary && <p className="mt-2 text-[13.5px] text-ink-2 [text-wrap:pretty]">{plan.summary}</p>}
          <p className="mt-2.5 text-[13.5px] text-muted [text-wrap:pretty]">
            Every step below was checked by the policy engine. Steps marked “Needs approval” ask again, one by one, right before they run.
            The AI model only proposed the steps; permissions and approvals are decided by the server.
          </p>
          {plan.provider && (
            <p className="mt-1.5 text-[12.5px] text-muted">
              Planned by {plan.provider}
              {plan.provider_location ? ` (${plan.provider_location === "external" ? "external service" : "your own infrastructure"})` : ""}
              {plan.version && plan.version > 1 ? ` · plan version ${plan.version}` : ""}
            </p>
          )}
        </Goal>
        {blocked.length > 0 && (
          <div role="note" className="flex items-start gap-2.5 rounded-[10px] border border-danger-line bg-danger-soft px-4 py-3 text-[13.5px]">
            <Icon name="shield-ban" size={17} className="mt-px text-danger" />
            <span className="[text-wrap:pretty]">
              {blocked.length === 1 ? "1 step is" : `${blocked.length} steps are`} blocked by policy and can&apos;t be selected. Adjust Settings (allowed domains, tool permissions) and request a new plan if you need them.
            </span>
          </div>
        )}
        <section className={card}>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <h2 className="text-[15px] font-semibold">Step-by-step plan</h2>
            <span className="text-[13px] text-muted">
              {selectedIds.length} of {steps.length} steps selected
            </span>
          </div>
          {steps.map((st) => {
            const r = RISK_STEP[st.risk];
            const n = pad2(st.position);
            const off = isBlocked(st);
            return (
              <label
                key={st.id}
                className={cx("flex items-start gap-3.5 border-b border-line-soft px-5 py-3.5 last:border-b-0", off ? "cursor-not-allowed bg-subtle" : "cursor-pointer")}
              >
                <input
                  type="checkbox"
                  checked={!!sel[st.id] && !off}
                  disabled={!canApprove || off}
                  onChange={(e) => setSel((s) => ({ ...s, [st.id]: e.target.checked }))}
                  aria-label={`Include step ${n}`}
                  className="mt-[3px] h-4 w-4 flex-none accent-primary"
                />
                <span className="mt-0.5 flex-none font-mono text-[12.5px] text-muted">{n}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{st.title}</span>
                    <span className="rounded-md px-2 py-px text-xs font-medium" style={{ color: r.fg, background: r.bg }}>
                      {r.label}
                    </span>
                    {st.requires_approval && !off && !st.policy && (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-warning">
                        <Icon name="shield-alert" size={13} />
                        One-time approval when it runs
                      </span>
                    )}
                  </span>
                  <span className="mt-[3px] block text-[13px] text-muted">
                    {st.tool}
                    {st.description ? ` · ${st.description}` : ""}
                  </span>
                  <StepPolicy step={st} />
                </span>
              </label>
            );
          })}
        </section>
      </div>

      <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
        <section className={cx(card, "flex flex-col gap-3.5 px-5 py-[18px]")}>
          <div>
            <div className="mb-1.5 text-[12.5px] text-muted">Tools and integrations</div>
            <div className="flex flex-wrap gap-1.5">
              {tools.map((x) => (
                <span key={x} className="rounded-md border border-line px-2 py-0.5 text-[12.5px]">
                  {x}
                </span>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[12.5px] text-muted">Files and data accessed</div>
            {sources.length === 0 ? (
              <div className="text-[13.5px] text-ink-3">None</div>
            ) : (
              sources.map((f) => (
                <div key={f} className="flex gap-2 py-0.5 text-[13.5px]">
                  <Icon name="file" size={14} className="mt-[3px] text-muted" />
                  {f}
                </div>
              ))
            )}
          </div>
          <div>
            <div className="mb-1.5 text-[12.5px] text-muted">External destinations</div>
            <div className="flex gap-2 text-[13.5px]">
              <Icon name="send" size={14} className="mt-[3px] text-warning" />
              {dests.length ? dests.join(", ") : (plan.destination ?? "None — everything stays in this workspace")}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[12.5px] text-muted">Irreversible or high-impact steps</div>
            {irrev.length === 0 ? (
              <div className="text-[13.5px] text-ink-3">None</div>
            ) : (
              irrev.map((r) => (
                <div key={r.id} className="flex gap-2 text-[13.5px]">
                  <Icon name="triangle-alert" size={14} className="mt-[3px] text-warning" />
                  {r.title} ({RISK_STEP[r.risk].label})
                </div>
              ))
            )}
          </div>
          <div>
            <div className="mb-1 text-[12.5px] text-muted">Estimated usage and cost</div>
            <div className="text-[13.5px] text-ink-3">Model usage is recorded per call and counted against the workspace allowance (Settings → Usage). Cost estimates are not shown.</div>
          </div>
        </section>

        {canAsk && (
          <div className={cx(card, "flex flex-col gap-2 p-4")}>
            {canApprove && (
              <Button variant="primary" icon="check" onClick={() => setModal("approvePlan")} disabled={selectedIds.length === 0} className="h-10">
                Approve selected steps
              </Button>
            )}
            {canApprove && selectedIds.length === 0 && <p className="text-xs text-danger">Select at least one step to approve.</p>}
            <div className="grid grid-cols-2 gap-2">
              {canRevise && (
                <Button size="sm" onClick={() => setModal("editPlan")} className="h-9">
                  Edit plan
                </Button>
              )}
              <Button size="sm" onClick={() => setModal("ask")} className={cx("h-9", !canRevise && "col-span-2")}>
                Ask a question
              </Button>
            </div>
            {canReject && (
              <Button size="sm" variant="danger" onClick={() => setModal("rejectPlan")} className="h-9">
                Reject plan
              </Button>
            )}
            <p className="mt-1 text-xs text-muted [text-wrap:pretty]">
              {DEMO_MODE
                ? "Demo: approving only changes the status here. Approval will be enforced by the server later."
                : "Approving queues the selected steps. Each is checked again right before it runs, and steps that need approval will ask you first."}
            </p>
          </div>
        )}
      </div>
      {modal && <PlanModal kind={modal} task={t} selectedIds={selectedIds} total={steps.length} onClose={() => setModal(null)} />}
    </div>
  );
}
