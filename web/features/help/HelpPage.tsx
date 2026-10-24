"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { DEMO_MODE } from "@/lib/api";
import { useUi } from "@/lib/session";
import { Button, Icon, PageHeader } from "@/components/ui";

const STEPS: [string, string, string][] = [
  ["Choose privacy defaults", "/security", "Security & Privacy"],
  ["Add the files it should use", "/files", "Files & Knowledge"],
  ["Describe a task", "/tasks/new", "New task"],
  ["Review and approve", "/approvals", "Approvals"],
];

const FAQ: [string, string][] = [
  [
    "What can the Agent access?",
    "Only the places you allow: files you add to this workspace, tools you connect, and websites on your allowlist. Everything else is off-limits. " +
      (DEMO_MODE ? "In this prototype, the Agent can access nothing real." : "Right now the AI engine isn't installed, so the Agent can't access anything yet."),
  ],
  [
    "When does data leave my workspace?",
    "Only when a step needs an outside service — like an AI provider or email — and you approve that specific step. Adding a file never counts as permission to share it.",
  ],
  [
    "Why is approval needed?",
    "Some actions cannot be undone or affect other people: changing a live website, publishing, sending messages, deleting items or sharing data. Approval lets you see the exact scope first.",
  ],
  [
    "How do I stop a task?",
    "Open the task and choose Pause or Cancel. Cancelling asks you to confirm. Steps that already finished are listed in the task log.",
  ],
  [
    "What happens when I delete a file?",
    DEMO_MODE
      ? "Deletion needs its own approval listing the exact file. Once the backend is connected, deleted files are kept for the retention period and then removed permanently."
      : "Deletion needs its own approval listing the exact file. Approving records your decision, but nothing is deleted yet — deletion runs once the execution engine is installed (Phase 3), and then follows the retention period.",
  ],
];

const outlineBtn =
  "inline-flex h-[34px] items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink hover:bg-subtle hover:text-ink hover:no-underline";

export function HelpPage() {
  const { toast } = useUi();
  const [open, setOpen] = useState(0);
  const base = useId();

  return (
    <div data-screen-label="Help" className="flex max-w-[900px] flex-col gap-4">
      <PageHeader title="Help & Getting Started" subtitle="Plain-language answers about what the Agent can and can't do." />

      <section className="rounded-[10px] border border-line bg-surface px-5 py-[18px]">
        <h2 className="mb-3 text-[15px] font-semibold">Getting started</h2>
        <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-3 p-0">
          {STEPS.map(([title, href, link], i) => (
            <li key={href} className="flex flex-col gap-1">
              <span className="font-mono text-[12.5px] text-primary">{String(i + 1).padStart(2, "0")}</span>
              <span className="font-medium">{title}</span>
              <Link href={href} className="self-start text-[13px]">
                {link} →
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-[10px] border border-line bg-surface">
        <h2 className="px-5 pb-2 pt-4 text-[15px] font-semibold">Common questions</h2>
        {FAQ.map(([q, a], i) => {
          const isOpen = open === i;
          const pid = `${base}-faq-${i}`;
          return (
            <div key={q} className="border-t border-line-soft">
              <h3 className="m-0">
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? -1 : i)}
                  aria-expanded={isOpen}
                  aria-controls={pid}
                  className="flex w-full items-center justify-between gap-3 border-0 bg-transparent px-5 py-3.5 text-left text-sm font-medium"
                >
                  {q}
                  <Icon name={isOpen ? "minus" : "plus"} size={16} className="text-muted" />
                </button>
              </h3>
              {isOpen && (
                <p id={pid} className="px-5 pb-4 text-ink-3 [text-wrap:pretty]">
                  {a}
                </p>
              )}
            </div>
          );
        })}
      </section>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,280px),1fr))] gap-3">
        <section className="flex flex-col items-start gap-2 rounded-[10px] border border-line bg-surface px-5 py-[18px]">
          <h2 className="text-[15px] font-semibold">Contact support</h2>
          <p className="text-[13.5px] text-muted">Support channel to be added.</p>
          <Button size="sm" className="text-[13px]" onClick={() => toast("Placeholder — add your support email or help desk link.", "info")}>
            Contact (placeholder)
          </Button>
        </section>
        <section className="flex flex-col items-start gap-2 rounded-[10px] border border-line bg-surface px-5 py-[18px]">
          <h2 className="text-[15px] font-semibold">System states (for review)</h2>
          <p className="text-[13.5px] text-muted">Loading, empty, error, permission and session states used across the app.</p>
          <Link href="/states" className={outlineBtn}>
            View states
          </Link>
        </section>
      </div>
    </div>
  );
}
