"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage } from "@/lib/api";
import { fmtBytes, fmtDateTime } from "@/lib/format";
import { useSession, useUi } from "@/lib/session";
import { Button, ErrorState, Icon, Skeleton } from "@/components/ui";
import { fileIcon } from "./shared";

/** Soft-deleted files that can still be restored during the retention window. */
export function RecentlyDeleted() {
  const { me } = useSession();
  const { toast } = useUi();
  const qc = useQueryClient();
  const canRestore = me?.workspace.role === "owner" || me?.workspace.role === "admin";
  const q = useQuery({ queryKey: ["files", { deleted: true }], queryFn: () => api.listFiles({ deleted: true }) });
  const restore = useMutation({
    mutationFn: (id: string) => api.restoreFile(id),
    onSuccess: (f) => {
      toast(`Restoring ${f.name}. It reappears in Files in a moment.`, "success");
      void qc.invalidateQueries({ queryKey: ["files"] });
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  if (q.isLoading) return <Skeleton lines={4} className="rounded-[10px] border border-line bg-surface p-4" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} retrying={q.isFetching} title="We couldn't load deleted files" />;
  const items = q.data?.items ?? [];
  return (
    <section aria-label="Recently deleted files" className="flex flex-col gap-3">
      <p className="text-[13px] text-muted [text-wrap:pretty]">
        Files deleted through an approved deletion request. They can be restored until the date shown, then their contents are removed for good.
        {!canRestore && " Only workspace owners and admins can restore files."}
      </p>
      {items.length === 0 ? (
        <div className="flex flex-col items-center gap-1.5 rounded-[10px] border border-line bg-surface px-6 py-10 text-center">
          <Icon name="trash-2" size={22} className="text-muted" />
          <div className="font-semibold">Nothing recently deleted</div>
          <div className="max-w-[360px] text-[13.5px] text-muted">
            {DEMO_MODE ? "Demo files are never deleted." : "Deleted files that can still be restored appear here."}
          </div>
        </div>
      ) : (
        <ul className="m-0 list-none overflow-hidden rounded-[10px] border border-line bg-surface p-0">
          {items.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-3 border-b border-line-soft px-4 py-3 last:border-b-0">
              <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg bg-line-soft">
                <Icon name={fileIcon(f)} size={16} className="text-ink-3" />
              </span>
              <span className="min-w-0 flex-[1_1_200px]">
                <span className="block truncate font-medium">{f.name}</span>
                <span className="block text-xs text-muted">
                  {f.type_label} · {fmtBytes(f.size_bytes)}
                  {f.deleted_at && ` · deleted ${fmtDateTime(f.deleted_at)}`}
                  {f.restorable_until && ` · restorable until ${fmtDateTime(f.restorable_until)}`}
                </span>
              </span>
              {canRestore && (
                <Button
                  size="sm"
                  icon="archive-restore"
                  onClick={() => restore.mutate(f.id)}
                  disabled={restore.isPending && restore.variables === f.id}
                  aria-label={`Restore ${f.name}`}
                >
                  Restore
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
