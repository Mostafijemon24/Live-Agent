"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage } from "@/lib/api";
import type { Task } from "@/lib/api/types";
import { useUi } from "@/lib/session";
import { Button, Modal } from "@/components/ui";

export type PlanModalKind = "approvePlan" | "rejectPlan" | "editPlan" | "ask" | "cancelTask";

const TITLES: Record<PlanModalKind, string> = {
  approvePlan: "Approve selected steps",
  rejectPlan: "Reject plan",
  editPlan: "Edit plan",
  ask: "Ask a question",
  cancelTask: "Cancel task",
};

const COPY = {
  approved: DEMO_MODE
    ? "Plan approved (simulated). The demo agent does not touch any real system."
    : "Plan approved and recorded. Nothing ran — the execution engine isn't installed yet.",
  ack: DEMO_MODE
    ? "I understand this is a simulated approval. No step will touch a real system."
    : "I understand approving the plan records my decision; each high-impact step still needs its own approval.",
  rejected: "Plan rejected. The task was cancelled; nothing ran.",
  revised: DEMO_MODE
    ? "Plan change requested. Demo note: the sample plan stays the same — a real agent would update it."
    : "Plan change request saved to the task. The planner will prepare a revised plan.",
  editNote: DEMO_MODE ? "Demo: the sample plan won't actually change." : "Your request is saved to the task log. The planner uses it to prepare a revised plan.",
  asked: DEMO_MODE
    ? "Question saved to the task log. The demo agent cannot answer — an AI provider is required."
    : "Question saved to the task log. The Agent can answer once the AI engine is installed (Phase 3).",
  cancelled: "Task cancelled. Nothing had run.",
};

const textareaCls = "rounded-lg border border-line-strong px-3 py-2.5 text-sm font-normal resize-y placeholder:text-faint";
const labelCls = "flex flex-col gap-1.5 text-[13px] font-medium";

export function PlanModal({
  kind,
  task,
  selectedIds,
  total,
  onClose,
}: {
  kind: PlanModalKind;
  task: Task;
  selectedIds: string[];
  total: number;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const { toast } = useUi();
  const [text, setText] = useState("");
  const [check, setCheck] = useState(false);
  const id = task.id;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["task", id] });
    qc.invalidateQueries({ queryKey: ["task-events", id] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const m = useMutation({
    mutationFn: async (): Promise<Task> => {
      const note = text.trim();
      switch (kind) {
        case "approvePlan":
          return api.approvePlan(id, selectedIds);
        case "rejectPlan":
          return api.rejectPlan(id, note || undefined);
        case "editPlan":
          return api.postTaskMessage(id, note, "plan_change");
        case "ask":
          return api.postTaskMessage(id, note, "question");
        case "cancelTask":
          return api.cancelTask(id);
      }
    },
    onSuccess: (updated) => {
      qc.setQueryData(["task", id], updated);
      refresh();
      onClose();
      if (kind === "approvePlan") {
        toast(COPY.approved, "success");
        router.push(`/tasks/${id}?tab=plan`);
      } else if (kind === "rejectPlan") {
        toast(COPY.rejected, "info");
        router.push(`/tasks/${id}`);
      } else if (kind === "editPlan") toast(COPY.revised, "info");
      else if (kind === "ask") toast(COPY.asked, "info");
      else toast(COPY.cancelled, "info");
    },
    onError: (e) => {
      toast(errorMessage(e), "danger");
      // The task may have moved on (e.g. a 409 conflict) — reload its real state.
      qc.invalidateQueries({ queryKey: ["task", id] });
    },
  });

  const textEmpty = !text.trim();
  const cancelBtn = (label = "Cancel") => (
    <Button onClick={onClose} className="px-3.5">
      {label}
    </Button>
  );

  let body: ReactNode;
  let footer: ReactNode;
  switch (kind) {
    case "approvePlan":
      body = (
        <div className="flex flex-col gap-3.5 p-5">
          <div>
            <div className="font-medium">{task.title}</div>
            <div className="mt-0.5 text-[13.5px] text-ink-3">
              {selectedIds.length} of {total} steps selected. Steps that change live systems, publish, send or share will still ask for their own approval.
            </div>
          </div>
          <label className="flex cursor-pointer items-start gap-2.5 text-[13.5px]">
            <input type="checkbox" checked={check} onChange={(e) => setCheck(e.target.checked)} className="mt-[3px] accent-primary" />
            {COPY.ack}
          </label>
        </div>
      );
      footer = (
        <>
          {cancelBtn()}
          <Button variant="primary" disabled={!check || selectedIds.length === 0} loading={m.isPending} onClick={() => m.mutate()} className="px-4">
            Approve steps
          </Button>
        </>
      );
      break;
    case "rejectPlan":
      body = (
        <div className="flex flex-col gap-2.5 p-5">
          <p className="text-ink-2">The task will be cancelled. No step has run.</p>
          <label className={labelCls}>
            Reason (optional)
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000} className={textareaCls} />
          </label>
        </div>
      );
      footer = (
        <>
          {cancelBtn("Keep plan")}
          <Button variant="danger-solid" loading={m.isPending} onClick={() => m.mutate()} className="px-4">
            Reject plan
          </Button>
        </>
      );
      break;
    case "editPlan":
      body = (
        <div className="flex flex-col gap-2.5 p-5">
          <label className={labelCls}>
            Tell the Agent how to change the plan
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              maxLength={4000}
              placeholder="e.g. Skip the speed test and only check the 10 most visited pages."
              className={textareaCls}
            />
          </label>
          <p className="text-[12.5px] text-muted">{COPY.editNote}</p>
        </div>
      );
      footer = (
        <>
          {cancelBtn()}
          <Button variant="primary" disabled={textEmpty} loading={m.isPending} onClick={() => m.mutate()} className="px-4">
            Revise plan
          </Button>
        </>
      );
      break;
    case "ask":
      body = (
        <div className="p-5">
          <label className={labelCls}>
            Your question
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              maxLength={4000}
              placeholder="e.g. Will step 2 slow down the site for visitors?"
              className={textareaCls}
            />
          </label>
        </div>
      );
      footer = (
        <>
          {cancelBtn()}
          <Button variant="primary" disabled={textEmpty} loading={m.isPending} onClick={() => m.mutate()} className="px-4">
            Send question
          </Button>
        </>
      );
      break;
    case "cancelTask":
      body = (
        <div className="p-5">
          <p className="text-ink-2">
            <strong>
              {task.ref} · {task.title}
            </strong>{" "}
            will be cancelled. Nothing has run, so there is nothing to undo. This can&apos;t be resumed.
          </p>
        </div>
      );
      footer = (
        <>
          {cancelBtn("Keep task")}
          <Button variant="danger-solid" loading={m.isPending} onClick={() => m.mutate()} className="px-4">
            Cancel task
          </Button>
        </>
      );
      break;
  }

  return (
    <Modal title={TITLES[kind]} onClose={onClose} footer={footer}>
      {body}
    </Modal>
  );
}
