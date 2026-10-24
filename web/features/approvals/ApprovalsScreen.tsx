"use client";

import { useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, DEMO_MODE, type Approval } from "@/lib/api";
import { APPROVAL_CATEGORY, APPROVAL_STATUS, RISK_LEVEL } from "@/lib/labels";
import { ErrorState, Icon, PageHeader, Skeleton } from "@/components/ui";
import { ApprovalDetail } from "./ApprovalDetail";
import { DecisionModal, type DecisionKind } from "./DecisionModal";

type Filter = "pending" | "decided" | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "pending", label: "Pending" },
  { key: "decided", label: "Decided" },
  { key: "all", label: "All" },
];

const EMPTY: Record<Filter, { icon: string; color: string; title: string; body: string }> = {
  pending: { icon: "circle-check", color: "#16803C", title: "You're all caught up", body: "No approvals are waiting for you." },
  decided: { icon: "history", color: "#667085", title: "No decisions yet", body: "Approvals you approve, reject or send back appear here." },
  all: {
    icon: "shield-check",
    color: "#667085",
    title: "No approvals yet",
    body: "When a task needs to do something sensitive, it asks here first.",
  },
};

function parseFilter(v: string | null): Filter {
  return v === "decided" || v === "all" ? v : "pending";
}

function matchesFilter(a: Approval, f: Filter) {
  return f === "all" || (f === "pending" ? a.status === "pending" : a.status !== "pending");
}

export function ApprovalsScreen() {
  const router = useRouter();
  const pathname = usePathname() ?? "/approvals";
  const params = useSearchParams();
  const filter = parseFilter(params.get("filter"));
  const selId = params.get("id");
  const detailRef = useRef<HTMLDivElement>(null);
  const [modal, setModal] = useState<{ kind: DecisionKind; approval: Approval } | null>(null);

  const setParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const list = useQuery({
    queryKey: ["approvals", filter],
    queryFn: () => api.listApprovals(filter),
    placeholderData: keepPreviousData,
  });
  const items = list.data?.items ?? [];
  const inList = selId ? items.find((a) => a.id === selId) : undefined;

  // Deep links (e.g. from a task or a file deletion) may point at an approval outside the loaded page.
  const single = useQuery({
    queryKey: ["approval", selId],
    queryFn: () => api.getApproval(selId as string),
    enabled: !!selId && !!list.data && !inList,
  });

  const fetched = single.data && matchesFilter(single.data, filter) ? single.data : undefined;
  const selected = inList ?? fetched ?? items[0] ?? null;
  const pendingCount = list.data?.pending_count;

  const select = (id: string) => {
    setParams({ id });
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 979px)").matches) {
      detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div data-screen-label="Approvals" className="flex flex-col gap-4">
      <PageHeader
        title="Approvals"
        subtitle="Sensitive actions wait here until you decide. Each approval covers one exact action."
        actions={
          <div role="tablist" aria-label="Filter approvals" className="flex gap-1.5">
            {FILTERS.map((f) => {
              const on = f.key === filter;
              return (
                <button
                  key={f.key}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => setParams({ filter: f.key, id: null })}
                  className="h-8 rounded-lg border px-3 text-[13px] font-medium"
                  style={{ background: on ? "#EEF1FC" : "#FFFFFF", borderColor: on ? "#3448C5" : "#E4E7EC", color: on ? "#3448C5" : "#344054" }}
                >
                  {f.key === "pending" && pendingCount !== undefined ? `Pending (${pendingCount})` : f.label}
                </button>
              );
            })}
          </div>
        }
      />

      <div className="flex gap-2 rounded-[10px] border border-warning-line bg-warning-soft px-3.5 py-2.5 text-[13px] text-[#93370D]">
        <Icon name={DEMO_MODE ? "flask-conical" : "server"} size={15} className="mt-0.5" />
        <span>
          {DEMO_MODE
            ? "Demo: decisions only change status here. No action is executed and nothing is sent anywhere."
            : "Decisions are saved and logged. No action is executed yet — the execution engine and policy checks arrive in Phase 3."}
        </span>
      </div>

      {list.isLoading ? (
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex min-w-0 max-w-full flex-[1_1_300px] flex-col gap-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-[10px] border border-line bg-surface p-3.5">
                <Skeleton lines={2} />
              </div>
            ))}
          </div>
          <div className="min-w-0 flex-[999_1_460px] rounded-[10px] border border-line bg-surface p-5">
            <Skeleton lines={6} />
          </div>
        </div>
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} retrying={list.isFetching} title="We couldn't load approvals" />
      ) : items.length === 0 ? (
        <div className="rounded-[10px] border border-line bg-surface px-6 py-12 text-center">
          <Icon name={EMPTY[filter].icon} size={24} className="mx-auto" style={{ color: EMPTY[filter].color }} />
          <div className="mt-2 font-semibold">{EMPTY[filter].title}</div>
          <div className="text-[13.5px] text-muted">{EMPTY[filter].body}</div>
        </div>
      ) : (
        <div className="flex flex-wrap items-start gap-4">
          <div role="list" aria-label="Approvals" className="flex min-w-0 max-w-full flex-[1_1_300px] flex-col gap-2">
            {items.map((a) => {
              const active = selected?.id === a.id;
              const cat = APPROVAL_CATEGORY[a.category];
              const risk = RISK_LEVEL[a.risk];
              const st = APPROVAL_STATUS[a.status];
              return (
                <button
                  key={a.id}
                  type="button"
                  role="listitem"
                  aria-current={active || undefined}
                  onClick={() => select(a.id)}
                  className="flex items-start gap-3 rounded-[10px] border p-3.5 text-left"
                  style={{ background: active ? "#EEF1FC" : "#FFFFFF", borderColor: active ? "#C7D0F5" : "#E4E7EC" }}
                >
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-surface">
                    <Icon name={cat.icon} size={15} style={{ color: risk.color }} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-medium [text-wrap:pretty]">{a.title}</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {cat.label} · <span className="font-medium" style={{ color: risk.color }}>{risk.label} risk</span>
                    </span>
                    <span
                      className="mt-1.5 inline-flex items-center gap-[5px] rounded-[5px] px-[7px] py-px text-[11.5px] font-medium"
                      style={{ color: st.fg, background: st.bg }}
                    >
                      <Icon name={st.icon} size={12} />
                      {st.label}
                    </span>
                  </span>
                </button>
              );
            })}
            {list.data && list.data.total > items.length && (
              <p className="px-1 text-xs text-muted">
                Showing the {items.length} most recent of {list.data.total}.
              </p>
            )}
          </div>

          <div ref={detailRef} className="flex min-w-0 flex-[999_1_460px] scroll-mt-4">
            {selected && <ApprovalDetail ap={selected} onDecide={(kind) => setModal({ kind, approval: selected })} />}
          </div>
        </div>
      )}

      {modal && <DecisionModal approval={modal.approval} kind={modal.kind} onClose={() => setModal(null)} />}
    </div>
  );
}
