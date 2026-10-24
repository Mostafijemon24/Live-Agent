"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { Approval } from "@/lib/api";
import { APPROVAL_CATEGORY, APPROVAL_STATUS, RISK_LEVEL, TONE } from "@/lib/labels";
import { fmtDateTime, fmtExpires } from "@/lib/format";
import { Badge, Button, Icon } from "@/components/ui";
import type { DecisionKind } from "./DecisionModal";

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{k}</dt>
      <dd className="m-0 min-w-0 [text-wrap:pretty]">{children}</dd>
    </>
  );
}

/** Right-hand detail panel of the Approvals screen (prototype `ap`). */
export function ApprovalDetail({ ap, onDecide }: { ap: Approval; onDecide: (k: DecisionKind) => void }) {
  const cat = APPROVAL_CATEGORY[ap.category];
  const tone = TONE[cat.tone];
  const risk = RISK_LEVEL[ap.risk];
  const status = APPROVAL_STATUS[ap.status];
  const pending = ap.status === "pending";

  return (
    <article aria-labelledby="ap-title" className="w-full min-w-0 overflow-hidden rounded-[10px] border border-line bg-surface">
      <div className="border-b border-line px-5 py-[18px]">
        <div className="font-mono text-[12.5px] text-muted">
          {ap.ref} · {cat.label}
        </div>
        <h2 id="ap-title" className="mt-1 text-[19px] font-semibold tracking-[-.01em] [text-wrap:balance]">
          {ap.title}
        </h2>
      </div>

      <div className="mx-5 mt-4 flex gap-3 rounded-[10px] border px-4 py-3.5" style={{ background: tone.bg, borderColor: tone.border }}>
        <Icon name={cat.icon} size={18} className="mt-px" style={{ color: tone.fg }} />
        <div>
          <div className="font-semibold" style={{ color: tone.fg }}>
            {cat.head}
          </div>
          <div className="mt-0.5 text-[13.5px] text-ink-2 [text-wrap:pretty]">{cat.body}</div>
        </div>
      </div>

      <dl className="m-0 grid grid-cols-[minmax(120px,170px)_minmax(0,1fr)] gap-x-4 gap-y-3 px-5 py-4 text-[13.5px] max-[520px]:grid-cols-1 max-[520px]:gap-y-1 max-[520px]:[&>dd]:mb-2">
        <Row k="Requested action">
          <span className="font-medium">{ap.title}</span>
        </Row>
        <Row k="Why it's needed">{ap.reason}</Row>
        <Row k="Affected items">
          <div className="mb-1 text-[12.5px] text-muted">{ap.scope_summary}</div>
          {ap.affected_items.length > 0 ? (
            <ul className="m-0 list-none rounded-lg border border-line p-0">
              {ap.affected_items.map((x, i) => (
                <li
                  key={`${x}-${i}`}
                  className="flex items-center gap-2 border-b border-line-soft px-2.5 py-[7px] font-mono text-[12.5px] last:border-b-0 [overflow-wrap:anywhere]"
                >
                  <Icon name="file" size={13} className="text-faint" />
                  {x}
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-muted">No items listed</span>
          )}
        </Row>
        <Row k="Data leaves workspace?">
          <span className="flex items-center gap-1.5 font-medium" style={{ color: ap.data_leaves_workspace ? "#B42318" : "#16803C" }}>
            <Icon name={ap.data_leaves_workspace ? "send" : "shield-check"} size={14} />
            {ap.data_leaves_workspace ? "Yes — data leaves the workspace" : "No — stays within your own systems"}
          </span>
        </Row>
        <Row k="Destination">{ap.destination}</Row>
        <Row k="Expected consequences">{ap.consequences}</Row>
        <Row k="Reversible?">{ap.reversible}</Row>
        <Row k="Risk">
          <span className="font-medium" style={{ color: risk.color }}>
            {risk.label} risk
          </span>
        </Row>
        <Row k="Expires">{pending ? fmtExpires(ap.expires_at) : ap.expires_at ? fmtDateTime(ap.expires_at) : "—"}</Row>
        <Row k="Requested">
          {fmtDateTime(ap.requested_at)}
          {ap.task_id && (
            <>
              {" · "}
              <Link href={`/tasks/${ap.task_id}?tab=approvals`} className="font-mono">
                {ap.task_ref ?? "Open task"}
              </Link>
            </>
          )}
        </Row>
      </dl>

      {pending ? (
        <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-subtle px-5 py-3.5">
          <Button size="md" className="text-[13.5px]" onClick={() => onDecide("changes")}>
            Request changes
          </Button>
          <Button variant="danger" size="md" className="text-[13.5px]" onClick={() => onDecide("reject")}>
            Reject
          </Button>
          <Button variant="primary" size="md" icon="check" className="gap-1.5 px-4 text-[13.5px]" onClick={() => onDecide("approve")}>
            Approve once
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2.5 border-t border-line bg-subtle px-5 py-3.5">
          <Badge meta={status} />
          <span className="text-[13px] text-muted">{ap.decided_at ? `Decided · ${fmtDateTime(ap.decided_at)}` : status.label}</span>
          {ap.decision_note && <span className="basis-full text-[13px] text-ink-2">Note: {ap.decision_note}</span>}
          {ap.execution_state === "blocked_until_phase3" && (
            <span className="flex basis-full items-start gap-1.5 text-[12.5px] text-muted">
              <Icon name="info" size={14} className="mt-0.5 text-primary" />
              Execution blocked until the execution engine and policy checks are installed (Phase 3).
            </span>
          )}
        </div>
      )}
    </article>
  );
}
