"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { DEMO_MODE } from "@/lib/api";
import { Icon } from "@/components/ui";

const DEMO_POINTS: [string, string][] = [
  ["lock", "Accounts, passwords and sessions will be handled by the backend with secure cookies."],
  ["eye-off", "Nothing you type here is saved — not even in this browser."],
  ["server", "Rate limits, email verification and account recovery require the backend."],
];

const REAL_POINTS: [string, string][] = [
  ["lock", "Passwords are hashed on the server. Your session lives in a secure, HttpOnly cookie — nothing secret is kept in this browser."],
  ["history", "Sign-in attempts are rate limited, and sign-ins and security changes are recorded in your activity log."],
  ["server", "Every plan needs your approval before anything runs, and sensitive steps ask again, one by one."],
];

/** Two-column layout shared by the sign-in, sign-up, recovery and verification pages. */
export function AuthLayout({ children }: { children: ReactNode }) {
  const points = DEMO_MODE ? DEMO_POINTS : REAL_POINTS;
  return (
    <div className="flex min-h-[calc(100vh-34px)] flex-wrap">
      <div className="flex flex-[1_1_460px] flex-col bg-surface px-[clamp(16px,4vw,48px)] py-6">
        <Link href="/" className="flex items-center gap-2.5 self-start text-ink hover:text-ink hover:no-underline">
          <span className="grid h-[30px] w-[30px] place-items-center rounded-lg bg-primary text-white">
            <Icon name="shield-check" size={17} />
          </span>
          <span className="text-[17px] font-semibold">Steward</span>
        </Link>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[400px]">{children}</div>
        </div>
      </div>
      <aside className="flex flex-[1_1_380px] items-center bg-primary-soft p-[clamp(28px,5vw,64px)]">
        <div className="flex max-w-[420px] flex-col gap-5">
          <span className="font-mono text-xs tracking-[.06em] text-primary">{DEMO_MODE ? "ABOUT DEMO SIGN-IN" : "ABOUT YOUR ACCOUNT"}</span>
          <h2 className="text-2xl font-semibold tracking-[-.015em] [text-wrap:balance]">
            {DEMO_MODE ? "This screen shows the design, not real security." : "Your workspace is private by default."}
          </h2>
          <div className="flex flex-col gap-3.5 text-ink-2">
            {points.map(([icon, text]) => (
              <div key={icon} className="flex gap-3">
                <Icon name={icon} size={17} className="mt-0.5 text-primary" />
                <span>{text}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
