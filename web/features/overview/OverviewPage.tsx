"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError } from "@/lib/api";
import type { ComponentStatus, Dashboard } from "@/lib/api/types";
import { useSession, useUi } from "@/lib/session";
import { fmtDateTime, guessType, newIdempotencyKey, suggestTitle } from "@/lib/format";
import { ACTIVITY_ICON, APPROVAL_CATEGORY, RISK_LEVEL, TASK_NEXT, TASK_STATUS } from "@/lib/labels";
import { Badge, Button, CardHeader, EmptyState, ErrorState, Icon, MonoTag, PageHeader, Skeleton, TextArea, cx } from "@/components/ui";
import { WORDPRESS_EXAMPLE, taskHref } from "./taskRoutes";

const EXAMPLES = [
  "Audit my WordPress site for SEO problems and show fixes before changing anything",
  "Summarise the attached CSV and list the top 5 issues",
  "Draft a content brief for a local services page",
];
const QUICK_MIN_MSG = "Describe the task in a sentence or two so the Agent can plan it.";

const AGENT_BADGE: Record<ComponentStatus, { label: string; dot: string; fg: string; bg: string }> = {
  not_connected: { label: "Not connected", dot: "#98A2B3", fg: "#475467", bg: "#F2F4F7" },
  not_configured: { label: "Not connected", dot: "#98A2B3", fg: "#475467", bg: "#F2F4F7" },
  degraded: { label: "Degraded", dot: "#B54708", fg: "#B54708", bg: "#FFF6ED" },
  ok: { label: "Connected", dot: "#16803C", fg: "#16803C", bg: "#ECFDF3" },
};

const AGENT_INFO_TITLE = "Connecting the Agent";
const AGENT_INFO_BODY = DEMO_MODE
  ? "To run real tasks, Phase 3 installs: an AI orchestration service, background workers, a job queue and a policy engine that enforces approvals. Until then, every result here is sample data."
  : "To run real tasks, Phase 3 installs: an AI orchestration service, background workers, a job queue and a policy engine that enforces approvals. Until then, your tasks are saved securely and queued, but nothing is planned or executed.";

const card = "rounded-[10px] border border-line bg-surface";
const headLink = "text-[13.5px] font-medium text-primary";

export function OverviewPage() {
  const { me } = useSession();
  const { notice } = useUi();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api.dashboard(), staleTime: 15_000 });
  const d = q.data;

  const subtitle = d
    ? `${me?.workspace.name ?? "Workspace"} · ${d.counts.in_progress} in progress · ${d.counts.pending_actions} actions waiting for you`
    : (me?.workspace.name ?? "Workspace");

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Your workspace"
        subtitle={subtitle}
        actions={
          <>
            <Button
              icon="file-up"
              onClick={() =>
                notice(
                  "Importing needs the backend",
                  "Task lists from CSV, Excel or Notion will be parsed and validated on the server once the import service is installed (Phase 3). For now, create tasks one at a time.",
                )
              }
            >
              Import task list
            </Button>
            <Link
              href="/tasks/new"
              className="inline-flex h-[38px] items-center gap-2 rounded-lg bg-primary px-3.5 text-sm font-medium text-white hover:bg-primary-hover hover:text-white hover:no-underline"
            >
              <Icon name="plus" size={16} />
              Create task
            </Link>
          </>
        }
      />

      <AgentStatus status={d?.agent.status} onInfo={() => notice(AGENT_INFO_TITLE, AGENT_INFO_BODY)} />

      {q.isLoading ? (
        <div className={cx(card, "p-5")}>
          <Skeleton />
        </div>
      ) : q.error || !d ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
      ) : (
        <>
          <Kpis d={d} />
          <div className="flex flex-wrap items-start gap-4">
            <div className="flex min-w-0 flex-[2_1_520px] flex-col gap-4">
              <QuickTask />
              <RecentTasks d={d} />
            </div>
            <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-4">
              <PendingApprovals d={d} />
              <SetupChecklist d={d} />
              <ActivityCard d={d} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function AgentStatus({ status, onInfo }: { status?: ComponentStatus; onInfo: () => void }) {
  const b = AGENT_BADGE[status ?? "not_connected"];
  const connected = status === "ok";
  const text = connected
    ? "The AI engine is connected."
    : DEMO_MODE
      ? "A demo agent simulates plans and results with sample data. It cannot open any website, file or service until the backend is connected."
      : "The AI engine is not installed yet (Phase 3). Your tasks are saved and queued, but no plan is prepared and nothing runs until it is connected.";
  return (
    <div className={cx(card, "flex flex-wrap items-center gap-4 px-5 py-4")}>
      <div className="grid h-10 w-10 flex-none place-items-center rounded-[10px] bg-neutral-soft text-ink-3">
        <Icon name="bot" size={20} />
      </div>
      <div className="min-w-0 flex-[1_1_300px]">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="font-semibold">Agent status</span>
          <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium" style={{ color: b.fg, background: b.bg }}>
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: b.dot }} />
            {b.label}
          </span>
        </div>
        <div className="mt-0.5 text-[13.5px] text-muted [text-wrap:pretty]">{text}</div>
      </div>
      {!connected && (
        <Button size="sm" onClick={onInfo}>
          What&apos;s needed to connect?
        </Button>
      )}
    </div>
  );
}

function Kpis({ d }: { d: Dashboard }) {
  const c = d.counts;
  const kpis = [
    { label: "Tasks in progress", value: c.in_progress, hint: "Queued, planning or running", icon: "play", color: "#175CD3", href: "/tasks?status=running" },
    {
      label: "Awaiting approval",
      value: c.pending_actions + c.awaiting_approval_plans,
      hint: `${c.pending_actions} actions · ${c.awaiting_approval_plans} plans`,
      icon: "hourglass",
      color: "#B54708",
      href: "/approvals",
    },
    { label: "Completed this week", value: c.completed_week, hint: "Fully completed tasks only", icon: "circle-check", color: "#16803C", href: "/tasks?status=completed" },
    { label: "Needs attention", value: c.needs_attention, hint: "Failed, paused or waiting for you", icon: "circle-alert", color: "#B42318", href: "/tasks?status=needs_input" },
  ];
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        {DEMO_MODE ? (
          <>
            <MonoTag>DEMO DATA</MonoTag>
            <span className="text-[12.5px] text-muted">Counts come from sample tasks in this prototype.</span>
          </>
        ) : (
          <span className="text-[12.5px] text-muted">Counts from your workspace.</span>
        )}
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,190px),1fr))] gap-3">
        {kpis.map((k) => (
          <Link
            key={k.label}
            href={k.href}
            className="flex flex-col gap-1.5 rounded-[10px] border border-line bg-surface p-4 text-left text-ink hover:border-primary-line hover:text-ink hover:no-underline"
          >
            <span className="flex items-center gap-2 text-[13px] text-muted">
              <Icon name={k.icon} size={15} style={{ color: k.color }} />
              {k.label}
            </span>
            <span className="text-[28px] font-semibold leading-[1.1] tracking-[-.02em]">{k.value}</span>
            <span className="text-[12.5px] text-muted">{k.hint}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function QuickTask() {
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useUi();
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  // One idempotency key per attempt: reused if the same text is retried, replaced when the text changes.
  const keyRef = useRef<string | null>(null);

  const m = useMutation({
    mutationFn: (prompt: string) => {
      if (!keyRef.current) keyRef.current = newIdempotencyKey();
      return api.createTask({ prompt, type: guessType(prompt), priority: "normal", mode: "plan_only", title: suggestTitle(prompt) }, keyRef.current);
    },
    onSuccess: (task) => {
      keyRef.current = null;
      setText("");
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      toast(
        DEMO_MODE ? "Task created. A sample plan is being prepared (simulated)." : "Task saved and queued. Nothing runs until you review and approve a plan.",
        "success",
      );
      router.push(`/tasks/${task.id}/plan`);
    },
    onError: (e) => {
      const fe = isApiError(e) ? e.fieldErrors() : {};
      if (fe.prompt) setErr(fe.prompt);
      else toast(errorMessage(e), "danger");
    },
  });

  const change = (v: string) => {
    setText(v);
    setErr("");
    keyRef.current = null;
  };
  const submit = () => {
    const p = text.trim();
    if (p.length < 12) {
      setErr(QUICK_MIN_MSG);
      return;
    }
    m.mutate(p);
  };

  return (
    <section aria-labelledby="qt" className={cx(card, "px-5 py-[18px]")}>
      <h2 id="qt" className="mb-2.5 text-[15px] font-semibold">
        Quick task
      </h2>
      <TextArea
        value={text}
        onChange={(e) => change(e.target.value)}
        aria-label="Describe a task"
        aria-describedby={err ? "qt-err" : undefined}
        rows={3}
        maxLength={4000}
        invalid={!!err}
        placeholder="What would you like the Agent to do?"
        className="min-h-[84px]"
      />
      {err && (
        <div id="qt-err" role="alert" className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-danger">
          <Icon name="circle-alert" size={14} />
          {err}
        </div>
      )}
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        {EXAMPLES.map((x) => (
          <button
            key={x}
            type="button"
            onClick={() => change(x)}
            className="rounded-md border border-line bg-subtle px-2.5 py-[5px] text-left text-[12.5px] text-ink-2 hover:border-primary-line hover:bg-primary-soft"
          >
            {x.length > 46 ? x.slice(0, 44) + "…" : x}
          </button>
        ))}
        <div className="flex-1" />
        <Button variant="primary" icon="list-checks" loading={m.isPending} onClick={submit} className="h-9">
          Plan task
        </Button>
      </div>
      <p className="mt-2.5 text-[12.5px] text-muted">Plan only — nothing runs until you review and approve the plan.</p>
    </section>
  );
}

function RecentTasks({ d }: { d: Dashboard }) {
  return (
    <section aria-labelledby="rt" className={card}>
      <CardHeader
        id="rt"
        title="Recent tasks"
        action={
          <Link href="/tasks" className={headLink}>
            View all
          </Link>
        }
      />
      {d.recent_tasks.length === 0 ? (
        <EmptyState icon="list-checks" title="No tasks yet">
          Describe a task above and the Agent will prepare a plan for you to review.
        </EmptyState>
      ) : (
        d.recent_tasks.slice(0, 5).map((t) => {
          const s = TASK_STATUS[t.status];
          return (
            <Link
              key={t.id}
              href={taskHref(t)}
              className="flex w-full flex-wrap items-center gap-3.5 border-b border-line-soft px-5 py-3 text-left text-ink last:border-b-0 hover:bg-subtle hover:text-ink hover:no-underline"
            >
              <span className="min-w-0 flex-[1_1_220px]">
                <span className="block truncate font-medium">{t.title}</span>
                <span className="block text-[12.5px] text-muted">
                  <span className="font-mono">{t.ref}</span> · Updated {fmtDateTime(t.updated_at)}
                </span>
              </span>
              <Badge meta={s} />
              <span className="inline-flex items-center gap-1 whitespace-nowrap text-[13px] text-primary">
                {TASK_NEXT[t.status]}
                <Icon name="chevron-right" size={14} />
              </span>
            </Link>
          );
        })
      )}
    </section>
  );
}

function PendingApprovals({ d }: { d: Dashboard }) {
  const list = d.pending_approvals;
  return (
    <section aria-labelledby="pa" className={card}>
      <CardHeader
        id="pa"
        title={
          <>
            Pending approvals <span className="font-normal text-muted">· {d.counts.pending_actions}</span>
          </>
        }
        action={
          <Link href="/approvals" className={headLink}>
            Open center
          </Link>
        }
      />
      {list.length === 0 ? (
        <div className="px-5 py-6 text-center text-[13.5px] text-muted">
          <Icon name="circle-check" size={20} className="mx-auto mb-1.5 text-success" />
          Nothing is waiting for you.
        </div>
      ) : (
        list.slice(0, 3).map((a) => {
          const cat = APPROVAL_CATEGORY[a.category];
          const risk = RISK_LEVEL[a.risk];
          return (
            <div key={a.id} className="flex items-start gap-3 border-b border-line-soft px-5 py-3 last:border-b-0">
              <Icon name={cat.icon} size={16} className="mt-[3px]" style={{ color: risk.color }} />
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-medium [text-wrap:pretty]">{a.title}</div>
                <div className="mt-0.5 text-xs text-muted">
                  <span className="font-medium" style={{ color: risk.color }}>
                    {risk.label} risk
                  </span>{" "}
                  · {cat.label}
                </div>
              </div>
              <Link
                href={`/approvals?id=${a.id}`}
                className="inline-flex h-[30px] flex-none items-center rounded-[7px] border border-line-strong bg-surface px-2.5 text-[13px] font-medium text-ink hover:bg-subtle hover:text-ink hover:no-underline"
              >
                Review
              </Link>
            </div>
          );
        })
      )}
    </section>
  );
}

function SetupChecklist({ d }: { d: Dashboard }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useUi();
  const { me } = useSession();
  const verify = useMutation({
    mutationFn: () => api.resendVerification(me?.user.email ?? ""),
    onSuccess: (res) => {
      toast(DEMO_MODE ? res.message : "We sent a new verification link to your email.", "success");
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const s = d.setup;
  const items: { key: string; label: string; done: boolean; cta: string; act: () => void; busy?: boolean }[] = [
    { key: "verify", label: "Verify your email", done: s.verify_email, cta: "Verify", act: () => verify.mutate(), busy: verify.isPending },
    { key: "privacy", label: "Choose privacy defaults", done: s.privacy, cta: "Choose", act: () => router.push("/security") },
    { key: "integ", label: "Connect an integration (backend required)", done: s.integration, cta: "View", act: () => router.push("/integrations") },
    {
      key: "task",
      label: DEMO_MODE ? "Run a safe demo task" : "Create your first task",
      done: s.first_task,
      cta: "Start",
      act: () => router.push(`/tasks/new?prompt=${encodeURIComponent(WORDPRESS_EXAMPLE)}&type=website`),
    },
  ];
  const doneN = items.filter((i) => i.done).length;

  return (
    <section aria-labelledby="sc" className={cx(card, "px-5 py-4")}>
      <div className="flex items-center justify-between gap-2">
        <h2 id="sc" className="text-[15px] font-semibold">
          Setup checklist
        </h2>
        <span className="text-[12.5px] text-muted">{doneN} of 4 done</span>
      </div>
      <div
        className="mb-2 mt-2.5 h-1 overflow-hidden rounded-sm bg-track"
        role="progressbar"
        aria-label="Setup progress"
        aria-valuemin={0}
        aria-valuemax={4}
        aria-valuenow={doneN}
      >
        <div className="h-full bg-primary transition-[width] duration-200" style={{ width: `${(doneN / 4) * 100}%` }} />
      </div>
      {items.map((c) => (
        <div key={c.key} className="flex items-center gap-2.5 py-2">
          <Icon name={c.done ? "circle-check" : "circle"} size={17} style={{ color: c.done ? "#16803C" : "#98A2B3" }} label={c.done ? "Done" : "Not done"} />
          <span className="flex-1 text-[13.5px]" style={{ color: c.done ? "#667085" : "#172033" }}>
            {c.label}
          </span>
          {!c.done && (
            <button
              type="button"
              onClick={c.act}
              disabled={c.busy}
              className="inline-flex items-center gap-1 border-0 bg-transparent px-1 py-0.5 text-[13px] font-medium text-primary hover:underline disabled:opacity-60"
            >
              {c.busy && <Icon name="loader" size={13} spin />}
              {c.cta}
            </button>
          )}
        </div>
      ))}
    </section>
  );
}

function ActivityCard({ d }: { d: Dashboard }) {
  return (
    <section aria-labelledby="at" className={card}>
      <CardHeader
        id="at"
        title="Activity"
        action={
          <Link href="/reports" className={headLink}>
            View log
          </Link>
        }
      />
      {d.recent_activity.length === 0 ? (
        <EmptyState icon="activity" title="No activity yet">
          Everything that happens in this workspace is recorded here.
        </EmptyState>
      ) : (
        <div className="px-5 pb-3 pt-2">
          {d.recent_activity.slice(0, 6).map((a) => (
            <div key={a.id} className="flex gap-3 py-2">
              <span className="grid h-[26px] w-[26px] flex-none place-items-center rounded-[7px] bg-neutral-soft">
                <Icon name={ACTIVITY_ICON[a.type] ?? "activity"} size={13} className="text-ink-3" />
              </span>
              <div className="min-w-0">
                <div className="text-[13.5px] [text-wrap:pretty]">{a.message}</div>
                <div className="text-xs text-muted">{fmtDateTime(a.created_at)}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
