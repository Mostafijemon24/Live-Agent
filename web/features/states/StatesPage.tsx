"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { DEMO_MODE } from "@/lib/api";
import { Button, Icon, PageHeader, cx } from "@/components/ui";

const btn = "inline-flex h-8 items-center rounded-[7px] px-3 text-[13px] font-medium hover:no-underline";
const btnPrimary = cx(btn, "border-0 bg-primary text-white hover:bg-primary-hover hover:text-white");
const btnOutline = cx(btn, "border border-line-strong bg-surface text-ink hover:bg-subtle hover:text-ink");

function StateCard({ label, icon, color, title, children, action }: { label: string; icon: string; color: string; title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <article className="flex flex-col items-start gap-2 rounded-[10px] border border-line bg-surface p-[18px]">
      <div className="font-mono text-xs text-muted">{label}</div>
      <Icon name={icon} size={20} style={{ color }} />
      <div className="font-semibold">{title}</div>
      <div className="text-[13.5px] text-muted [text-wrap:pretty]">{children}</div>
      {action}
    </article>
  );
}

/** Demonstrates a safe retry: it spins, counts the attempt, and never pretends the retry worked. */
function NetworkErrorCard() {
  const [retrying, setRetrying] = useState(false);
  const [n, setN] = useState(1);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const retry = () => {
    setRetrying(true);
    timer.current = setTimeout(() => {
      setRetrying(false);
      setN((x) => x + 1);
    }, 1200);
  };
  return (
    <StateCard
      label="NETWORK ERROR · SAFE RETRY"
      icon="wifi-off"
      color="#B42318"
      title="We couldn't load your tasks"
      action={
        <Button size="xs" loading={retrying} onClick={retry} className="h-8 rounded-[7px] px-3">
          Try again
        </Button>
      }
    >
      <span role="status">
        The server didn&apos;t respond. Nothing was changed. Attempt {n} — this demo never pretends a retry worked.
      </span>
    </StateCard>
  );
}

export function StatesPage() {
  return (
    <div data-screen-label="System states" className="flex flex-col gap-4">
      <PageHeader title="System states" subtitle="Reference for reviewers: how every data screen behaves when things aren't normal." />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,340px),1fr))] gap-3">
        <article aria-busy="true" className="flex flex-col gap-2.5 rounded-[10px] border border-line bg-surface p-[18px]">
          <div className="font-mono text-xs text-muted">LOADING</div>
          <span className="sr-only">Loading example</span>
          {["50%", "90%", "75%", "60%"].map((w) => (
            <div key={w} className="h-3 animate-pulse-soft rounded bg-track" style={{ width: w }} />
          ))}
        </article>

        <StateCard
          label="EMPTY"
          icon="inbox"
          color="#667085"
          title="No tasks yet"
          action={
            <Link href="/tasks/new" className={btnPrimary}>
              Create task
            </Link>
          }
        >
          Describe your first task and the Agent will plan it for you.
        </StateCard>

        <NetworkErrorCard />

        <StateCard
          label="PERMISSION DENIED"
          icon="lock"
          color="#B54708"
          title="You don't have access to this"
          action={
            <Link href="/overview" className={btnOutline}>
              Back to overview
            </Link>
          }
        >
          This item belongs to another workspace or needs a role you don&apos;t have. Ask a workspace admin.
        </StateCard>

        <StateCard
          label="SESSION EXPIRED"
          icon="clock"
          color="#475467"
          title="Your session has ended"
          action={
            <Link href="/login" className={btnPrimary}>
              Sign in again
            </Link>
          }
        >
          For your security, please sign in again. Unsaved changes in open forms may be lost.
        </StateCard>

        {DEMO_MODE ? (
          <StateCard label="BACKEND NOT CONFIGURED" icon="server" color="#B54708" title="This feature needs the backend">
            It will work once the server, database and workers are connected. Until then it shows sample data only.
          </StateCard>
        ) : (
          <StateCard label="NO AI MODEL" icon="server" color="#B54708" title="No AI model is configured">
            Your task is saved and waits. Nothing is sent anywhere until an administrator configures an approved model. Screens say so instead of showing made-up results.
          </StateCard>
        )}

        <StateCard label="PARTIAL FAILURE" icon="circle-dashed" color="#B54708" title="Some results couldn't load">
          Tasks loaded, but activity is unavailable right now. What you see may be incomplete.
        </StateCard>

        <StateCard label="SUCCESS" icon="circle-check" color="#16803C" title="Saved">
          Success messages say exactly what happened — and in demo mode, that it was simulated.
        </StateCard>

        <StateCard
          label="NOT FOUND"
          icon="map-pin-off"
          color="#475467"
          title="Page not found"
          action={
            <Link href="/this-page-does-not-exist" className={btnOutline}>
              Open a broken link
            </Link>
          }
        >
          Preview the full-page version.
        </StateCard>
      </div>
    </div>
  );
}
