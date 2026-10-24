"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError } from "@/lib/api";
import type { CreateTaskInput, ExecutionMode, TaskPriority, TaskType } from "@/lib/api/types";
import { useUi } from "@/lib/session";
import { fmtBytes, newIdempotencyKey, suggestTitle } from "@/lib/format";
import { CLASSIFICATION, FILE_TYPE_ICON, MODES, TASK_TYPES } from "@/lib/labels";
import { Button, ErrorState, FieldError, Icon, Skeleton, cx } from "@/components/ui";

const MAX = 4000;
const MIN_MSG = "Describe the task in a sentence or two so the Agent can plan it.";
const P = "#3448C5";
const chip = (on: boolean) => ({ bg: on ? "#EEF1FC" : "#FFFFFF", bd: on ? P : "#E4E7EC", fg: on ? P : "#344054", box: on ? P : "#FFFFFF" });

type SourceKey = "none" | "workspace_file" | "imported_csv" | "wordpress";
const SOURCES: { key: SourceKey; label: string; disabled: boolean }[] = [
  { key: "none", label: "No source", disabled: false },
  { key: "workspace_file", label: "Workspace file", disabled: false },
  { key: "imported_csv", label: "Imported CSV (backend required)", disabled: true },
  DEMO_MODE
    ? { key: "wordpress", label: "WordPress (demo)", disabled: false }
    : { key: "wordpress", label: "WordPress — not connected (Phase 3)", disabled: true },
];

const isType = (v: string | null): v is TaskType => !!v && TASK_TYPES.some((t) => t.value === v);

const fieldLabel = "flex flex-col gap-1.5 text-[13px] font-medium";

export function NewTaskPage() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const { toast } = useUi();

  const [prompt, setPrompt] = useState(() => (params.get("prompt") ?? "").slice(0, MAX));
  const [title, setTitle] = useState("");
  const [type, setType] = useState<TaskType>(() => {
    const t = params.get("type");
    return isType(t) ? t : "website";
  });
  const [priority, setPriority] = useState<TaskPriority>("normal");
  const [mode, setMode] = useState<ExecutionMode>("plan_only");
  const [source, setSource] = useState<SourceKey>("none");
  const [attach, setAttach] = useState<string[]>(() => {
    const a = params.get("attach");
    return a ? [a] : [];
  });
  const [errs, setErrs] = useState<Record<string, string>>({});
  // Generated once per form attempt: a retry of the unchanged form reuses it, any edit starts a new attempt.
  const keyRef = useRef<string | null>(null);

  const edit = <T,>(set: (v: T) => void, field?: string) => (v: T) => {
    set(v);
    keyRef.current = null;
    if (field) setErrs((e) => (e[field] ? { ...e, [field]: "" } : e));
  };

  const files = useQuery({ queryKey: ["files", { status: "ready" }], queryFn: () => api.listFiles({ status: "ready" }) });
  const limits = useQuery({ queryKey: ["upload-limits"], queryFn: () => api.uploadLimits(), staleTime: 300_000 });

  const create = useMutation({
    mutationFn: (input: CreateTaskInput) => {
      if (!keyRef.current) keyRef.current = newIdempotencyKey();
      return api.createTask(input, keyRef.current);
    },
    onSuccess: (task) => {
      keyRef.current = null;
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      toast(
        DEMO_MODE ? "Task created. A sample plan is being prepared (simulated)." : "Task saved and queued. Nothing runs until you review and approve a plan.",
        "success",
      );
      router.push(`/tasks/${task.id}/plan`);
    },
    onError: (e) => {
      const fe = isApiError(e) ? e.fieldErrors() : {};
      const known = ["prompt", "title", "type", "priority", "mode", "integration_key", "attachment_file_ids"];
      const shown = Object.fromEntries(Object.entries(fe).filter(([k]) => known.includes(k)));
      setErrs(shown);
      if (Object.keys(shown).length === 0) toast(errorMessage(e), "danger");
    },
  });

  const submit = () => {
    const p = prompt.trim();
    if (p.length < 12) {
      setErrs({ prompt: MIN_MSG });
      return;
    }
    const integration_key = DEMO_MODE && (source === "wordpress" || type === "website") ? "wordpress" : null;
    create.mutate({
      prompt: p,
      title: title.trim() || suggestTitle(p),
      type,
      priority,
      mode,
      integration_key,
      attachment_file_ids: attach,
    });
  };

  const readyFiles = files.data?.items ?? [];
  const limitText = limits.data
    ? `${limits.data.allowed_types.join(", ")} · up to ${fmtBytes(limits.data.max_bytes)}.`
    : "PDF, DOCX, CSV, XLSX, TXT, MD · up to 25 MB (limits come from the backend).";
  const otherErrs = [errs.type, errs.priority, errs.mode].filter(Boolean);

  return (
    <div className="flex max-w-[960px] flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-.015em]">New task</h1>
        <p className="mt-1 text-muted">Describe what you need. The Agent prepares a plan first — nothing runs until you approve it.</p>
      </div>
      <div className="flex flex-wrap items-start gap-4">
        <div className="flex min-w-0 flex-[2_1_520px] flex-col gap-5 rounded-[10px] border border-line bg-surface p-5">
          <label className={fieldLabel}>
            What would you like the Agent to do?
            <textarea
              value={prompt}
              onChange={(e) => edit(setPrompt, "prompt")(e.target.value)}
              rows={6}
              maxLength={MAX}
              aria-invalid={!!errs.prompt || undefined}
              aria-describedby={errs.prompt ? "np-prompt-err" : undefined}
              placeholder="e.g. Audit my WordPress website for performance and SEO problems, prepare a report, and show me recommended fixes before changing anything."
              className="min-h-[150px] w-full resize-y rounded-lg border bg-surface px-3.5 py-3 text-[15px] font-normal leading-[1.55] placeholder:text-faint"
              style={{ borderColor: errs.prompt ? "#B42318" : "#D0D5DD" }}
            />
            <span className="flex justify-between gap-3 text-[12.5px] font-normal text-muted">
              <span>Plain language is fine. Mention anything the Agent must not change.</span>
              <span className="font-mono whitespace-nowrap">
                {prompt.length} / {MAX}
              </span>
            </span>
            {errs.prompt && (
              <span id="np-prompt-err" role="alert" className="flex items-center gap-1.5 text-[12.5px] font-normal text-danger">
                <Icon name="circle-alert" size={14} />
                {errs.prompt}
              </span>
            )}
          </label>

          <label className={fieldLabel}>
            <span>
              Task title <span className="font-normal text-muted">Optional — we&apos;ll suggest one from your description.</span>
            </span>
            <input
              value={title}
              onChange={(e) => edit(setTitle, "title")(e.target.value)}
              maxLength={200}
              placeholder="e.g. Website SEO audit"
              aria-invalid={!!errs.title || undefined}
              className="h-10 w-full rounded-lg border bg-surface px-3 text-sm font-normal placeholder:text-faint"
              style={{ borderColor: errs.title ? "#B42318" : "#D0D5DD" }}
            />
            <FieldError>{errs.title}</FieldError>
          </label>

          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-2 p-0 text-[13px] font-medium">Task type</legend>
            <div className="flex flex-wrap gap-2">
              {TASK_TYPES.map((t) => {
                const c = chip(type === t.value);
                return (
                  <button
                    key={t.value}
                    type="button"
                    aria-pressed={type === t.value}
                    onClick={() => edit(setType, "type")(t.value)}
                    className="inline-flex h-[34px] items-center gap-2 rounded-lg border px-3 text-[13.5px] font-medium"
                    style={{ borderColor: c.bd, background: c.bg, color: c.fg }}
                  >
                    <Icon name={t.icon} size={15} />
                    {t.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="m-0 border-0 p-0">
            <legend className="mb-2 p-0 text-[13px] font-medium">Execution mode</legend>
            <div role="radiogroup" aria-label="Execution mode" className="flex flex-col gap-2">
              {MODES.map((m) => {
                const on = mode === m.value;
                const c = chip(on);
                return (
                  <button
                    key={m.value}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    disabled={m.disabled}
                    onClick={() => !m.disabled && edit(setMode, "mode")(m.value)}
                    className="flex items-start gap-3 rounded-[10px] border px-3.5 py-3 text-left"
                    style={{ borderColor: c.bd, background: c.bg, opacity: m.disabled ? 0.6 : 1 }}
                  >
                    <span className="mt-0.5 grid h-[18px] w-[18px] flex-none place-items-center rounded-full border-[1.5px] bg-surface" style={{ borderColor: c.bd }}>
                      {on && <span className="h-[9px] w-[9px] rounded-full bg-primary" />}
                    </span>
                    <span className="flex-1">
                      <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
                        {m.label}
                        {m.disabled && (
                          <span className="rounded-[5px] bg-warning-soft px-[7px] py-px text-[11.5px] font-medium text-warning">
                            {DEMO_MODE ? "Backend required" : "Phase 3"}
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 block text-[13px] text-muted">{m.description}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>
          {otherErrs.length > 0 && (
            <div role="alert" className="flex flex-col gap-1 text-[12.5px] text-danger">
              {otherErrs.map((e) => (
                <span key={e} className="flex items-center gap-1.5">
                  <Icon name="circle-alert" size={14} />
                  {e}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
          <div className="flex flex-col gap-4 rounded-[10px] border border-line bg-surface p-[18px]">
            <div>
              <div className="mb-2 text-[13px] font-medium">Priority</div>
              <div role="radiogroup" aria-label="Priority" className="flex overflow-hidden rounded-lg border border-line-strong">
                {(["normal", "high"] as const).map((p) => {
                  const c = chip(priority === p);
                  return (
                    <button
                      key={p}
                      type="button"
                      role="radio"
                      aria-checked={priority === p}
                      onClick={() => edit(setPriority, "priority")(p)}
                      className="h-[34px] flex-1 border-0 text-[13.5px] font-medium"
                      style={{ background: c.bg, color: c.fg }}
                    >
                      {p === "normal" ? "Normal" : "High"}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className={fieldLabel}>
              Source / integration
              <select
                value={source}
                onChange={(e) => edit(setSource, "integration_key")(e.target.value as SourceKey)}
                className="h-[38px] rounded-lg border border-line-strong bg-surface px-2.5 text-sm font-normal"
              >
                {SOURCES.map((o) => (
                  <option key={o.key} value={o.key} disabled={o.disabled}>
                    {o.label}
                  </option>
                ))}
              </select>
              <FieldError>{errs.integration_key}</FieldError>
            </label>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[13px] font-medium">Attachments</span>
                <span className="text-xs text-muted">{attach.length} selected</span>
              </div>
              {files.isLoading ? (
                <Skeleton lines={3} />
              ) : files.error ? (
                <ErrorState error={files.error} onRetry={() => files.refetch()} retrying={files.isFetching} title="We couldn't load your files" />
              ) : readyFiles.length === 0 ? (
                <p className="text-[13px] text-muted">No ready files yet. Files appear here once they finish processing in Files &amp; Knowledge.</p>
              ) : (
                <div className="flex max-h-[220px] flex-col gap-1.5 overflow-auto">
                  {readyFiles.map((f) => {
                    const on = attach.includes(f.id);
                    const c = chip(on);
                    const cls = CLASSIFICATION[f.classification];
                    return (
                      <button
                        key={f.id}
                        type="button"
                        aria-pressed={on}
                        onClick={() => edit(setAttach, "attachment_file_ids")(on ? attach.filter((x) => x !== f.id) : [...attach, f.id])}
                        className="flex items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left"
                        style={{ borderColor: c.bd, background: c.bg }}
                      >
                        <Icon name={FILE_TYPE_ICON[f.type_label] ?? "file"} size={15} className="text-muted" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] text-ink">{f.name}</span>
                          <span className="block text-[11.5px]" style={{ color: cls.fg }}>
                            {cls.label}
                          </span>
                        </span>
                        <span className="grid h-4 w-4 flex-none place-items-center rounded border-[1.5px] text-white" style={{ borderColor: c.bd, background: c.box }}>
                          {on && <Icon name="check" size={11} />}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
              <FieldError>{errs.attachment_file_ids}</FieldError>
              <Link
                href="/files"
                className="mt-2 flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-dashed border-line-strong bg-subtle text-[13px] text-ink-3 hover:border-primary hover:text-ink-3 hover:no-underline"
              >
                <Icon name="paperclip" size={15} />
                Upload from device
              </Link>
              <p className="mt-2 text-xs text-muted">{limitText}</p>
            </div>
          </div>
          <div className="flex gap-2.5 rounded-[10px] bg-primary-soft px-3.5 py-3 text-[13px] text-primary-hover">
            <Icon name="shield-check" size={16} className="mt-px" />
            <span>Attaching a file lets the Agent read it inside this workspace. It does not allow sending it to an outside AI provider.</span>
          </div>
          <Button variant="primary" size="lg" icon="list-checks" loading={create.isPending} onClick={submit} className={cx("w-full")}>
            Create task &amp; plan
          </Button>
        </div>
      </div>
    </div>
  );
}
