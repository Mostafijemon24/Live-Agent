"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, type NotificationItem } from "@/lib/api";
import { useUi } from "@/lib/session";
import { fmtRelativeDay } from "@/lib/format";
import { Button, Chip, EmptyState, ErrorState, Icon, Skeleton } from "@/components/ui";

type Filter = "all" | "unread";

/**
 * Where a notification leads. `target.route` is a complete in-app path
 * (e.g. "/tasks/<id>/plan", "/approvals?id=<id>"). Anything that isn't a
 * same-origin path (protocol-relative "//…", absolute URLs) falls back to the overview.
 */
export function notificationHref(target: NotificationItem["target"]): string {
  const r = target?.route;
  if (r && r.startsWith("/") && !r.startsWith("//") && !r.startsWith("/\\")) return r;
  return "/overview";
}

export function NotificationsPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const qc = useQueryClient();
  const router = useRouter();
  const { toast } = useUi();
  const q = useQuery({ queryKey: ["notifications", filter], queryFn: () => api.listNotifications(filter === "unread") });
  const unread = q.data?.unread ?? 0;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["notifications"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const markAll = useMutation({
    mutationFn: () => api.markAllNotificationsRead(),
    onSuccess: () => {
      invalidate();
      toast("All notifications marked as read.", "success");
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const [opening, setOpening] = useState<string | null>(null);
  const open = async (n: NotificationItem) => {
    if (n.unread) {
      setOpening(n.id);
      try {
        await api.markNotificationRead(n.id);
        invalidate();
      } catch (e) {
        // The link still works; only the read marker failed — say so.
        toast(errorMessage(e), "danger");
      } finally {
        setOpening(null);
      }
    }
    router.push(notificationHref(n.target));
  };

  const chips: { k: Filter; label: string }[] = [
    { k: "all", label: "All" },
    { k: "unread", label: `Unread (${unread})` },
  ];

  return (
    <div data-screen-label="Notifications" className="flex max-w-[820px] flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-[-.015em]">Notifications</h1>
          <p className="mt-1 text-muted">{DEMO_MODE ? "Sample notifications." : "Updates about your tasks, approvals and security."}</p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter notifications">
          {chips.map((c) => (
            <Chip key={c.k} on={filter === c.k} onClick={() => setFilter(c.k)} className="h-8 px-3 text-[13px] font-medium">
              {c.label}
            </Chip>
          ))}
          <Button variant="link" className="h-8 px-3 text-[13px]" loading={markAll.isPending} disabled={unread === 0 || !q.data} onClick={() => markAll.mutate()}>
            Mark all as read
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-[10px] border border-line bg-surface">
        {q.isLoading ? (
          <Skeleton lines={5} className="p-[18px]" />
        ) : q.isError || !q.data ? (
          <div className="p-3">
            <ErrorState error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} title="We couldn't load notifications" />
          </div>
        ) : q.data.items.length === 0 ? (
          <EmptyState icon="bell-off" title={filter === "unread" ? "No unread notifications." : "No notifications yet."}>
            {filter === "all" ? "You'll see approval requests, finished tasks and security alerts here." : undefined}
          </EmptyState>
        ) : (
          <ul className="m-0 list-none p-0">
            {q.data.items.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => open(n)}
                  disabled={opening === n.id}
                  className="flex w-full items-start gap-3 border-0 border-b border-line-soft px-[18px] py-3.5 text-left hover:!bg-subtle"
                  style={{ background: n.unread ? "#F5F7FE" : "#FFFFFF" }}
                >
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-surface">
                    <Icon name={opening === n.id ? "loader" : n.icon} spin={opening === n.id} size={15} className="text-ink-3" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs text-muted">{n.type}</span>
                    <span className="block text-[13.5px] font-medium">{n.text}</span>
                  </span>
                  <span className="whitespace-nowrap text-xs text-muted">{fmtRelativeDay(n.created_at)}</span>
                  {n.unread && (
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary">
                      <span className="sr-only">Unread</span>
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
