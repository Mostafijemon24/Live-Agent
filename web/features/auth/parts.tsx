"use client";

import { sameOriginPath } from "@/lib/safe-path";

import { forwardRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { FieldError, Icon, TextInput, cx } from "@/components/ui";
import { isApiError } from "@/lib/api";

/** Page heading used on every auth card: 26px title + muted lead. */
export function AuthHeading({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div>
      <h1 className="text-[26px] font-semibold tracking-[-.015em]">{title}</h1>
      {children && <p className="mt-1.5 text-muted [text-wrap:pretty]">{children}</p>}
    </div>
  );
}

/** 44px rounded icon tile shown above success / info states. */
export function StateIcon({ icon, tone }: { icon: string; tone: "success" | "primary" | "danger" }) {
  const cls = { success: "bg-success-soft text-success", primary: "bg-primary-soft text-primary", danger: "bg-danger-soft text-danger" }[tone];
  return (
    <div className={cx("grid h-11 w-11 place-items-center rounded-[10px]", cls)}>
      <Icon name={icon} size={22} />
    </div>
  );
}

/** Labelled field in the prototype's stacked style (label text, control, hint, error). */
export function AuthField({
  label,
  labelExtra,
  htmlFor,
  hint,
  error,
  errorId,
  children,
}: {
  label: ReactNode;
  labelExtra?: ReactNode;
  htmlFor: string;
  hint?: ReactNode;
  error?: string;
  errorId?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5 text-[13px] font-medium">
      {labelExtra ? (
        <span className="flex justify-between">
          <label htmlFor={htmlFor}>{label}</label>
          {labelExtra}
        </span>
      ) : (
        <label htmlFor={htmlFor}>{label}</label>
      )}
      {children}
      {hint && <span className="text-[12.5px] font-normal text-muted">{hint}</span>}
      {error && (
        <div className="-mt-1.5 font-normal">
          <FieldError id={errorId}>{error}</FieldError>
        </div>
      )}
    </div>
  );
}

/** Password input with the prototype's eye / eye-off visibility toggle. */
export const PasswordInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(function PasswordInput(
  { invalid, className, ...rest },
  ref,
) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <TextInput ref={ref} type={show ? "text" : "password"} invalid={invalid} className={cx("pr-11", className)} {...rest} />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute top-1 right-1 grid h-8 w-8 place-items-center rounded-md border-0 bg-transparent text-muted hover:bg-line-soft"
      >
        <Icon name={show ? "eye-off" : "eye"} size={16} />
      </button>
    </div>
  );
});

/** Full-width 42px primary action used by all auth forms. */
export function AuthButton({
  loading,
  variant = "primary",
  className,
  children,
  type = "button",
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; variant?: "primary" | "secondary" }) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        "flex h-[42px] w-full items-center justify-center gap-2 rounded-lg font-medium disabled:opacity-70",
        variant === "primary" ? "border-0 bg-primary text-[14.5px] text-white hover:bg-primary-hover" : "border border-line-strong bg-surface text-sm text-ink hover:bg-subtle",
        className,
      )}
      {...rest}
    >
      {loading && <Icon name="loader" size={16} spin />}
      {children}
    </button>
  );
}

export function SsoButton() {
  return (
    <button
      type="button"
      disabled
      title="Single sign-on is not configured"
      className="flex h-[42px] items-center justify-center gap-2 rounded-lg border border-line bg-subtle text-sm font-medium text-faint"
    >
      <Icon name="key-round" size={16} />
      Single sign-on — not configured
    </button>
  );
}

/** Form-level error box (invalid credentials, rate limited, expired link…). */
export function AuthAlert({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <div role="alert" className="flex gap-2.5 rounded-lg border border-danger-line bg-danger-soft px-3.5 py-3 text-[13.5px] text-danger">
      <Icon name="circle-alert" size={16} className="mt-0.5" />
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

export function OrDivider() {
  return (
    <div className="flex items-center gap-3 text-[12.5px] text-faint">
      <span className="h-px flex-1 bg-line" />
      or
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

/**
 * Split a thrown error into per-field messages (shown under inputs) and a
 * form-level message (shown in the alert box). The server's generic message
 * is shown as-is — it never reveals whether an email is registered.
 */
export function splitError(e: unknown, known: string[]): { fields: Record<string, string>; form: string } {
  if (isApiError(e)) {
    const all = e.fieldErrors();
    const fields: Record<string, string> = {};
    for (const k of known) if (all[k]) fields[k] = all[k];
    const unmatched = Object.keys(all).some((k) => !known.includes(k));
    let form = "";
    if (e.status === 429) form = e.message || "Too many attempts. Please wait a few minutes and try again.";
    else if (!Object.keys(fields).length || unmatched) form = e.requestId ? `${e.message} (Ref: ${e.requestId.slice(0, 8)})` : e.message;
    return { fields, form };
  }
  return { fields: {}, form: "We couldn't reach the server. Nothing was changed. Please try again." };
}

/** Only allow same-origin app paths after login (see lib/safe-path.ts). */
export function safeNext(next: string | null | undefined): string | null {
  return sameOriginPath(next);
}

/** Shared toast text for the placeholder Terms / Privacy links. */
export const PLACEHOLDER_LINK = "Placeholder link — replace with your real policy page.";
