"use client";

import type { FileClassification, FileItem, FileStatus } from "@/lib/api";
import { CLASSIFICATION, FILE_STATUS, FILE_TYPE_ICON } from "@/lib/labels";
import { Icon, cx } from "@/components/ui";

export const BUSY_STATUSES: FileStatus[] = ["uploading", "scanning", "processing"];
export const isBusy = (s: FileStatus) => BUSY_STATUSES.includes(s);

export const fileIcon = (f: Pick<FileItem, "type_label">) => FILE_TYPE_ICON[f.type_label?.toUpperCase()] ?? "file";

/** File-input `accept` from the server's human type labels ("PDF", "DOCX" → ".pdf,.docx"). */
export function acceptFromLabels(labels: string[]): string | undefined {
  const exts = labels
    .map((l) => l.trim().toLowerCase().replace(/^\./, ""))
    .filter((l) => /^[a-z0-9]{1,8}$/.test(l))
    .map((l) => `.${l}`);
  return exts.length ? exts.join(",") : undefined;
}

export const SCAN_TEXT: Record<FileItem["scan_status"], string> = {
  not_configured: "Malware scanning: not configured",
  pending: "Malware scanning: pending",
  clean: "Malware scanning: no threats found",
  infected: "Malware scanning: threat found",
};

export function FileStatusBadge({ status, className }: { status: FileStatus; className?: string }) {
  const m = FILE_STATUS[status];
  const busy = isBusy(status);
  return (
    <span
      className={cx("inline-flex items-center gap-[5px] whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium", className)}
      style={{ color: m.fg, background: m.bg }}
    >
      <Icon name={busy ? "loader" : m.icon} size={12} spin={busy} />
      {m.label}
    </span>
  );
}

export function ClassificationBadge({ cls, className }: { cls: FileClassification; className?: string }) {
  const c = CLASSIFICATION[cls];
  return (
    <span
      className={cx("inline-flex items-center gap-[5px] whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium", className)}
      style={{ color: c.fg, background: c.bg }}
    >
      <Icon name={c.icon} size={12} />
      {c.label}
    </span>
  );
}
