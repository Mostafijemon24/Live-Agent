"use client";

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import type { TaskStatus, TaskSummary, WaitingFor } from "@/lib/api";
import { TASK_STATUS } from "@/lib/labels";
import { Icon, cx } from "@/components/ui";

/** The prototype's dec().open rule: plans under review open the plan screen, everything else the detail screen. */
export function taskHref(t: Pick<TaskSummary, "id" | "status">): string {
  return t.status === "awaiting_approval" || t.status === "planning" ? `/tasks/${t.id}/plan` : `/tasks/${t.id}`;
}

export const INTEGRATION_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All integrations" },
  { value: "wordpress", label: "WordPress" },
  { value: "none", label: "None" },
];

export function integrationLabel(key: string | null): string {
  if (!key) return "None";
  if (key === "wordpress") return "WordPress";
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/** Reasons a task is not moving — shown instead of the "next action" text. */
export const WAITING_LABEL: Partial<Record<NonNullable<WaitingFor>, string>> = {
  planning_service: "Waiting to be planned",
  execution_engine: "Queued to run",
  approval: "Waiting for your approval",
  user_input: "Waiting for your answer",
};

export function waitingLabel(w: WaitingFor): string | null {
  return w ? (WAITING_LABEL[w] ?? null) : null;
}

/** Status badge, in the list size (12px) or the detail-header size (13px). */
export function StatusBadge({ status, size = "sm" }: { status: TaskStatus; size?: "sm" | "lg" }) {
  const m = TASK_STATUS[status];
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md font-medium",
        size === "lg" ? "px-2.5 py-[3px] text-[13px]" : "px-2 py-0.5 text-xs",
      )}
      style={{ color: m.fg, background: m.bg }}
    >
      <Icon name={m.icon} size={size === "lg" ? 14 : 13} />
      {m.label}
    </span>
  );
}

const LB_VARIANT = {
  primary: "border-0 bg-primary text-white hover:bg-primary-hover hover:text-white",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-subtle hover:text-ink",
};

/** A next/link styled like the kit's Button (the kit Button is a <button>). */
export function LinkButton({
  variant = "secondary",
  icon,
  className,
  children,
  ...rest
}: { variant?: keyof typeof LB_VARIANT; icon?: string; children: ReactNode } & ComponentProps<typeof Link>) {
  return (
    <Link
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium transition-colors duration-150 hover:no-underline",
        LB_VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {icon && <Icon name={icon} size={16} />}
      {children}
    </Link>
  );
}
