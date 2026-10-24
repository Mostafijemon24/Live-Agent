"use client";

import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, DEMO_MODE, errorMessage, isApiError, type CreateAutomationInput } from "@/lib/api";
import { useUi } from "@/lib/session";
import { Button, Icon, Modal, cx } from "@/components/ui";

const STEPS = ["Basics", "Trigger", "Scope & tools", "Approval policy", "Review"] as const;
const TEMPLATES = ["WordPress audit (read-only)", "SEO report", "Plugin compatibility check", "Uptime and SSL check"];
const TRIGGERS = [
  { k: "Manual", d: "You start it from the Automations page.", icon: "hand", disabled: false },
  { k: "Schedule", d: "Runs on a timetable. Needs the backend scheduler.", icon: "calendar-clock", disabled: false },
  { k: "Event", d: "Runs when something happens. Coming later.", icon: "zap", disabled: true },
] as const;
const FREQS = ["Daily", "Weekly", "Monthly"] as const;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TOOLS = ["WordPress (read-only)", "WordPress (write)", "Browser runtime", "Agent analysis", "Email"];
const SCOPES = ["Private files only", "No files", "Approved files only"];
const POLICIES = ["Ask before any change", "Ask before publishing or sending", "Ask before external sharing only"];

type Trigger = "Manual" | "Schedule";
type Freq = (typeof FREQS)[number];
interface WizState {
  step: number;
  name: string;
  template: string;
  trigger: Trigger;
  freq: Freq;
  day: string;
  time: string;
  tools: string[];
  cls: string;
  policy: string;
}
const INITIAL: WizState = {
  step: 0,
  name: "",
  template: TEMPLATES[0],
  trigger: "Manual",
  freq: "Weekly",
  day: "Monday",
  time: "08:00",
  tools: ["WordPress (read-only)"],
  cls: SCOPES[0],
  policy: POLICIES[0],
};

const selectCls = "h-[38px] w-full rounded-lg border border-line-strong bg-surface px-2.5 text-sm font-normal";
const smallSelectCls = "h-9 rounded-lg border border-line-strong bg-surface px-2 text-[13.5px]";

function chipStyle(on: boolean) {
  return { background: on ? "#EEF1FC" : "#FFFFFF", borderColor: on ? "#3448C5" : "#E4E7EC", color: on ? "#3448C5" : "#344054" };
}

function whenText(w: WizState) {
  if (w.trigger === "Manual") return "When you start it";
  if (w.freq === "Weekly") return `Every ${w.day} at ${w.time}`;
  if (w.freq === "Daily") return `Every day at ${w.time}`;
  return `1st of each month at ${w.time}`;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-[13px] font-medium">
      {label}
      {children}
    </label>
  );
}

export function AutomationWizard({ timezone, onClose }: { timezone: string; onClose: () => void }) {
  const { toast } = useUi();
  const qc = useQueryClient();
  const [w, setW] = useState<WizState>(INITIAL);
  const [err, setErr] = useState("");
  const set = (patch: Partial<WizState>) => setW((s) => ({ ...s, ...patch }));
  const isSched = w.trigger === "Schedule";

  const save = useMutation({
    mutationFn: () => {
      const input: CreateAutomationInput = {
        name: w.name.trim(),
        trigger: isSched ? "schedule" : "manual",
        template: w.template,
        tools: w.tools,
        file_scope: w.cls,
        approval_policy: w.policy,
      };
      if (isSched) {
        input.frequency = w.freq.toLowerCase() as CreateAutomationInput["frequency"];
        input.time = w.time;
        if (w.freq === "Weekly") input.day = w.day;
      }
      return api.createAutomation(input);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["automations"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast(
        isSched ? "Automation saved as paused. Scheduled runs need the backend scheduler." : DEMO_MODE ? "Automation saved (demo)." : "Automation saved.",
        "success",
      );
      onClose();
    },
    onError: (e) => {
      const nameErr = isApiError(e) ? e.fieldErrors().name : undefined;
      if (nameErr) {
        setErr(nameErr);
        set({ step: 0 });
        return;
      }
      toast(errorMessage(e), "danger");
    },
  });

  const next = () => {
    if (w.step === 0 && !w.name.trim()) {
      setErr("Give the automation a name.");
      return;
    }
    if (w.step === 4) {
      save.mutate();
      return;
    }
    setErr("");
    set({ step: w.step + 1 });
  };
  const back = () => set({ step: Math.max(0, w.step - 1) });

  return (
    <Modal
      title="New automation"
      onClose={onClose}
      footer={
        <div className="flex w-full justify-between gap-2">
          <Button onClick={back} disabled={w.step === 0 || save.isPending}>
            Back
          </Button>
          <Button variant="primary" onClick={next} loading={save.isPending} className="px-4">
            {w.step === 4 ? "Save automation" : "Continue"}
          </Button>
        </div>
      }
    >
      <div className="px-5 pt-4">
        <div className="flex justify-between font-mono text-[12.5px] text-muted">
          <span>STEP {w.step + 1} OF 5</span>
          <span>{STEPS[w.step]}</span>
        </div>
      </div>
      <div className="flex min-h-[240px] flex-col gap-3.5 px-5 pb-5 pt-4">
        {w.step === 0 && (
          <>
            <Field label="Name">
              <input
                value={w.name}
                onChange={(e) => {
                  set({ name: e.target.value });
                  if (err) setErr("");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") next();
                }}
                placeholder="e.g. Weekly broken-link check"
                aria-invalid={err ? true : undefined}
                aria-describedby={err ? "wiz-name-err" : undefined}
                maxLength={120}
                className={cx(
                  "h-[38px] rounded-lg border bg-surface px-3 text-sm font-normal placeholder:text-faint",
                  err ? "border-danger" : "border-line-strong",
                )}
              />
              {err && (
                <span id="wiz-name-err" role="alert" className="text-[12.5px] font-normal text-danger">
                  {err}
                </span>
              )}
            </Field>
            <Field label="Task template">
              <select value={w.template} onChange={(e) => set({ template: e.target.value })} className={selectCls}>
                {TEMPLATES.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}

        {w.step === 1 && (
          <>
            <div role="radiogroup" aria-label="Trigger" className="flex flex-col gap-3.5">
              {TRIGGERS.map((t) => {
                const on = w.trigger === t.k;
                return (
                  <button
                    key={t.k}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    disabled={t.disabled}
                    onClick={() => {
                      if (!t.disabled) set({ trigger: t.k as Trigger });
                    }}
                    className="flex items-start gap-3 rounded-[10px] border px-3.5 py-3 text-left disabled:cursor-not-allowed disabled:opacity-55"
                    style={chipStyle(on)}
                  >
                    <Icon name={t.icon} size={17} className="mt-0.5 text-primary" />
                    <span>
                      <span className="block font-semibold text-ink">{t.k}</span>
                      <span className="block text-[13px] text-muted">{t.d}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {isSched && (
              <>
                <div className="flex flex-wrap gap-2">
                  <select aria-label="Frequency" value={w.freq} onChange={(e) => set({ freq: e.target.value as Freq })} className={smallSelectCls}>
                    {FREQS.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                  {w.freq === "Weekly" && (
                    <select aria-label="Day" value={w.day} onChange={(e) => set({ day: e.target.value })} className={smallSelectCls}>
                      {DAYS.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  )}
                  <input
                    type="time"
                    aria-label="Time"
                    value={w.time}
                    onChange={(e) => set({ time: e.target.value || "08:00" })}
                    className="h-9 rounded-lg border border-line-strong bg-surface px-2 text-[13.5px]"
                  />
                </div>
                <div className="text-[12.5px] text-muted">Timezone: {timezone}. Minimum interval is daily to avoid overloading your site.</div>
              </>
            )}
          </>
        )}

        {w.step === 2 && (
          <>
            <div className="text-[13px] font-medium" id="wiz-tools">
              Allowed tools
            </div>
            <div role="group" aria-labelledby="wiz-tools" className="flex flex-wrap gap-2">
              {TOOLS.map((t) => {
                const on = w.tools.includes(t);
                return (
                  <button
                    key={t}
                    type="button"
                    aria-pressed={on}
                    onClick={() => set({ tools: on ? w.tools.filter((x) => x !== t) : [...w.tools, t] })}
                    className="h-8 rounded-lg border px-3 text-[13px] font-medium"
                    style={chipStyle(on)}
                  >
                    {t}
                  </button>
                );
              })}
            </div>
            <Field label="Data classification rule">
              <select value={w.cls} onChange={(e) => set({ cls: e.target.value })} className={selectCls}>
                {SCOPES.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}

        {w.step === 3 && (
          <>
            <div className="text-[13px] font-medium" id="wiz-policy">
              When should it ask you?
            </div>
            <div role="radiogroup" aria-labelledby="wiz-policy" className="flex flex-col gap-3.5">
              {POLICIES.map((p) => {
                const on = w.policy === p;
                return (
                  <button
                    key={p}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => set({ policy: p })}
                    className="flex items-center gap-2.5 rounded-[10px] border px-3.5 py-3 text-left text-sm font-medium"
                    style={{ ...chipStyle(on), color: "#172033" }}
                  >
                    {p}
                  </button>
                );
              })}
            </div>
            <div className="text-[12.5px] text-muted">Deleting files or records always needs its own approval, whatever you pick here.</div>
          </>
        )}

        {w.step === 4 && (
          <>
            <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13.5px]">
              {(
                [
                  ["Name", w.name.trim()],
                  ["Template", w.template],
                  ["Trigger", `${w.trigger} · ${whenText(w)}`],
                  ["Timezone", timezone],
                  ["Tools", w.tools.join(", ") || "None"],
                  ["Data rule", w.cls],
                  ["Approvals", w.policy],
                ] as const
              ).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{k}</dt>
                  <dd className="m-0 min-w-0 break-words">{v}</dd>
                </div>
              ))}
            </dl>
            {isSched && (
              <div className="rounded-lg bg-warning-soft px-3 py-2.5 text-[13px] text-[#93370D]">Will be saved as paused — the scheduler needs the backend.</div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
