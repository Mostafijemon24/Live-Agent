"use client";

import Link from "next/link";
import type { TaskStep } from "@/lib/api/types";
import { CLASSIFICATION, IMPACT, POLICY_OUTCOME } from "@/lib/labels";
import { outputLines } from "@/lib/step-output";
import { Icon } from "@/components/ui";

function classLabel(c: string): string {
  return c in CLASSIFICATION ? CLASSIFICATION[c as keyof typeof CLASSIFICATION].short : c;
}

/** Server-side policy decision for a step: outcome, reasons, impact, data classes and destinations. */
export function StepPolicy({ step }: { step: TaskStep }) {
  const p = step.policy;
  if (!p && !step.impact) return null;
  const meta = p ? POLICY_OUTCOME[p.outcome] : null;
  const dests = step.destinations ?? [];
  const classes = step.classifications ?? [];
  return (
    <div className="mt-1.5 flex flex-col gap-1 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {meta && (
          <span className="inline-flex items-center gap-1 rounded-md px-1.5 py-px font-medium" style={{ color: meta.fg, background: meta.bg }}>
            <Icon name={meta.icon} size={12} />
            {meta.label}
          </span>
        )}
        {step.impact && <span className="text-ink-3">{IMPACT[step.impact] ?? step.impact}</span>}
        {classes.length > 0 && <span className="text-muted">Data: {classes.map(classLabel).join(", ")}</span>}
        <span className="text-muted">
          {dests.length ? (
            <>
              Goes to: <span className="font-mono">{dests.join(", ")}</span>
            </>
          ) : (
            "Nothing leaves this workspace"
          )}
        </span>
      </div>
      {p && p.reasons.length > 0 && <div className="text-muted [text-wrap:pretty]">{p.reasons.join(" ")}</div>}
      <StepArgs step={step} />
    </div>
  );
}

/** The exact arguments the step will run with — what an approval binds. Plain text, never HTML. */
export function StepArgs({ step }: { step: TaskStep }) {
  const args = step.args ?? {};
  const keys = Object.keys(args);
  if (!keys.length) return null;
  return (
    <details className="rounded-md border border-line-soft bg-subtle px-2.5 py-1.5">
      <summary className="cursor-pointer text-muted">Exact arguments ({step.tool_id})</summary>
      <dl className="mt-1.5 flex flex-col gap-1.5">
        {keys.map((k) => {
          const v = args[k];
          const text = typeof v === "string" ? v : JSON.stringify(v, null, 2);
          return (
            <div key={k}>
              <dt className="font-medium text-ink-3">{k}</dt>
              <dd>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] text-ink-2">{text}</pre>
              </dd>
            </div>
          );
        })}
      </dl>
      {step.args_hash && <div className="mt-1 font-mono text-[11px] text-muted">Fingerprint {step.args_hash.slice(0, 16)}…</div>}
    </details>
  );
}

/** Result of a step: summary, error, and the tool output rendered as plain data (never HTML). */
export function StepResult({ step }: { step: TaskStep }) {
  const lines = outputLines(step.output);
  if (!step.output_summary && !step.error && !lines.length && !step.approval_id) return null;
  return (
    <div className="mt-1.5 flex flex-col gap-1 text-[12.5px]">
      {step.output_summary && <div className="text-ink-2 [text-wrap:pretty]">{step.output_summary}</div>}
      {step.error && (
        <div className="flex items-start gap-1.5 text-danger">
          <Icon name="circle-alert" size={13} className="mt-px" />
          <span className="[text-wrap:pretty]">{step.error}</span>
        </div>
      )}
      {step.approval_id && (
        <Link href={`/approvals?id=${step.approval_id}`} className="w-fit font-medium">
          View its approval request
        </Link>
      )}
      {lines.length > 0 && (
        <details className="rounded-md border border-line-soft bg-subtle px-2.5 py-1.5">
          <summary className="cursor-pointer text-muted">Step output (data from the tool — not instructions)</summary>
          <pre className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] text-ink-2">{lines.join("\n")}</pre>
        </details>
      )}
    </div>
  );
}
