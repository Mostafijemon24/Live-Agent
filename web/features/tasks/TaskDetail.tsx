"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type Task } from "@/lib/api";
import { TASK_STATUS, TASK_TYPE_LABEL } from "@/lib/labels";
import { useUi } from "@/lib/session";
import { Button, ErrorState, Icon, Modal, Skeleton, TextArea, cx } from "@/components/ui";
import { LinkButton, StatusBadge } from "./shared";
import { ApprovalsTab, AuditTab, InputsTab, LogsTab, OutputsTab, PlanTab, SummaryTab } from "./TaskTabs";

const TABS = [
  ["summary", "Summary"],
  ["plan", "Plan & steps"],
  ["inputs", "Inputs & attachments"],
  ["approvals", "Approval history"],
  ["logs", "Run logs"],
  ["artifacts", "Outputs"],
  ["audit", "Audit events"],
] as const;
type TabKey = (typeof TABS)[number][0];
const isTab = (v: string | null): v is TabKey => TABS.some(([k]) => k === v);

export function TaskDetail({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["task", id], queryFn: () => api.getTask(id) });

  if (q.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <div className="rounded-[10px] border border-line bg-surface p-5">
          <Skeleton lines={5} />
        </div>
      </div>
    );
  }
  if (q.error || !q.data) {
    const status = isApiError(q.error) ? q.error.status : 0;
    if (status === 404 || status === 422) {
      return (
        <Missing
          tag="NOT FOUND"
          icon="map-pin-off"
          iconClass="text-ink-3"
          title="Task not found"
          body="This task doesn't exist, or the link is out of date. It may belong to another workspace."
        />
      );
    }
    if (status === 403) {
      return (
        <Missing
          tag="PERMISSION DENIED"
          icon="lock"
          iconClass="text-warning"
          title="You don't have access to this"
          body="This task belongs to another workspace or needs a role you don't have. Ask a workspace admin."
        />
      );
    }
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} title="We couldn't load this task" />
      </div>
    );
  }
  return <TaskView task={q.data} />;
}

function BackLink() {
  return (
    <Link href="/tasks" className="inline-flex items-center gap-1.5 self-start text-[13.5px] text-ink-3 hover:text-ink">
      <Icon name="arrow-left" size={15} />
      Tasks
    </Link>
  );
}

function Missing({ tag, icon, iconClass, title, body }: { tag: string; icon: string; iconClass: string; title: string; body: string }) {
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <article role="alert" className="flex max-w-[520px] flex-col items-start gap-2 rounded-[10px] border border-line bg-surface p-[18px]">
        <div className="font-mono text-xs text-muted">{tag}</div>
        <Icon name={icon} size={20} className={iconClass} />
        <div className="font-semibold">{title}</div>
        <div className="text-[13.5px] text-muted">{body}</div>
        <LinkButton href="/tasks" className="h-8 rounded-[7px] px-3 text-[13px]">
          Back to tasks
        </LinkButton>
      </article>
    </div>
  );
}

type ModalKind = "answer" | "cancel" | null;

function TaskView({ task }: { task: Task }) {
  const router = useRouter();
  const pathname = usePathname() ?? `/tasks/${task.id}`;
  const sp = useSearchParams();
  const qc = useQueryClient();
  const { toast, notice } = useUi();
  const [modal, setModal] = useState<ModalKind>(null);
  const [answer, setAnswer] = useState("");
  const baseId = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const rawTab = sp?.get("tab") ?? null;
  const tab: TabKey = isTab(rawTab) ? rawTab : "summary";
  const pickTab = (k: TabKey) => {
    const next = new URLSearchParams(sp?.toString() ?? "");
    if (k === "summary") next.delete("tab");
    else next.set("tab", k);
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };
  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    let n = -1;
    if (e.key === "ArrowRight") n = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = TABS.length - 1;
    if (n < 0) return;
    e.preventDefault();
    pickTab(TABS[n][0]);
    tabRefs.current[n]?.focus();
  };

  const can = (a: Task["allowed_actions"][number]) => task.allowed_actions.includes(a);

  const settle = (t: Task) => {
    qc.setQueryData(["task", task.id], t);
    for (const key of [["task", task.id], ["tasks"], ["dashboard"], ["task-events", task.id], ["activity"]]) {
      void qc.invalidateQueries({ queryKey: key });
    }
  };
  const onError = (e: unknown) => toast(errorMessage(e), "danger");

  const pause = useMutation({
    mutationFn: () => api.pauseTask(task.id),
    onSuccess: (t) => {
      settle(t);
      toast(DEMO_MODE ? "Task paused (simulated)." : "Task paused.", "info");
    },
    onError,
  });
  const resume = useMutation({
    mutationFn: () => api.resumeTask(task.id),
    onSuccess: (t) => {
      settle(t);
      toast(DEMO_MODE ? "Task resumed (simulated)." : "Task resumed. The next step will start shortly.", "info");
    },
    onError,
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(task.id),
    onSuccess: (t) => {
      settle(t);
      setModal(null);
      toast(
        DEMO_MODE
          ? "Task cancelled (simulated). Steps that already finished are listed in the log."
          : "Task cancelled. Steps that already finished are listed in the log.",
        "info",
      );
    },
    onError,
  });
  const sendAnswer = useMutation({
    mutationFn: (text: string) => api.postTaskMessage(task.id, text, "answer"),
    onSuccess: (t) => {
      settle(t);
      setModal(null);
      setAnswer("");
      toast(
        DEMO_MODE ? "Answer sent. Task resumed (simulated)." : "Answer recorded. The task continues.",
        "success",
      );
    },
    onError,
  });

  const copyError = async () => {
    const text = `${task.ref} · ${TASK_STATUS[task.status].label} · ${task.error_message ?? ""}`;
    try {
      await navigator.clipboard.writeText(text);
      toast("Error details copied. Secrets and file contents are excluded.", "success");
    } catch {
      toast("Your browser blocked copying. Select the text and copy it manually.", "danger");
    }
  };
  const retry = () =>
    notice(
      "Retry needs the execution engine",
      "Failed tasks are not retried automatically. Create a new task (or ask for a plan change) so the new plan is reviewed and approved again before anything re-runs.",
    );

  const busy = pause.isPending || resume.isPending || cancel.isPending;
  const secondary = "h-9 px-3 text-[13.5px]";
  const nothingRan = !task.plan || task.plan.steps.every((s) => s.state === "not_started");

  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-[1_1_400px]">
          <div className="font-mono text-[12.5px] text-muted">
            {task.ref} · {TASK_TYPE_LABEL[task.type]} · {task.priority === "high" ? "High" : "Normal"} priority
          </div>
          <h1 className="mb-2 mt-0.5 text-2xl font-semibold tracking-[-.015em] [overflow-wrap:anywhere] [text-wrap:balance]">{task.title}</h1>
          <StatusBadge status={task.status} size="lg" />
        </div>
        <div className="flex flex-wrap gap-2">
          {task.status === "awaiting_approval" && (
            <LinkButton href={`/tasks/${task.id}/plan`} variant="primary" className="h-9 px-3.5 text-[13.5px]">
              Review plan
            </LinkButton>
          )}
          {can("answer") && (
            <Button variant="primary" className="h-9 px-3.5 text-[13.5px]" onClick={() => setModal("answer")}>
              Answer question
            </Button>
          )}
          {can("pause") && (
            <Button icon="pause" className={secondary} loading={pause.isPending} disabled={busy} onClick={() => pause.mutate()}>
              Pause
            </Button>
          )}
          {can("resume") && (
            <Button icon="play" className={secondary} loading={resume.isPending} disabled={busy} onClick={() => resume.mutate()}>
              Resume
            </Button>
          )}
          {task.status === "failed" && (
            <Button icon="rotate-ccw" className={secondary} onClick={retry}>
              Retry
            </Button>
          )}
          {can("cancel") && (
            <Button variant="danger" className={secondary} disabled={busy} onClick={() => setModal("cancel")}>
              Cancel task
            </Button>
          )}
        </div>
      </div>

      <div role="tablist" aria-label="Task sections" className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line">
        {TABS.map(([k, l], i) => {
          const active = k === tab;
          return (
            <button
              key={k}
              ref={(el) => {
                tabRefs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${k}`}
              aria-selected={active}
              aria-controls={`${baseId}-panel`}
              tabIndex={active ? 0 : -1}
              onClick={() => pickTab(k)}
              onKeyDown={(e) => onTabKey(e, i)}
              className={cx(
                "-mb-px h-10 whitespace-nowrap border-0 border-b-2 bg-transparent px-3 text-[13.5px] font-medium",
                active ? "border-primary text-primary" : "border-transparent text-ink-3 hover:text-ink",
              )}
            >
              {l}
            </button>
          );
        })}
      </div>

      <div role="tabpanel" id={`${baseId}-panel`} aria-labelledby={`${baseId}-tab-${tab}`}>
        {tab === "summary" && <SummaryTab task={task} onAnswer={can("answer") ? () => setModal("answer") : undefined} onCopyError={copyError} />}
        {tab === "plan" && <PlanTab task={task} />}
        {tab === "inputs" && <InputsTab task={task} />}
        {tab === "approvals" && <ApprovalsTab task={task} />}
        {tab === "logs" && <LogsTab task={task} onCopy={copyError} />}
        {tab === "artifacts" && <OutputsTab task={task} />}
        {tab === "audit" && <AuditTab task={task} />}
      </div>

      {modal === "answer" && (
        <Modal
          title="Answer the Agent"
          onClose={() => setModal(null)}
          footer={
            <>
              <Button className="px-3.5" onClick={() => setModal(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                className="px-4"
                disabled={!answer.trim()}
                loading={sendAnswer.isPending}
                onClick={() => sendAnswer.mutate(answer.trim())}
              >
                Send answer
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-2.5 p-5">
            {task.question && <div className="rounded-lg bg-warning-soft px-3.5 py-3 text-[13.5px] text-[#93370D]">{task.question}</div>}
            <label className="flex flex-col gap-1.5 text-[13px] font-medium">
              Your answer
              <TextArea
                rows={4}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="Type your answer in plain language."
                className="font-normal"
                maxLength={4000}
              />
            </label>
          </div>
        </Modal>
      )}

      {modal === "cancel" && (
        <Modal
          title="Cancel task"
          onClose={() => setModal(null)}
          footer={
            <>
              <Button className="px-3.5" onClick={() => setModal(null)}>
                {task.status === "running" ? "Keep running" : "Keep task"}
              </Button>
              <Button variant="danger-solid" className="px-4" loading={cancel.isPending} onClick={() => cancel.mutate()}>
                Cancel task
              </Button>
            </>
          }
        >
          <div className="p-5">
            <p className="text-ink-2">
              <strong>
                {task.ref} · {task.title}
              </strong>{" "}
              {nothingRan
                ? "will be cancelled. Nothing has run yet, so there is nothing to undo. This can't be resumed."
                : "will stop. Steps already finished stay as they are and are listed in the log. This can't be resumed."}
            </p>
          </div>
        </Modal>
      )}
    </div>
  );
}
