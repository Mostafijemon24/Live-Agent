"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, type FileItem } from "@/lib/api";
import { Banner, Button, Icon, Modal, TextArea } from "@/components/ui";
import { useUi } from "@/lib/session";

/** Deletion is a request, not an action: it creates a record_deletion approval and opens it. */
export function DeleteFileModal({ file, onClose }: { file: FileItem; onClose: () => void }) {
  const qc = useQueryClient();
  const router = useRouter();
  const { toast } = useUi();
  const id = useId();
  const [reason, setReason] = useState("");
  const trimmed = reason.trim();

  const m = useMutation({
    mutationFn: () => api.requestFileDeletion(file.id, trimmed),
    onSuccess: (approval) => {
      qc.setQueryData(["approval", approval.id], approval);
      void qc.invalidateQueries({ queryKey: ["files"] });
      void qc.invalidateQueries({ queryKey: ["file", file.id] });
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: ["activity"] });
      toast("Deletion needs its own approval. Review it here.", "info");
      onClose();
      router.push(`/approvals?id=${encodeURIComponent(approval.id)}&filter=pending`);
    },
  });

  return (
    <Modal
      title="Request deletion"
      onClose={m.isPending ? () => {} : onClose}
      footer={
        <>
          <Button onClick={onClose} disabled={m.isPending}>
            Cancel
          </Button>
          <Button variant="danger-solid" className="px-4" disabled={!trimmed} loading={m.isPending} onClick={() => trimmed && m.mutate()}>
            Request deletion
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3 p-5">
        <div className="flex gap-2 rounded-lg border border-danger-line bg-danger-soft px-3.5 py-3 text-[13.5px] text-danger">
          <Icon name="trash-2" size={15} className="mt-0.5" />
          <span className="min-w-0 [overflow-wrap:anywhere]">
            <strong className="font-semibold">{file.name}</strong> will not be deleted yet. This creates an approval request that covers only this file.
          </span>
        </div>
        <label htmlFor={id} className="flex flex-col gap-1.5 text-[13px] font-medium">
          Why should it be deleted?
          <TextArea
            id={id}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={1000}
            aria-required
            placeholder="e.g. Old export, replaced by a newer crawl."
            className="font-normal"
          />
        </label>
        {m.error && (
          <Banner tone="danger" icon="circle-alert" role="alert">
            {errorMessage(m.error)}
          </Banner>
        )}
      </div>
    </Modal>
  );
}
