"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type Approval, type ApprovalDecision } from "@/lib/api";
import { Banner, Button, Checkbox, Icon, Modal, TextArea } from "@/components/ui";
import { useUi } from "@/lib/session";

export type DecisionKind = "approve" | "reject" | "changes";

const TITLE: Record<DecisionKind, string> = {
  approve: "Approve once",
  reject: "Reject request",
  changes: "Request changes",
};

const DECISION: Record<DecisionKind, ApprovalDecision> = {
  approve: "approve",
  reject: "reject",
  changes: "request_changes",
};

const ACK_COPY = DEMO_MODE
  ? "I understand this is a simulated approval. Nothing will actually run."
  : "I understand this approves this exact action once. If anything about it changes before it runs, it will need a new approval.";

/** Toast copy after a successful decision — prototype copy in demo, the real outcome otherwise. */
function successToast(kind: DecisionKind): { text: string; tone: "success" | "info" } {
  if (DEMO_MODE) {
    if (kind === "approve") return { text: "Approval recorded (simulated). Nothing was executed — no backend is connected.", tone: "success" };
    if (kind === "reject") return { text: "Rejected. The Agent will not perform this action.", tone: "info" };
    return { text: "Change request added to the task (simulated).", tone: "success" };
  }
  if (kind === "reject") return { text: "Rejected and recorded. The Agent will not perform this action.", tone: "info" };
  return { text: "Decision recorded. If approved, the action runs once after a final check.", tone: "success" };
}

/** The approve / reject / request-changes dialogs (prototype modal.is.approve|reject|changes). */
export function DecisionModal({ approval, kind, onClose }: { approval: Approval; kind: DecisionKind; onClose: () => void }) {
  const qc = useQueryClient();
  const { toast } = useUi();
  const [ack, setAck] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [note, setNote] = useState("");

  const isDelete = approval.category === "record_deletion";
  const n = approval.affected_items.length;
  const noteTrim = note.trim();

  const m = useMutation({
    mutationFn: () =>
      api.decideApproval(approval.id, {
        decision: DECISION[kind],
        note: noteTrim || undefined,
        acknowledged: kind === "approve" ? ack : true,
        confirmed_items: kind === "approve" && isDelete ? approval.affected_items : undefined,
      }),
    onSuccess: (updated) => {
      qc.setQueryData(["approval", approval.id], updated);
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["approval", approval.id] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      const t = successToast(kind);
      toast(t.text, t.tone);
      onClose();
    },
  });

  const canSubmit =
    kind === "approve" ? ack && (!isDelete || reviewed) : kind === "changes" ? noteTrim.length > 0 : true;

  const serverError = m.error ? (
    <Banner tone="danger" icon="circle-alert" role="alert">
      {errorMessage(m.error)}
      {isApiError(m.error) && Object.values(m.error.fieldErrors()).length > 0 && (
        <ul className="mt-1 list-disc pl-4">
          {Object.entries(m.error.fieldErrors()).map(([k, v]) => (
            <li key={k}>{v}</li>
          ))}
        </ul>
      )}
    </Banner>
  ) : null;

  const footer = (
    <>
      <Button onClick={onClose} disabled={m.isPending}>
        Cancel
      </Button>
      {kind === "approve" && (
        <Button variant="primary" className="px-4" disabled={!canSubmit} loading={m.isPending} onClick={() => canSubmit && m.mutate()}>
          Approve once
        </Button>
      )}
      {kind === "reject" && (
        <Button variant="danger-solid" className="px-4" loading={m.isPending} onClick={() => m.mutate()}>
          Reject request
        </Button>
      )}
      {kind === "changes" && (
        <Button variant="primary" className="px-4" disabled={!canSubmit} loading={m.isPending} onClick={() => canSubmit && m.mutate()}>
          Send request
        </Button>
      )}
    </>
  );

  return (
    <Modal title={TITLE[kind]} onClose={m.isPending ? () => {} : onClose} footer={footer}>
      {kind === "approve" ? (
        <div className="flex flex-col gap-3.5 p-5">
          <div className="font-medium">{approval.title}</div>
          <div className="text-[13.5px] text-ink-3">
            Scope: {approval.scope_summary} · {approval.destination}. This approval applies once, to exactly this action. Any change needs a new
            approval.
          </div>
          {isDelete && (
            <>
              <div className="flex gap-2 rounded-lg border border-danger-line bg-danger-soft px-3.5 py-3 text-[13.5px] text-danger">
                <Icon name="trash-2" size={15} className="mt-0.5" />
                <span>
                  {n} item(s) will be deleted. {approval.reversible}
                </span>
              </div>
              <Checkbox checked={reviewed} onChange={setReviewed}>
                I reviewed the exact list of {n} item(s).
              </Checkbox>
            </>
          )}
          <Checkbox checked={ack} onChange={setAck}>
            {ACK_COPY}
          </Checkbox>
          {serverError}
        </div>
      ) : (
        <div className="flex flex-col gap-2.5 p-5">
          <div className="font-medium">{approval.title}</div>
          <label className="flex flex-col gap-1.5 text-[13px] font-medium">
            {kind === "reject" ? "Reason (optional)" : "What should change?"}
            <TextArea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              placeholder={kind === "changes" ? "e.g. Only change robots.txt, leave caching as it is." : undefined}
              className="font-normal"
              aria-required={kind === "changes" || undefined}
            />
          </label>
          {serverError}
        </div>
      )}
    </Modal>
  );
}
