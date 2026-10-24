"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, DEMO_MODE, type TaskListQuery, type TaskStatus, type TaskSummary, type TaskType } from "@/lib/api";
import { TASK_NEXT, TASK_STATUS, TASK_STATUSES, TASK_TYPES, TASK_TYPE_ICON, TASK_TYPE_LABEL } from "@/lib/labels";
import { fmtDateTime } from "@/lib/format";
import { useUi } from "@/lib/session";
import { EmptyState, ErrorState, Icon, Skeleton, cx } from "@/components/ui";
import { INTEGRATION_OPTIONS, LinkButton, StatusBadge, taskHref, waitingLabel } from "./shared";

const PAGE_SIZE = 8;

const DATE_OPTIONS: { value: "" | "today" | "3d"; label: string }[] = [
  { value: "", label: "Any time" },
  { value: "today", label: "Today" },
  { value: "3d", label: "Last 3 days" },
];
const SORT_OPTIONS: { value: NonNullable<TaskListQuery["sort"]>; label: string }[] = [
  { value: "updated", label: "Last updated" },
  { value: "created", label: "Date created" },
  { value: "title", label: "Title (A–Z)" },
];

/** Reads and validates the filters from the URL so links like /tasks?status=running and /tasks?q= work. */
function parseQuery(sp: URLSearchParams): Required<Pick<TaskListQuery, "page" | "page_size" | "sort">> & TaskListQuery {
  const status = sp.get("status");
  const type = sp.get("type");
  const created = sp.get("created");
  const integration = sp.get("integration");
  const sort = sp.get("sort");
  const page = Number.parseInt(sp.get("page") ?? "1", 10);
  const q = (sp.get("q") ?? "").trim();
  return {
    ...(q ? { q } : {}),
    ...(status && (TASK_STATUSES as string[]).includes(status) ? { status: status as TaskStatus } : {}),
    ...(type && TASK_TYPES.some((t) => t.value === type) ? { type: type as TaskType } : {}),
    ...(created === "today" || created === "3d" ? { created } : {}),
    ...(integration && INTEGRATION_OPTIONS.some((o) => o.value && o.value === integration) ? { integration } : {}),
    sort: SORT_OPTIONS.some((o) => o.value === sort) ? (sort as NonNullable<TaskListQuery["sort"]>) : "updated",
    page: Number.isFinite(page) && page >= 1 ? page : 1,
    page_size: PAGE_SIZE,
  };
}

const selectCls = "h-9 rounded-lg border border-line-strong bg-surface px-2 text-[13.5px]";

export function TasksList() {
  const router = useRouter();
  const pathname = usePathname() ?? "/tasks";
  const sp = useSearchParams();
  const { compactRows } = useUi();
  const query = parseQuery(new URLSearchParams(sp?.toString() ?? ""));
  const urlQ = query.q ?? "";

  // Search box: local while typing, pushed to the URL after a short pause. Re-syncs when
  // the URL changes from elsewhere (e.g. the header search).
  const [qInput, setQInput] = useState(urlQ);
  const [syncedQ, setSyncedQ] = useState(urlQ);
  if (syncedQ !== urlQ) {
    setSyncedQ(urlQ);
    setQInput(urlQ);
  }

  const setParams = (patch: Record<string, string | number | undefined>, resetPage = true) => {
    const next = new URLSearchParams(sp?.toString() ?? "");
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined || v === "" || (k === "sort" && v === "updated") || (k === "page" && v === 1)) next.delete(k);
      else next.set(k, String(v));
    }
    if (resetPage && !("page" in patch)) next.delete("page");
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  useEffect(() => {
    if (qInput.trim() === urlQ) return;
    const t = setTimeout(() => {
      const next = new URLSearchParams(window.location.search);
      if (qInput.trim()) next.set("q", qInput.trim());
      else next.delete("q");
      next.delete("page");
      const s = next.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    }, 300);
    return () => clearTimeout(t);
  }, [qInput, urlQ, pathname, router]);

  const { data, error, isLoading, isFetching, refetch, isPlaceholderData } = useQuery({
    queryKey: ["tasks", query],
    queryFn: () => api.listTasks(query),
    placeholderData: keepPreviousData,
  });

  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = query.page;

  // Out-of-range page (e.g. after filtering or a stale link): go to the last real page.
  useEffect(() => {
    if (data && !isPlaceholderData && total > 0 && page > pages) {
      const next = new URLSearchParams(window.location.search);
      if (pages === 1) next.delete("page");
      else next.set("page", String(pages));
      const s = next.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    }
  }, [data, isPlaceholderData, total, page, pages, pathname, router]);

  const filtersOn = !!(query.q || query.status || query.type || query.created || query.integration);
  const clear = () => {
    setQInput("");
    const next = new URLSearchParams();
    if (query.sort !== "updated") next.set("sort", query.sort);
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  const rows = data?.items ?? [];
  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);
  const rowPad = compactRows ? "px-4 py-2" : "px-4 py-3";

  let body: ReactNode;
  if (isLoading && !data) {
    body = (
      <div className="rounded-[10px] border border-line bg-surface p-5">
        <Skeleton lines={6} />
      </div>
    );
  } else if (error && !data) {
    body = <ErrorState error={error} onRetry={() => refetch()} retrying={isFetching} title="We couldn't load your tasks" />;
  } else if (rows.length === 0 && filtersOn) {
    body = (
      <div className="flex flex-col items-center gap-2 rounded-[10px] border border-line bg-surface px-6 py-12 text-center">
        <span className="grid h-11 w-11 place-items-center rounded-[10px] bg-line-soft">
          <Icon name="search-x" size={20} className="text-muted" />
        </span>
        <div className="font-semibold">No tasks match these filters</div>
        <div className="text-[13.5px] text-muted">Try a different search or clear the filters.</div>
        <button
          type="button"
          onClick={clear}
          className="mt-1.5 h-9 rounded-lg border border-line-strong bg-surface px-3.5 text-[13.5px] font-medium hover:bg-subtle"
        >
          Clear filters
        </button>
      </div>
    );
  } else if (rows.length === 0) {
    body = (
      <div className="rounded-[10px] border border-line bg-surface">
        <EmptyState
          icon="list-checks"
          title="No tasks yet"
          action={
            <LinkButton href="/tasks/new" variant="primary" icon="plus" className="h-[38px] px-3.5 text-sm">
              Create task
            </LinkButton>
          }
        >
          Describe what you need in plain language. The Agent prepares a plan and nothing happens without your approval.
        </EmptyState>
      </div>
    );
  } else {
    body = (
      <div aria-busy={isFetching || undefined} className={cx("flex flex-col gap-4 transition-opacity", isPlaceholderData && "opacity-60")}>
        {error && (
          <div role="alert" className="text-[13px] text-danger">
            Couldn&apos;t refresh the list. Showing the last results we loaded.
          </div>
        )}
        <DesktopTable rows={rows} rowPad={rowPad} onOpen={(t) => router.push(taskHref(t))} />
        <MobileCards rows={rows} />
        <div className="flex flex-wrap items-center justify-between gap-3 text-[13px] text-muted">
          <span>{total ? `Showing ${from}–${to} of ${total}` : "No results"}</span>
          <div className="flex items-center gap-2">
            <PagerButton label="Previous page" icon="chevron-left" disabled={page <= 1} onClick={() => setParams({ page: Math.max(1, page - 1) }, false)} />
            <span>
              Page {Math.min(page, pages)} of {pages}
            </span>
            <PagerButton label="Next page" icon="chevron-right" disabled={page >= pages} onClick={() => setParams({ page: Math.min(pages, page + 1) }, false)} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-[-.015em]">Tasks</h1>
          <p className="mt-1 text-muted">
            Everything the Agent has planned, run or is waiting on.{DEMO_MODE ? " Sample tasks." : ""}
          </p>
        </div>
        <LinkButton href="/tasks/new" variant="primary" icon="plus" className="h-[38px] px-3.5 text-sm">
          Create task
        </LinkButton>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-[10px] border border-line bg-surface p-3">
        <div className="relative min-w-0 flex-[1_1_220px]">
          <Icon name="search" size={15} className="absolute left-[11px] top-[11px] text-faint" />
          <input
            type="search"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            aria-label="Search tasks"
            placeholder="Search by title or ID"
            className="h-9 w-full rounded-lg border border-line-strong bg-surface pl-[34px] pr-3 text-sm placeholder:text-faint"
          />
        </div>
        <select aria-label="Status" value={query.status ?? ""} onChange={(e) => setParams({ status: e.target.value })} className={selectCls}>
          <option value="">All statuses</option>
          {TASK_STATUSES.map((s) => (
            <option key={s} value={s}>
              {TASK_STATUS[s].label}
            </option>
          ))}
        </select>
        <select aria-label="Type" value={query.type ?? ""} onChange={(e) => setParams({ type: e.target.value })} className={selectCls}>
          <option value="">All types</option>
          {TASK_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <select aria-label="Date" value={query.created ?? ""} onChange={(e) => setParams({ created: e.target.value })} className={selectCls}>
          {DATE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select aria-label="Integration" value={query.integration ?? ""} onChange={(e) => setParams({ integration: e.target.value })} className={selectCls}>
          {INTEGRATION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select aria-label="Sort" value={query.sort} onChange={(e) => setParams({ sort: e.target.value })} className={selectCls}>
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {filtersOn && (
          <button type="button" onClick={clear} className="h-9 border-0 bg-transparent px-2.5 text-[13.5px] font-medium text-primary hover:underline">
            Clear filters
          </button>
        )}
      </div>

      {body}
    </div>
  );
}

function NextAction({ t, arrow }: { t: TaskSummary; arrow?: boolean }) {
  const waiting = waitingLabel(t.waiting_for);
  if (waiting) {
    return (
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] text-muted">
        <Icon name="hourglass" size={13} />
        {waiting}
      </span>
    );
  }
  return (
    <span className="whitespace-nowrap text-[13.5px] font-medium text-primary">
      {TASK_NEXT[t.status]}
      {arrow ? " →" : ""}
    </span>
  );
}

function DesktopTable({ rows, rowPad, onOpen }: { rows: TaskSummary[]; rowPad: string; onOpen: (t: TaskSummary) => void }) {
  const th = "border-b border-line px-4 py-2.5 font-medium";
  return (
    <div className="overflow-hidden rounded-[10px] border border-line bg-surface max-[979px]:hidden">
      <table className="w-full border-collapse text-[13.5px]">
        <thead>
          <tr className="bg-subtle text-left text-[12.5px] text-ink-3">
            <th scope="col" className={th}>Task</th>
            <th scope="col" className={th}>Status</th>
            <th scope="col" className={th}>Type</th>
            <th scope="col" className={th}>Created</th>
            <th scope="col" className={th}>Updated</th>
            <th scope="col" className={th}>Next action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id} onClick={() => onOpen(t)} className="cursor-pointer border-b border-line-soft last:border-b-0 hover:bg-subtle">
              <td className={cx(rowPad, "max-w-[340px]")}>
                <Link
                  href={taskHref(t)}
                  onClick={(e) => e.stopPropagation()}
                  className="block truncate font-medium text-ink hover:text-ink hover:underline"
                >
                  {t.title}
                </Link>
                <div className="flex items-center gap-2 text-xs text-muted">
                  <span className="font-mono">{t.ref}</span>
                  {t.priority === "high" && <span className="font-medium text-warning">High priority</span>}
                </div>
              </td>
              <td className={rowPad}>
                <StatusBadge status={t.status} />
              </td>
              <td className={cx(rowPad, "whitespace-nowrap text-ink-3")}>
                <span className="inline-flex items-center gap-1.5">
                  <Icon name={TASK_TYPE_ICON[t.type]} size={14} className="text-faint" />
                  {TASK_TYPE_LABEL[t.type]}
                </span>
              </td>
              <td className={cx(rowPad, "whitespace-nowrap text-ink-3")}>{fmtDateTime(t.created_at)}</td>
              <td className={cx(rowPad, "whitespace-nowrap text-ink-3")}>{fmtDateTime(t.updated_at)}</td>
              <td className={rowPad}>
                <NextAction t={t} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileCards({ rows }: { rows: TaskSummary[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0 min-[980px]:hidden">
      {rows.map((t) => (
        <li key={t.id}>
          <Link
            href={taskHref(t)}
            className="flex flex-col gap-2 rounded-[10px] border border-line bg-surface p-3.5 text-left text-ink hover:border-line-strong hover:text-ink hover:no-underline"
          >
            <span className="flex items-start justify-between gap-2">
              <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{t.title}</span>
              <StatusBadge status={t.status} />
            </span>
            <span className="text-[12.5px] text-muted">
              <span className="font-mono">{t.ref}</span> · {TASK_TYPE_LABEL[t.type]} · Updated {fmtDateTime(t.updated_at)}
              {t.priority === "high" && <span className="font-medium text-warning"> · High priority</span>}
            </span>
            <span className="text-[13px]">
              <NextAction t={t} arrow />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function PagerButton({ label, icon, disabled, onClick }: { label: string; icon: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-8 place-items-center rounded-lg border border-line-strong bg-surface px-2.5 text-ink disabled:opacity-50"
    >
      <Icon name={icon} size={15} />
    </button>
  );
}
