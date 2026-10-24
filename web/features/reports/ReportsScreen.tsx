"use client";

import { useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, DEMO_MODE, type ActivityType, type Artifact, type Task } from "@/lib/api";
import { ACTIVITY_ICON, ACTIVITY_LABEL, TASK_STATUS } from "@/lib/labels";
import { fmtDateTime } from "@/lib/format";
import { useUi } from "@/lib/session";
import { Badge, Button, EmptyState, ErrorState, Icon, PageHeader, Skeleton } from "@/components/ui";

const EXPORT_BODY =
  "Exports are generated on the server and checked for confidential content first. Logs are redacted of tokens, passwords and personal data. Report export arrives in Phase 3.";

type Filter = ActivityType | "all";
const FILTERS: { k: Filter; label: string }[] = [
  { k: "all", label: "All" },
  ...(Object.keys(ACTIVITY_LABEL) as ActivityType[]).map((k) => ({ k, label: ACTIVITY_LABEL[k] })),
];

const PROVENANCE: Record<Artifact["provenance"], { label: string; fg: string; bg: string; icon: string }> = {
  ai_generated: { label: "AI-generated", fg: "#B54708", bg: "#FFF6ED", icon: "sparkles" },
  verified_result: { label: "Verified result", fg: "#16803C", bg: "#ECFDF3", icon: "circle-check" },
};

function ReportCard({ t }: { t: Task }) {
  const r = t.report!;
  return (
    <article className="flex flex-col gap-2.5 rounded-[10px] border border-line bg-surface px-[18px] py-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold break-words">{t.title}</div>
          <div className="text-xs text-muted">
            <span className="font-mono">{t.ref}</span> · {fmtDateTime(t.updated_at)}
          </div>
        </div>
        <Badge meta={TASK_STATUS[t.status]} className="gap-[5px]" />
      </div>
      <div className="text-[13.5px] [text-wrap:pretty]">{r.summary}</div>
      {r.open_issues && (
        <div className="flex gap-1.5 text-[13px] text-warning">
          <Icon name="circle-alert" size={13} className="mt-[3px]" />
          <span>{r.open_issues}</span>
        </div>
      )}
      <div className="mt-auto flex items-center justify-between gap-2">
        <span className="rounded-[5px] bg-warning-soft px-[7px] py-px text-[11.5px] font-medium text-warning">
          AI-generated summary{DEMO_MODE ? " · sample" : ""}
        </span>
        <Link href={`/tasks/${t.id}?tab=artifacts`} className="text-[13px] font-medium" aria-label={`Open report for ${t.ref}`}>
          Open
        </Link>
      </div>
    </article>
  );
}

function ReportsSection() {
  const q = useQuery({ queryKey: ["reports"], queryFn: () => api.listReports() });
  const reports = (q.data?.reports ?? []).filter((t) => t.report);
  const artifacts = q.data?.artifacts ?? [];

  return (
    <>
      <section aria-labelledby="reports-h">
        <h2 id="reports-h" className="mb-2.5 text-[15px] font-semibold">
          Task reports
        </h2>
        {q.isLoading ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,320px),1fr))] gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-[10px] border border-line bg-surface px-[18px] py-4">
                <Skeleton lines={4} />
              </div>
            ))}
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
        ) : reports.length === 0 ? (
          <div className="rounded-[10px] border border-line bg-surface">
            <EmptyState icon="file-text" title="No reports yet">
              {DEMO_MODE ? "Reports appear here when tasks finish." : "Reports appear here when the execution engine (Phase 3) finishes tasks."}
            </EmptyState>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,320px),1fr))] gap-3">
            {reports.map((t) => (
              <ReportCard key={t.id} t={t} />
            ))}
          </div>
        )}
      </section>

      {artifacts.length > 0 && (
        <section aria-labelledby="artifacts-h" className="rounded-[10px] border border-line bg-surface">
          <h2 id="artifacts-h" className="border-b border-line px-[18px] py-3.5 text-[15px] font-semibold">
            Artifacts
          </h2>
          <ul className="m-0 list-none p-0">
            {artifacts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 border-b border-line-soft px-4 py-3 last:border-b-0">
                <Icon name="file-text" size={15} className="text-ink-3" />
                <div className="min-w-0 flex-[1_1_240px]">
                  <div className="text-[13.5px] font-medium break-words">{a.name}</div>
                  <div className="text-xs text-muted">
                    {a.kind} · {fmtDateTime(a.created_at)}
                  </div>
                </div>
                <Badge meta={PROVENANCE[a.provenance]} className="gap-[5px]" />
                {a.task_id && a.task_ref && (
                  <Link href={`/tasks/${a.task_id}?tab=artifacts`} className="font-mono text-[12.5px]">
                    {a.task_ref}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function ActivityLog() {
  const { compactRows } = useUi();
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(1);
  const type = filter === "all" ? undefined : filter;
  const q = useQuery({
    queryKey: ["activity", type, page],
    queryFn: () => api.listActivity(type, page),
    placeholderData: keepPreviousData,
  });
  const rows = q.data?.items ?? [];
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / Math.max(1, q.data.page_size))) : 1;
  const pad = compactRows ? "py-2 px-4" : "py-3 px-4";

  return (
    <section aria-labelledby="activity-h" className="rounded-[10px] border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-[18px] py-3.5">
        <h2 id="activity-h" className="text-[15px] font-semibold">
          Activity log
        </h2>
        <div role="group" aria-label="Filter by event type" className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => {
            const on = filter === f.k;
            return (
              <button
                key={f.k}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setFilter(f.k);
                  setPage(1);
                }}
                className="h-7 rounded-[7px] border px-2.5 text-[12.5px] font-medium"
                style={{ background: on ? "#EEF1FC" : "#FFFFFF", borderColor: on ? "#3448C5" : "#E4E7EC", color: on ? "#3448C5" : "#344054" }}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </div>

      {q.isLoading ? (
        <div className="p-[18px]">
          <Skeleton lines={6} />
        </div>
      ) : q.isError && !q.data ? (
        <div className="p-4">
          <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
        </div>
      ) : rows.length === 0 ? (
        <div className="p-8 text-center text-muted">{filter === "all" ? "No activity yet." : "No events of this type."}</div>
      ) : (
        <ul className={`m-0 list-none p-0 transition-opacity ${q.isPlaceholderData ? "opacity-60" : ""}`} aria-busy={q.isFetching || undefined}>
          {rows.map((a) => (
            <li key={a.id} className={`flex flex-wrap items-center gap-3 border-b border-line-soft ${pad}`}>
              <span className="w-24 shrink-0 font-mono text-[12.5px] text-muted">{fmtDateTime(a.created_at)}</span>
              <span className="inline-flex w-24 shrink-0 items-center gap-1.5 text-xs text-ink-3">
                <Icon name={ACTIVITY_ICON[a.type] ?? "activity"} size={13} />
                {ACTIVITY_LABEL[a.type] ?? a.type}
              </span>
              <span className="min-w-0 flex-[1_1_240px] text-[13.5px] break-words">{a.message}</span>
              {a.task_id && (
                <Link href={`/tasks/${a.task_id}?tab=audit`} className="font-mono text-[12.5px]">
                  {a.task_ref ?? "Task"}
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {q.data && q.data.total > q.data.page_size && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
          <span className="text-[13px] text-muted">
            Page {page} of {pages} · {q.data.total} events
          </span>
          <div className="flex gap-2">
            <Button size="xs" icon="chevron-left" disabled={page <= 1 || q.isFetching} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Previous
            </Button>
            <Button size="xs" iconRight="chevron-right" disabled={page >= pages || q.isFetching} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
      {q.isError && q.data && (
        <div role="alert" className="border-t border-line-soft px-4 py-2.5 text-[13px] text-danger">
          Couldn&apos;t load that page. Showing the previous one.{" "}
          <button type="button" onClick={() => q.refetch()} className="border-0 bg-transparent p-0 font-medium text-primary hover:underline">
            Try again
          </button>
        </div>
      )}
    </section>
  );
}

export function ReportsScreen() {
  const { notice } = useUi();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Reports & Activity"
        subtitle="Task results and a full log of what happened. Times shown in your browser's time zone."
        actions={
          <Button icon="download" onClick={() => notice("Export needs the backend", EXPORT_BODY)}>
            Export
          </Button>
        }
      />
      <ReportsSection />
      <ActivityLog />
    </div>
  );
}
