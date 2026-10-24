"use client";

import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Icon } from "./Icon";
import type { BadgeMeta, Tone } from "@/lib/labels";
import { TONE } from "@/lib/labels";

export { Icon };

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

// ---------------------------------------------------------------- Button
type Variant = "primary" | "secondary" | "ghost" | "link" | "danger" | "danger-solid";
type Size = "xs" | "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: string;
  iconRight?: string;
  loading?: boolean;
}

const VARIANT: Record<Variant, string> = {
  primary: "border-0 bg-primary text-white hover:bg-primary-hover",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-subtle",
  ghost: "border-0 bg-transparent text-ink-3 hover:bg-line-soft",
  link: "border-0 bg-transparent text-primary hover:underline px-1",
  danger: "border border-danger-line bg-surface text-danger hover:bg-danger-soft",
  "danger-solid": "border-0 bg-danger text-white hover:bg-[#912018]",
};
// Heights from the prototype: 30 (row actions), 34/36 (secondary), 38 (page actions), 44 (hero)
const SIZE: Record<Size, string> = {
  xs: "h-[30px] px-2.5 text-[13px] rounded-[7px] gap-1.5",
  sm: "h-[34px] px-3 text-[13.5px] rounded-lg gap-1.5",
  md: "h-[38px] px-3.5 text-sm rounded-lg gap-2",
  lg: "h-11 px-5 text-[15px] rounded-lg gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon, iconRight, loading, className, children, disabled, type = "button", ...rest },
  ref,
) {
  const iconSize = size === "lg" ? 16 : size === "md" ? 16 : 14;
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        "inline-flex items-center justify-center font-medium whitespace-nowrap transition-colors duration-150 disabled:opacity-50",
        variant !== "link" && SIZE[size],
        variant === "link" && "text-[13.5px]",
        VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Icon name="loader" size={iconSize} spin /> : icon ? <Icon name={icon} size={iconSize} /> : null}
      {children}
      {iconRight && <Icon name={iconRight} size={iconSize} />}
    </button>
  );
});

export function IconButton({
  icon,
  label,
  size = 36,
  iconSize = 18,
  className,
  ...rest
}: { icon: string; label: string; size?: number; iconSize?: number } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx("grid place-items-center rounded-lg border-0 bg-transparent text-ink-3 hover:bg-line-soft shrink-0", className)}
      style={{ width: size, height: size }}
      {...rest}
    >
      <Icon name={icon} size={iconSize} />
    </button>
  );
}

// ---------------------------------------------------------------- Badge
export function Badge({ meta, className, children }: { meta: Pick<BadgeMeta, "fg" | "bg"> & { icon?: string; label?: string }; className?: string; children?: ReactNode }) {
  return (
    <span
      className={cx("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap", className)}
      style={{ color: meta.fg, background: meta.bg }}
    >
      {meta.icon && <Icon name={meta.icon} size={13} />}
      {children ?? meta.label}
    </span>
  );
}

/** Dashed mono tag used for "DEMO DATA", "NOT ENFORCED" etc. */
export function MonoTag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("rounded border border-dashed border-line-strong px-1.5 py-px font-mono text-[11px] font-medium tracking-[.04em] text-muted", className)}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------- Layout
export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-[-.015em]">{title}</h1>
        {subtitle && <p className="mt-1 text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ className, children, as: As = "section", ...rest }: { className?: string; children: ReactNode; as?: "section" | "div" | "article" } & Record<string, unknown>) {
  return (
    <As className={cx("rounded-[10px] border border-line bg-surface", className)} {...rest}>
      {children}
    </As>
  );
}

export function CardHeader({ title, id, action, className }: { title: ReactNode; id?: string; action?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex items-center justify-between gap-3 border-b border-line px-5 py-4", className)}>
      <h2 id={id} className="text-[15px] font-semibold">
        {title}
      </h2>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- Banners
export function Banner({ tone, icon, title, children, className, role }: { tone: Tone; icon?: string; title?: ReactNode; children?: ReactNode; className?: string; role?: string }) {
  const t = TONE[tone];
  return (
    <div
      role={role}
      className={cx("flex gap-2.5 rounded-lg border px-3.5 py-3 text-[13.5px]", className)}
      style={{ background: t.bg, borderColor: t.border, color: tone === "info" ? "#1F2A7A" : t.fg }}
    >
      {icon && <Icon name={icon} size={16} className="mt-0.5" style={{ color: t.fg }} />}
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold" style={{ color: t.fg }}>{title}</div>}
        {children && <div className={title ? "mt-0.5" : ""} style={{ color: title ? "#344054" : undefined }}>{children}</div>}
      </div>
    </div>
  );
}

export function FieldError({ id, children }: { id?: string; children?: ReactNode }) {
  if (!children) return null;
  return (
    <div id={id} role="alert" className="mt-1.5 flex items-center gap-1.5 text-[12.5px] text-danger">
      <Icon name="circle-alert" size={14} />
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- Form controls
const controlBase = "w-full rounded-lg border bg-surface text-sm placeholder:text-faint";

export function Label({ htmlFor, children, hint }: { htmlFor?: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between gap-2 text-[13.5px] font-medium">
      <span>{children}</span>
      {hint && <span className="text-xs font-normal text-muted">{hint}</span>}
    </label>
  );
}

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(function TextInput(
  { invalid, className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cx(controlBase, "h-10 px-3", invalid ? "border-danger" : "border-line-strong", className)}
      {...rest}
    />
  );
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }>(function TextArea(
  { invalid, className, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cx(controlBase, "resize-y px-3 py-2.5 leading-[1.5]", invalid ? "border-danger" : "border-line-strong", className)}
      {...rest}
    />
  );
});

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(controlBase, "h-9 border-line-strong px-2.5", className)} {...rest}>
      {children}
    </select>
  );
}

export function Checkbox({ checked, onChange, children, id }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; id?: string }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-2.5 text-[13.5px]">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-[3px] accent-primary" />
      <span>{children}</span>
    </label>
  );
}

/** role="switch" toggle — the prototype's sw() helper. */
export function Switch({ on, onToggle, label, disabled }: { on: boolean; onToggle: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className="flex h-[22px] w-[38px] shrink-0 items-center rounded-full border-0 p-0.5 transition-colors disabled:opacity-50"
      style={{ background: on ? "#3448C5" : "#D0D5DD", justifyContent: on ? "flex-end" : "flex-start" }}
    >
      <span className="block h-[18px] w-[18px] rounded-full bg-white shadow-[0_1px_2px_rgba(16,24,40,.2)]" />
    </button>
  );
}

/** Selectable chip / option card — the prototype's chip() helper. */
export function Chip({
  on,
  onClick,
  children,
  className,
  disabled,
  role,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  role?: "radio" | "checkbox";
}) {
  return (
    <button
      type="button"
      role={role}
      aria-checked={role ? on : undefined}
      aria-pressed={role ? undefined : on}
      disabled={disabled}
      onClick={onClick}
      className={cx("rounded-lg border text-left text-[13.5px] transition-colors disabled:opacity-55", className)}
      style={{ background: on ? "#EEF1FC" : "#FFFFFF", borderColor: on ? "#3448C5" : "#E4E7EC", color: on ? "#3448C5" : "#344054" }}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- Overlays
function useEscape(onClose: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
}

function useFocusOnOpen<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const first = el?.querySelector<HTMLElement>("input, textarea, select, button:not([aria-label='Close'])");
    (first ?? el)?.focus();
    return () => prev?.focus?.();
  }, []);
  return ref;
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  maxWidth = 540,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  maxWidth?: number;
}) {
  useEscape(onClose);
  const ref = useFocusOnOpen<HTMLDivElement>();
  const id = useId();
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <div onClick={onClose} className="absolute inset-0 bg-[rgba(16,24,40,.5)]" />
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        className="relative max-h-[calc(100vh-32px)] w-full overflow-auto rounded-xl bg-surface shadow-[0_24px_48px_-12px_rgba(16,24,40,.3)]"
        style={{ maxWidth }}
      >
        <div className="sticky top-0 z-[1] flex items-center justify-between gap-3 border-b border-line bg-surface px-5 py-[18px]">
          <h2 id={id} className="text-[17px] font-semibold">
            {title}
          </h2>
          <IconButton icon="x" label="Close" size={32} iconSize={17} onClick={onClose} className="text-ink" />
        </div>
        {children}
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</div>}
      </div>
    </div>
  );
}

export function Drawer({
  label,
  onClose,
  header,
  children,
  footer,
}: {
  label: string;
  onClose: () => void;
  header: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEscape(onClose);
  const ref = useFocusOnOpen<HTMLElement>();
  return (
    <div className="fixed inset-0 z-[70] flex justify-end">
      <div onClick={onClose} className="absolute inset-0 bg-[rgba(16,24,40,.35)]" />
      <aside
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className="relative flex h-full w-[min(440px,100%)] flex-col overflow-auto bg-surface shadow-[-12px_0_32px_-12px_rgba(16,24,40,.25)]"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-5 py-4">
          {header}
          <IconButton icon="x" label="Close" size={32} iconSize={17} onClick={onClose} className="text-ink" />
        </div>
        <div className="flex flex-col gap-[18px] p-5">{children}</div>
        {footer && <div className="mt-auto flex flex-wrap justify-between gap-2 border-t border-line px-5 py-3.5">{footer}</div>}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- States
export function Skeleton({ lines = 4, className }: { lines?: number; className?: string }) {
  const widths = ["50%", "90%", "75%", "60%", "80%", "40%"];
  return (
    <div aria-busy="true" aria-live="polite" className={cx("flex flex-col gap-2.5", className)}>
      <span className="sr-only">Loading…</span>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-3 animate-pulse-soft rounded bg-track" style={{ width: widths[i % widths.length] }} />
      ))}
    </div>
  );
}

export function EmptyState({ icon = "inbox", title, children, action, className }: { icon?: string; title: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex flex-col items-center gap-2 px-5 py-10 text-center", className)}>
      <Icon name={icon} size={22} className="text-muted" />
      <div className="font-semibold">{title}</div>
      {children && <div className="max-w-[420px] text-[13.5px] text-muted">{children}</div>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/** Load-error block with a retry that really re-requests — never fakes success. */
export function ErrorState({ error, onRetry, retrying, title = "We couldn't load this" }: { error: unknown; onRetry?: () => void; retrying?: boolean; title?: string }) {
  const msg = (error as { message?: string })?.message ?? "The server didn't respond. Nothing was changed.";
  const rid = (error as { requestId?: string | null })?.requestId;
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-[10px] border border-line bg-surface p-[18px]">
      <Icon name="wifi-off" size={20} className="text-danger" />
      <div className="font-semibold">{title}</div>
      <div className="text-[13.5px] text-muted">
        {msg}
        {rid ? <span className="font-mono"> · Ref {rid.slice(0, 8)}</span> : null}
      </div>
      {onRetry && (
        <Button size="xs" loading={retrying} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Icon name="loader" size={size} spin label="Loading" />;
}

/** Definition list in the prototype's two-column grid style. */
export function DefList({ items, className }: { items: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <dl className={cx("m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13.5px]", className)}>
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="m-0 min-w-0">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
