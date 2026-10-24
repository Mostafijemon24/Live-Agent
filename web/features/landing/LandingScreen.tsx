"use client";

import { useRouter } from "next/navigation";
import { DEMO_MODE } from "@/lib/api";
import { useSession, useUi } from "@/lib/session";
import { Icon } from "@/components/ui";

const PLAN_STEPS: [string, string, string, string][] = [
  ["01", "Read site structure and page list", "Read only", "text-success bg-success-soft"],
  ["02", "Measure loading speed on 25 pages", "Read only", "text-success bg-success-soft"],
  ["03", "Write a report with prioritised fixes", "Workspace only", "text-ink-3 bg-neutral-soft"],
  ["04", "Apply fixes to the live website", "Needs approval", "text-warning bg-warning-soft"],
];

const HOW: [string, string, string][] = [
  ["01", "Describe the task", "Write what you need the way you would brief a colleague. Attach files only if they are needed."],
  ["02", "Review the plan", "See every step, the tools involved, the files it reads and anywhere data might go — before anything runs."],
  ["03", "Approve and track", "Approve sensitive actions one at a time. Follow progress, logs and reports in one place."],
];

const PRINCIPLES: [string, string, string][] = [
  ["send", "Nothing leaves without approval", "Uploading a file never authorises sharing it with an AI provider."],
  ["globe", "Live sites change only after review", "Changes are prepared first and shown to you with their consequences."],
  ["trash-2", "Deletion is always specific", "Each deletion lists the exact items and needs its own approval."],
  ["history", "Everything is logged", "Who approved what, when and for which exact scope."],
];

const btnPrimary = "inline-flex items-center gap-2 rounded-lg border-0 bg-primary font-medium text-white hover:bg-primary-hover";
const btnSecondary = "rounded-lg border border-line-strong bg-surface font-medium text-ink hover:bg-subtle";
const wrap = "mx-auto max-w-[1200px] px-[clamp(16px,4vw,40px)]";

export function LandingScreen() {
  const router = useRouter();
  const { me } = useSession();
  const { toast } = useUi();
  const placeholder = () => toast("Placeholder link — replace with your real policy page.", "info");

  return (
    <div className="bg-page">
      <header className={`${wrap} flex flex-wrap items-center justify-between gap-4 py-[18px]`}>
        <div className="flex items-center gap-2.5">
          <div className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-primary text-white">
            <Icon name="shield-check" size={17} />
          </div>
          <span className="text-[17px] font-semibold tracking-[-.01em]">Steward</span>
        </div>
        <nav aria-label="Site" className="flex flex-wrap items-center gap-2">
          {me ? (
            <button type="button" onClick={() => router.push("/overview")} className={`${btnPrimary} h-9 px-3.5 text-sm`}>
              Open workspace
            </button>
          ) : (
            <>
              <button type="button" onClick={() => router.push("/login")} className={`${btnSecondary} h-9 px-3.5 text-sm`}>
                Sign in
              </button>
              <button type="button" onClick={() => router.push("/register")} className={`${btnPrimary} h-9 px-3.5 text-sm`}>
                {DEMO_MODE ? "Create demo account" : "Create account"}
              </button>
            </>
          )}
        </nav>
      </header>

      <section className={`${wrap} flex flex-wrap items-center gap-12 py-[clamp(32px,6vw,72px)]`}>
        <div className="min-w-0 flex-[1_1_420px]">
          <div className="mb-5 inline-flex items-center gap-2 rounded-md bg-primary-soft px-2.5 py-1 text-[12.5px] font-medium text-primary">
            <Icon name="sparkles" size={14} />
            {DEMO_MODE ? "AI agent workspace · design prototype" : "AI agent workspace · early preview"}
          </div>
          <h1 className="text-[clamp(34px,5vw,52px)] leading-[1.08] font-semibold tracking-[-.025em] [text-wrap:balance]">Hand off the busywork. Keep every decision.</h1>
          <p className="mt-5 max-w-[540px] text-[17px] leading-[1.6] text-ink-3 [text-wrap:pretty]">
            Describe a task in plain language. Steward plans it, shows exactly what it will touch, and waits for your approval before anything leaves your workspace or
            changes a live system.
          </p>
          <div className="mt-7 flex flex-wrap gap-2.5">
            {me ? (
              <button type="button" onClick={() => router.push("/overview")} className={`${btnPrimary} h-11 px-5 text-[15px]`}>
                Go to your workspace
                <Icon name="arrow-right" size={16} />
              </button>
            ) : (
              <>
                <button type="button" onClick={() => router.push("/register")} className={`${btnPrimary} h-11 px-5 text-[15px]`}>
                  {DEMO_MODE ? "Try the demo workspace" : "Create your workspace"}
                  <Icon name="arrow-right" size={16} />
                </button>
                <button type="button" onClick={() => router.push("/login")} className={`${btnSecondary} h-11 px-5 text-[15px]`}>
                  Sign in
                </button>
              </>
            )}
          </div>
          <p className="mt-3.5 text-[13px] text-muted">
            {DEMO_MODE
              ? "Prototype only — no real account is created and no task is executed."
              : "Early preview — the Agent plans first, and nothing runs until you approve the plan."}
          </p>
        </div>

        <div aria-hidden="true" className="max-w-[520px] min-w-0 flex-[1_1_400px]">
          <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-hero">
            <div className="flex items-center justify-between gap-3 border-b border-line px-[18px] py-3.5">
              <div>
                <div className="font-mono text-xs text-muted">T-1048 · Plan review</div>
                <div className="text-[15px] font-semibold">WordPress performance &amp; SEO audit</div>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-md bg-warning-soft px-2 py-0.5 text-xs font-medium whitespace-nowrap text-warning">
                <Icon name="hourglass" size={13} />
                Awaiting approval
              </span>
            </div>
            <div className="px-[18px] pt-2 pb-1">
              {PLAN_STEPS.map(([n, text, tag, cls]) => (
                <div key={n} className="flex items-center gap-3 border-b border-line-soft py-2.5 last:border-b-0">
                  <span className="w-[18px] font-mono text-xs text-muted">{n}</span>
                  <span className="flex-1">{text}</span>
                  <span className={`rounded-md px-2 py-px text-xs ${cls}`}>{tag}</span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-subtle px-[18px] py-3.5">
              <span className="inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium">Request changes</span>
              <span className="inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-medium text-white">Approve selected steps</span>
            </div>
          </div>
          <p className="mx-1 mt-2.5 font-mono text-xs text-muted">Illustration of the plan review screen</p>
        </div>
      </section>

      <section className="border-y border-line bg-surface">
        <div className={`${wrap} py-[clamp(40px,6vw,72px)]`}>
          <h2 className="text-[26px] font-semibold tracking-[-.015em]">How it works</h2>
          <div className="mt-8 grid grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))] gap-8">
            {HOW.map(([n, title, body]) => (
              <div key={n} className="flex flex-col gap-2">
                <span className="font-mono text-[13px] text-primary">{n}</span>
                <h3 className="text-[17px] font-semibold">{title}</h3>
                <p className="text-ink-3 [text-wrap:pretty]">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className={`${wrap} flex flex-wrap gap-12 py-[clamp(40px,6vw,72px)]`}>
        <div className="min-w-0 flex-[1_1_300px]">
          <h2 className="text-[26px] font-semibold tracking-[-.015em] [text-wrap:balance]">Built around your approval</h2>
          <p className="mt-3 max-w-[420px] text-ink-3 [text-wrap:pretty]">
            The Agent asks first whenever data would leave your workspace, a live system would change, or something would be deleted.
          </p>
        </div>
        <div className="grid min-w-0 flex-[2_1_480px] grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-3">
          {PRINCIPLES.map(([icon, title, body]) => (
            <div key={title} className="flex gap-3 rounded-[10px] border border-line bg-surface p-[18px]">
              <Icon name={icon} size={18} className="mt-0.5 text-primary" />
              <div>
                <div className="font-semibold">{title}</div>
                <div className="mt-1 text-[13.5px] text-muted">{body}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-line bg-surface">
        <div className={`${wrap} flex flex-wrap justify-between gap-4 py-5 text-[13px] text-muted`}>
          <span>{DEMO_MODE ? "Steward — design prototype. Not a production service." : "Steward — early preview. Not a guarantee of complete security; see Security & privacy."}</span>
          <div className="flex gap-4">
            <button type="button" onClick={placeholder} className="border-0 bg-transparent p-0 text-[13px] text-primary">
              Terms (placeholder)
            </button>
            <button type="button" onClick={placeholder} className="border-0 bg-transparent p-0 text-[13px] text-primary">
              Privacy (placeholder)
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
