"use client";

import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type AccountRequest } from "@/lib/api";
import { Banner, Button, Checkbox, FieldError, Icon, Label, Modal, TextArea } from "@/components/ui";

const DELETION_FALLBACK = "Request received. Deletion is reviewed manually; nothing is deleted automatically.";

function Sent({ res }: { res: AccountRequest }) {
  return (
    <div className="p-5">
      <Banner tone="success" icon="circle-check" title="Request received" role="status">
        {res.message}
      </Banner>
    </div>
  );
}

/** "Request data export" — records a request on the server and shows the server's own message. */
export function DataExportModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api.requestDataExport(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activity"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  return (
    <Modal
      title="Request data export"
      onClose={onClose}
      footer={
        m.data ? (
          <Button variant="primary" onClick={onClose} className="px-4">
            Got it
          </Button>
        ) : (
          <>
            <Button onClick={onClose} className="px-4">
              Cancel
            </Button>
            <Button variant="primary" loading={m.isPending} onClick={() => m.mutate()} className="px-4">
              Request export
            </Button>
          </>
        )
      }
    >
      {m.data ? (
        <Sent res={m.data} />
      ) : (
        <div className="flex flex-col gap-3 p-5">
          <p className="text-ink-2 [text-wrap:pretty]">
            An export includes your tasks, files and activity log. It is prepared on the server and sent via a short-lived private link.
            {DEMO_MODE ? " Demo: no export is created." : " Sending this only records your request — you'll see exactly what happens next."}
          </p>
          {m.isError && (
            <Banner tone="danger" icon="circle-alert" role="alert">
              {errorMessage(m.error)}
            </Banner>
          )}
        </div>
      )}
    </Modal>
  );
}

/** "Request account deletion" — needs a reason and an explicit confirmation. Nothing is deleted automatically. */
export function AccountDeletionModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [touched, setTouched] = useState(false);
  const rid = useId();
  const cid = useId();
  const m = useMutation({
    mutationFn: (r: string) => api.requestAccountDeletion(r),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activity"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const fieldErr = isApiError(m.error) ? m.error.fieldErrors().reason : undefined;
  const reasonErr = touched && !reason.trim() ? "Please tell us why you want to delete your account." : fieldErr;
  const submit = () => {
    setTouched(true);
    if (!reason.trim() || !confirmed) return;
    m.mutate(reason.trim());
  };

  return (
    <Modal
      title="Request account deletion"
      onClose={onClose}
      footer={
        m.data ? (
          <Button variant="primary" onClick={onClose} className="px-4">
            Got it
          </Button>
        ) : (
          <>
            <Button onClick={onClose} className="px-4">
              Close
            </Button>
            <Button variant="danger-solid" loading={m.isPending} disabled={!reason.trim() || !confirmed} onClick={submit} className="px-4">
              Request deletion
            </Button>
          </>
        )
      }
    >
      {m.data ? (
        <Sent res={{ ...m.data, message: m.data.message || DELETION_FALLBACK }} />
      ) : (
        <div className="flex flex-col gap-4 p-5">
          <div className="flex gap-3">
            <Icon name="triangle-alert" size={20} className="mt-0.5 text-danger" />
            <p className="text-ink-2 [text-wrap:pretty]">
              {DEMO_MODE
                ? "Account deletion would be confirmed by email and carried out by the backend after a waiting period, following the retention policy. Demo: no request is sent and nothing is deleted."
                : "Deletion is reviewed manually and carried out after a waiting period, following the retention policy. Sending this request deletes nothing."}
            </p>
          </div>
          <div>
            <Label htmlFor={rid}>Reason</Label>
            <TextArea
              id={rid}
              rows={3}
              value={reason}
              maxLength={1000}
              invalid={!!reasonErr}
              aria-describedby={reasonErr ? `${rid}-err` : undefined}
              onChange={(e) => setReason(e.target.value)}
              onBlur={() => setTouched(true)}
              placeholder="Tell us why you're leaving"
            />
            <FieldError id={`${rid}-err`}>{reasonErr}</FieldError>
          </div>
          <Checkbox id={cid} checked={confirmed} onChange={setConfirmed}>
            I understand this asks for my account and workspace to be permanently deleted after review.
          </Checkbox>
          {m.isError && !fieldErr && (
            <Banner tone="danger" icon="circle-alert" role="alert">
              {errorMessage(m.error)}
            </Banner>
          )}
        </div>
      )}
    </Modal>
  );
}
