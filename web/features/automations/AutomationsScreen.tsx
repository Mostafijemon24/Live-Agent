"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type Automation } from "@/lib/api";
import { useUi } from "@/lib/session";
import { Badge, Button, EmptyState, ErrorState, Icon, Modal, PageHeader, Skeleton } from "@/components/ui";
import { AutomationWizard } from "./AutomationWizard";

const ENABLED = { label: "Enabled", fg: "#16803C", bg: "#ECFDF3", icon: "circle-check" };
const PAUSED = { label: "Paused", fg: "#475467", bg: "#F2F4F7", icon: "circle-pause" };
const TRIGGER_LABEL: Record<Automation["trigger"], string> = { manual: "Manual", schedule: "Schedule", event: "Event" };
const TRIGGER_ICON: Record<Automation["trigger"], string> = { manual: "hand", schedule: "calendar-clock", event: "zap" };

const SCHEDULER_BODY =
  "This server can't schedule automations right now. Your settings are saved; you can still run the automation by hand.";

export function AutomationsScreen() {
  const { toast, notice } = useUi();
  const qc = useQueryClient();
  const [wizard, setWizard] = useState(false);
  const [history, setHistory] = useState<Automation | null>(null);

  const list = useQuery({ queryKey: ["automations"], queryFn: () => api.listAutomations() });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.getSettings() });
  const tz = settings.data?.profile.timezone;

  const toggle = useMutation({
    mutationFn: (a: Automation) => api.setAutomationEnabled(a.id, !a.enabled),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["automations"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast(`Automation ${res.enabled ? "enabled" : "paused"}${DEMO_MODE ? " (demo)" : ""}.`, "info");
    },
    onError: (e) => {
      if (isApiError(e) && e.code === "scheduler_not_configured") notice("Scheduler not connected", SCHEDULER_BODY);
      else toast(errorMessage(e), "danger");
    },
  });

  const run = useMutation({
    mutationFn: (a: Automation) => api.runAutomation(a.id),
    onSuccess: (task) => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["automations"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
      toast(
        DEMO_MODE
          ? `Queued ${task.ref} (simulated). It will not run without a backend.`
          : `Queued ${task.ref}. You’ll review its plan before anything runs.`,
        "success",
      );
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const items = list.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Automations"
        subtitle={`Repeatable tasks that run by hand or on a schedule. Times shown in ${tz ?? "your profile's timezone"}.`}
        actions={
          <Button variant="primary" icon="plus" onClick={() => setWizard(true)}>
            New automation
          </Button>
        }
      />

      <div className="flex gap-2 rounded-[10px] border border-line bg-surface px-3.5 py-2.5 text-[13px] text-ink-3">
        <Icon name="calendar-clock" size={15} className="mt-0.5 text-primary" />
        <span>
          {DEMO_MODE
            ? "Demo: schedules are not run in this prototype."
            : "Scheduled automations create a task at each scheduled time (at most once per slot). The task’s plan waits for your review — nothing runs on its own."}
        </span>
      </div>

      {list.isLoading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-[10px] border border-line bg-surface p-[18px]">
              <Skeleton lines={6} />
            </div>
          ))}
        </div>
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} retrying={list.isFetching} />
      ) : items.length === 0 ? (
        <div className="rounded-[10px] border border-line bg-surface">
          <EmptyState
            icon="repeat"
            title="No automations yet"
            action={
              <Button variant="primary" size="sm" icon="plus" onClick={() => setWizard(true)}>
                New automation
              </Button>
            }
          >
            Save a task you repeat often — like a weekly site check — and start it with one click.
          </EmptyState>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-3">
          {items.map((a) => {
            const toggling = toggle.isPending && toggle.variables?.id === a.id;
            const running = run.isPending && run.variables?.id === a.id;
            return (
              <article key={a.id} className="flex flex-col rounded-[10px] border border-line bg-surface">
                <div className="flex items-start gap-3 border-b border-line-soft px-[18px] py-4">
                  <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg bg-primary-soft">
                    <Icon name={TRIGGER_ICON[a.trigger]} size={16} className="text-primary" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold break-words">{a.name}</div>
                    <div className="text-[12.5px] text-muted">
                      {TRIGGER_LABEL[a.trigger]} · {a.schedule_text}
                    </div>
                  </div>
                  <Badge meta={a.enabled ? ENABLED : PAUSED} className="gap-[5px]" />
                </div>
                <dl className="m-0 grid flex-1 grid-cols-[auto_1fr] gap-x-3.5 gap-y-1.5 px-[18px] py-3.5 text-[13px]">
                  {(
                    [
                      ["Template", a.template],
                      ["Allowed tools", a.tools.join(", ") || "None"],
                      ["Data rules", a.file_scope],
                      ["Approvals", a.approval_policy],
                      ["Last run", a.last_run_text],
                      ["Next run", a.next_run_text],
                      ["Timezone", a.timezone],
                    ] as const
                  ).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-muted">{k}</dt>
                      <dd className="m-0 min-w-0 break-words">{v}</dd>
                    </div>
                  ))}
                </dl>
                <div className="flex flex-wrap gap-2 border-t border-line-soft px-[18px] py-3">
                  {a.trigger === "manual" && (
                    <Button variant="primary" size="xs" icon="play" className="h-8! px-3!" loading={running} onClick={() => run.mutate(a)}>
                      Run now
                    </Button>
                  )}
                  <Button size="xs" className="h-8! px-3!" loading={toggling} onClick={() => toggle.mutate(a)}>
                    {a.enabled ? "Pause" : "Resume"}
                  </Button>
                  <Button variant="ghost" size="xs" className="h-8! px-3! text-primary! hover:bg-primary-soft!" onClick={() => setHistory(a)}>
                    Run history
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {wizard && <AutomationWizard timezone={tz ?? "your profile's timezone"} onClose={() => setWizard(false)} />}

      {history && (
        <Modal
          title="Run history"
          onClose={() => setHistory(null)}
          footer={
            <Button onClick={() => setHistory(null)} className="px-4">
              Close
            </Button>
          }
        >
          <div className="px-5 py-7 text-center text-muted">
            <Icon name="history" size={22} className="mx-auto" />
            <div className="mt-1.5 font-semibold text-ink">{history.name}</div>
            <div className="mt-1 text-[13.5px]">
              Last run: {history.last_run_text}.{" "}
              {DEMO_MODE
                ? "Run history with outcomes and links to each task appears once the scheduler and job queue are connected."
                : "Each run creates a task in Tasks. Its plan waits for your review — scheduled runs never execute on their own."}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
