"use client";

import Link from "next/link";
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AgentStatusCard } from "@/features/agent/AgentStatusCard";
import { api, DEMO_MODE, errorMessage, type PrivacyMode, type SecurityCheck, type SecurityStatus } from "@/lib/api";
import { useUi } from "@/lib/session";
import { APPROVAL_STATUS, INTEGRATION_STATUS, PRIVACY_MODES } from "@/lib/labels";
import { fmtDateTime } from "@/lib/format";
import { Badge, Banner, Button, DefList, EmptyState, ErrorState, Icon, MonoTag, PageHeader, Skeleton, cx } from "@/components/ui";
import { AccountDeletionModal, DataExportModal } from "./AccountRequestModals";

const CHECK_META: Record<SecurityCheck["status"], { icon: string; color: string; label: string }> = {
  enforced: { icon: "circle-check", color: "#16803C", label: "Enforced" },
  partial: { icon: "circle-alert", color: "#B54708", label: "Partly in place" },
  not_configured: { icon: "circle-dashed", color: "#B54708", label: "Not configured" },
};

function Panel({ children, className, padded }: { children: ReactNode; className?: string; padded?: boolean }) {
  return <section className={cx("rounded-[10px] border border-line bg-surface", padded && "px-5 py-[18px]", className)}>{children}</section>;
}

function PanelTitle({ children, action, className }: { children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex items-center justify-between gap-3 px-5 pb-2.5 pt-4", className)}>
      <h2 className="text-[15px] font-semibold">{children}</h2>
      {action}
    </div>
  );
}

const Row = ({ children, className }: { children: ReactNode; className?: string }) => (
  <div className={cx("flex items-center gap-2.5 border-t border-line-soft px-5 py-2 text-[13.5px]", className)}>{children}</div>
);

// ------------------------------------------------------------------ privacy mode
function PrivacyModeCard({ status }: { status: SecurityStatus }) {
  const qc = useQueryClient();
  const { toast } = useUi();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.getSettings() });
  const canEdit = settings.data ? settings.data.workspace.can_edit : true;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const m = useMutation({
    mutationFn: (privacy_mode: PrivacyMode) => api.updateWorkspaceSettings({ privacy_mode }),
    onSuccess: (res) => {
      qc.setQueryData(["settings"], res);
      qc.invalidateQueries({ queryKey: ["security"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      if (res.enforced) toast("Saved.", "success");
      else if (DEMO_MODE) toast("Saved for this demo session only.", "info");
      else toast("Saved, but this server reports it is not enforced.", "info");
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const current = m.isPending && m.variables ? m.variables : status.privacy_mode;
  const pick = (v: PrivacyMode) => {
    if (!canEdit || m.isPending || v === status.privacy_mode) return;
    m.mutate(v);
  };
  const onKey = (e: KeyboardEvent, i: number) => {
    const d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = (i + d + PRIVACY_MODES.length) % PRIVACY_MODES.length;
    refs.current[n]?.focus();
    pick(PRIVACY_MODES[n].value);
  };

  return (
    <Panel padded>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold">Workspace privacy mode</h2>
        {status.privacy_enforced ? (
          <Badge meta={{ fg: "#16803C", bg: "#ECFDF3", icon: "circle-check" }}>Enforced</Badge>
        ) : (
          <span className="rounded-md bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">
            {DEMO_MODE ? "Demo — not enforced" : "Not enforced on this server"}
          </span>
        )}
      </div>
      <div role="radiogroup" aria-label="Privacy mode" aria-busy={m.isPending || undefined} className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-2.5">
        {PRIVACY_MODES.map((p, i) => {
          const on = current === p.value;
          return (
            <button
              key={p.value}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={on}
              tabIndex={on ? 0 : -1}
              disabled={!canEdit}
              onClick={() => pick(p.value)}
              onKeyDown={(e) => onKey(e, i)}
              className="flex flex-col gap-1.5 rounded-[10px] border px-4 py-3.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60"
              style={{ borderColor: on ? "#3448C5" : "#E4E7EC", background: on ? "#EEF1FC" : "#FFFFFF" }}
            >
              <span className="flex items-center gap-2 font-semibold">
                <span className="grid h-4 w-4 place-items-center rounded-full border-[1.5px] bg-white" style={{ borderColor: on ? "#3448C5" : "#E4E7EC" }}>
                  {on && (m.isPending ? <Icon name="loader" size={10} spin className="text-primary" /> : <span className="h-2 w-2 rounded-full bg-primary" />)}
                </span>
                {p.label}
              </span>
              <span className="text-[13px] text-ink-3 [text-wrap:pretty]">{p.description}</span>
            </button>
          );
        })}
      </div>
      {!canEdit && <p className="mt-3 text-[13px] text-muted">Only workspace owners and admins can change this.</p>}
    </Panel>
  );
}

// ------------------------------------------------------------------ integration permissions
function IntegrationPermissions() {
  const q = useQuery({ queryKey: ["integrations"], queryFn: () => api.listIntegrations() });
  return (
    <Panel>
      <PanelTitle>Integration permissions</PanelTitle>
      {q.isLoading ? (
        <Skeleton lines={4} className="px-5 pb-4" />
      ) : q.isError ? (
        <div className="px-5 pb-4">
          <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} title="We couldn't load integrations" />
        </div>
      ) : !q.data?.length ? (
        <EmptyState icon="plug" title="No integrations available" className="border-t border-line-soft py-8" />
      ) : (
        q.data.map((i) => (
          <Row key={i.key}>
            <Icon name={i.icon} size={15} className="text-muted" />
            <span className="flex-1">{i.name}</span>
            <Badge meta={INTEGRATION_STATUS[i.status]} />
          </Row>
        ))
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------ page
export function SecurityPage() {
  const q = useQuery({ queryKey: ["security"], queryFn: () => api.securityStatus() });
  const agent = useQuery({ queryKey: ["agent-status"], queryFn: () => api.getAgentStatus(), staleTime: 30_000 });
  const [modal, setModal] = useState<"export" | "delete" | null>(null);

  const header = <PageHeader title="Security & Privacy" subtitle="Control what the Agent can share, and see what it was stopped from doing." />;

  if (q.isLoading) {
    return (
      <div data-screen-label="Security" className="flex flex-col gap-4">
        {header}
        <Panel padded>
          <Skeleton lines={5} />
        </Panel>
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div data-screen-label="Security" className="flex flex-col gap-4">
        {header}
        <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} title="We couldn't load your security settings" />
      </div>
    );
  }

  const s = q.data;
  const enforcedN = s.checklist.filter((c) => c.status === "enforced").length;
  const incomplete = !s.privacy_enforced || enforcedN < s.checklist.length;

  return (
    <div data-screen-label="Security" className="flex flex-col gap-4">
      {header}

      {!s.privacy_enforced && (
        <div role="alert" className="flex gap-3 rounded-[10px] border border-danger-line bg-danger-soft px-4 py-3.5">
          <Icon name="shield-alert" size={18} className="mt-px text-danger" />
          <div>
            <div className="font-semibold text-danger">Security configuration incomplete</div>
            <div className="mt-0.5 text-[13.5px] text-ink-2 [text-wrap:pretty]">
              {DEMO_MODE
                ? "These are demonstration settings. They do not protect any data until a backend policy engine enforces them."
                : "This server reports the policy engine is not enforcing your privacy choices. Treat them as preferences only."}
            </div>
          </div>
        </div>
      )}

      <div role="note" className="flex gap-3 rounded-[10px] border border-primary-line bg-primary-soft px-4 py-3.5 text-[#1F2A7A]">
        <Icon name="shield-check" size={18} className="mt-px text-primary" />
        <span className="[text-wrap:pretty]">
          <strong>Uploading a file does not authorise sharing it with an external AI provider or connected app.</strong> Sharing always needs a separate approval, and files
          marked Unclassified can&apos;t be shared at all.
        </span>
      </div>

      <AgentStatusCard agent={agent.data} />

      <PrivacyModeCard status={s} />

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,360px),1fr))] gap-4">
        <Panel padded>
          <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[15px] font-semibold">External AI provider data policy</h2>
            {!s.privacy_enforced && <MonoTag>NOT ENFORCED</MonoTag>}
          </div>
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13.5px]">
            {[
              "Data reaches an external AI model only after the policy engine allows it — confidential data needs a one-time approval.",
              "Unclassified data never leaves the workspace.",
              "Known secret patterns (keys, tokens, passwords) are redacted before anything is sent; this reduces, but cannot rule out, accidental exposure.",
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <Icon name="circle-check" size={15} className="mt-0.5 text-success" />
                {t}
              </li>
            ))}
            <li className="flex gap-2">
              <Icon name="circle-help" size={15} className="mt-0.5 text-warning" />
              <span className="[text-wrap:pretty]">{s.ai_provider_policy}</span>
            </li>
          </ul>
        </Panel>

        <IntegrationPermissions />

        <Panel>
          <PanelTitle
            action={
              <Link href="/approvals?filter=decided" className="text-[13px] font-medium">
                All approvals
              </Link>
            }
          >
            Recent approval decisions
          </PanelTitle>
          {s.recent_decisions.length === 0 ? (
            <EmptyState icon="shield-check" title="No decisions yet." className="border-t border-line-soft py-8" />
          ) : (
            s.recent_decisions.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-2.5 border-t border-line-soft px-5 py-2.5">
                <span className="min-w-0 flex-[1_1_200px] text-[13.5px]">
                  <Link href={`/approvals?id=${a.id}`} className="text-ink hover:text-primary">
                    {a.title}
                  </Link>
                  <span className="block text-xs text-muted">{fmtDateTime(a.decided_at)}</span>
                </span>
                <Badge meta={APPROVAL_STATUS[a.status]} />
              </div>
            ))
          )}
        </Panel>

        <Panel>
          <PanelTitle>Recently blocked actions</PanelTitle>
          {s.blocked_actions.length === 0 ? (
            <EmptyState icon="ban" title="No blocked actions yet." className="border-t border-line-soft py-8" />
          ) : (
            s.blocked_actions.map((b) => (
              <div key={b.id} className="flex gap-2.5 border-t border-line-soft px-5 py-2.5">
                <Icon name="ban" size={15} className="mt-[3px] text-danger" />
                <div className="text-[13.5px]">
                  <div>{b.text}</div>
                  <div className="text-xs text-muted">
                    {fmtDateTime(b.created_at)} · {b.reason}
                  </div>
                </div>
              </div>
            ))
          )}
        </Panel>

        <Panel padded>
          <h2 className="mb-2.5 text-[15px] font-semibold">Data retention</h2>
          {s.retention.length ? (
            <DefList items={s.retention.map((r) => [r.label, r.value])} />
          ) : (
            <p className="text-[13.5px] text-muted">No retention rules are configured yet.</p>
          )}
          <div className="mt-3.5 flex flex-wrap gap-2">
            <Button size="sm" className="text-[13px]" onClick={() => setModal("export")}>
              Request data export
            </Button>
            <Button size="sm" variant="danger" className="text-[13px]" onClick={() => setModal("delete")}>
              Request account deletion
            </Button>
          </div>
        </Panel>

        <Panel>
          <h2 className="px-5 pb-1 pt-4 text-[15px] font-semibold">Security configuration checklist</h2>
          <p className="px-5 pb-2.5 text-[12.5px] text-muted">
            {enforcedN === 0
              ? "None of these items is enforced on this server."
              : enforcedN === s.checklist.length
                ? "Every listed item is enforced. That still isn’t a guarantee of complete security."
                : `${enforcedN} of ${s.checklist.length} enforced. Items marked partial or not configured are listed honestly below.`}
          </p>
          {s.checklist.map((c) => {
            const meta = CHECK_META[c.status];
            return (
              <Row key={c.key} className="items-start">
                <Icon name={meta.icon} size={15} className="mt-0.5" style={{ color: meta.color }} />
                <span className="min-w-0 flex-1">
                  {c.label}
                  {c.detail && <span className="block text-xs text-muted [text-wrap:pretty]">{c.detail}</span>}
                </span>
                <span className="whitespace-nowrap text-[11.5px]" style={{ color: meta.color }}>
                  {meta.label}
                </span>
              </Row>
            );
          })}
        </Panel>
      </div>

      {modal === "export" && <DataExportModal onClose={() => setModal(null)} />}
      {modal === "delete" && <AccountDeletionModal onClose={() => setModal(null)} />}
    </div>
  );
}
