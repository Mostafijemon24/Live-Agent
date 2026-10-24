"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSession, useUi } from "@/lib/session";
import { Icon } from "@/components/ui/Icon";
import { IconButton, Skeleton, cx } from "@/components/ui";
import { DEMO_MODE } from "@/lib/api";

export const NAV: { href: string; label: string; icon: string; match?: (p: string) => boolean }[] = [
  { href: "/overview", label: "Overview", icon: "house" },
  { href: "/tasks/new", label: "New task", icon: "sparkles", match: (p) => p === "/tasks/new" || /^\/tasks\/[^/]+\/plan$/.test(p) },
  { href: "/tasks", label: "Tasks", icon: "list-checks", match: (p) => p === "/tasks" || (/^\/tasks\/[^/]+$/.test(p) && p !== "/tasks/new") },
  { href: "/approvals", label: "Approvals", icon: "shield-check" },
  { href: "/files", label: "Files & Knowledge", icon: "folder" },
  { href: "/automations", label: "Automations", icon: "repeat" },
  { href: "/integrations", label: "Integrations", icon: "plug" },
  { href: "/reports", label: "Reports & Activity", icon: "activity" },
  { href: "/security", label: "Security & Privacy", icon: "lock" },
  { href: "/settings", label: "Settings", icon: "settings" },
  { href: "/help", label: "Help & Getting Started", icon: "life-buoy" },
];

/** Persistent status strip — the prototype's DEMO MODE bar, honest in both modes. */
export function StatusStrip() {
  return (
    <div role="status" className="relative z-30 flex flex-wrap items-center justify-center gap-2.5 bg-ink px-4 py-[7px] text-center text-[12.5px] text-white">
      {DEMO_MODE ? (
        <>
          <span className="font-mono font-medium tracking-[.06em]">DEMO MODE</span>
          <span className="text-line-strong">No real AI tasks are being executed. Everything shown is sample data in this browser.</span>
        </>
      ) : (
        <>
          <span className="font-mono font-medium tracking-[.06em]">PREVIEW</span>
          <span className="text-line-strong">The AI agent engine is not installed yet. Tasks are saved securely but nothing is executed.</span>
        </>
      )}
    </div>
  );
}

function useActive() {
  const p = usePathname() ?? "";
  return (n: (typeof NAV)[number]) => (n.match ? n.match(p) : p === n.href || p.startsWith(n.href + "/"));
}

function useShellData() {
  return useQuery({ queryKey: ["dashboard"], queryFn: () => api.dashboard(), staleTime: 15_000 });
}

function Logo() {
  return (
    <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-primary text-white">
      <Icon name="shield-check" size={17} />
    </span>
  );
}

function Sidebar() {
  const { rail, setRail } = useUi();
  const isActive = useActive();
  const { data } = useShellData();
  const pending = data ? data.counts.pending_actions : 0;
  const setup = data?.setup;
  const setupDone = setup ? Object.values(setup).filter(Boolean).length : 0;

  return (
    <aside
      aria-label="Main navigation"
      className="sticky top-0 flex h-screen shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-line bg-surface px-2.5 py-3.5 transition-[width] duration-150"
      style={{ width: rail ? 64 : 248 }}
    >
      <div className="flex items-center justify-between gap-1.5 px-1 pb-3.5 pt-0.5">
        <Link href="/overview" aria-label="Steward overview" className="flex items-center gap-2.5 p-0.5 text-ink hover:no-underline">
          <Logo />
          {!rail && <span className="text-base font-semibold">Steward</span>}
        </Link>
        {!rail && <IconButton icon="panel-left-close" label="Collapse sidebar" size={30} iconSize={17} onClick={() => setRail(true)} className="text-muted" />}
      </div>
      {rail && (
        <button type="button" onClick={() => setRail(false)} aria-label="Expand sidebar" title="Expand sidebar" className="mb-1.5 grid h-9 place-items-center rounded-lg border-0 bg-transparent text-muted hover:bg-line-soft">
          <Icon name="panel-left-open" size={17} />
        </button>
      )}
      <nav className="flex flex-col gap-0.5">
        {NAV.map((n) => {
          const active = isActive(n);
          const badge = n.href === "/approvals" && pending > 0;
          return (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active ? "page" : undefined}
              title={n.label}
              className={cx(
                "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm hover:no-underline",
                active ? "bg-primary-soft font-medium text-primary hover:text-primary" : "text-ink-2 hover:bg-line-soft hover:text-ink-2",
              )}
            >
              <Icon name={n.icon} size={17} className={active ? "" : "text-muted"} />
              {!rail && <span className="flex-1 truncate">{n.label}</span>}
              {badge && (
                <span
                  className="grid h-5 min-w-5 place-items-center rounded-[10px] px-1.5 text-[11.5px] font-semibold"
                  style={active ? { background: "#3448C5", color: "#FFF" } : { background: "#FFF6ED", color: "#B54708" }}
                >
                  {pending}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="flex-1" />
      {!rail && (
        <Link href="/overview" className="mt-3 flex flex-col gap-2 rounded-[10px] border border-line bg-subtle p-3 text-left text-ink hover:border-line-strong hover:no-underline">
          <span className="flex justify-between text-[12.5px] font-medium">
            <span>Workspace setup</span>
            <span className="text-muted">{setupDone} of 4</span>
          </span>
          <span className="block h-1 overflow-hidden rounded-sm bg-track">
            <span className="block h-full bg-primary" style={{ width: `${(setupDone / 4) * 100}%` }} />
          </span>
        </Link>
      )}
    </aside>
  );
}

function MobileNav({ onClose }: { onClose: () => void }) {
  const isActive = useActive();
  const { data } = useShellData();
  const pending = data ? data.counts.pending_actions : 0;
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[60] flex">
      <div onClick={onClose} className="absolute inset-0 bg-[rgba(16,24,40,.45)]" />
      <aside aria-label="Main navigation" role="dialog" aria-modal="true" className="relative flex h-full w-[min(300px,86vw)] flex-col gap-0.5 overflow-y-auto bg-surface px-2.5 py-3.5 shadow-[0_12px_32px_rgba(16,24,40,.2)]">
        <div className="flex items-center justify-between px-1 pb-3.5 pt-0.5">
          <div className="flex items-center gap-2.5">
            <Logo />
            <span className="text-base font-semibold">Steward</span>
          </div>
          <IconButton icon="x" label="Close navigation" size={34} onClick={onClose} className="text-ink" />
        </div>
        {NAV.map((n) => {
          const active = isActive(n);
          return (
            <Link
              key={n.href}
              href={n.href}
              onClick={onClose}
              aria-current={active ? "page" : undefined}
              className={cx("flex h-11 items-center gap-3 rounded-lg px-3 text-[15px] hover:no-underline", active ? "bg-primary-soft font-medium text-primary" : "text-ink-2")}
            >
              <Icon name={n.icon} size={18} />
              <span className="flex-1">{n.label}</span>
              {n.href === "/approvals" && pending > 0 && (
                <span className="grid h-5 min-w-5 place-items-center rounded-[10px] bg-warning-soft px-1.5 text-[11.5px] font-semibold text-warning">{pending}</span>
              )}
            </Link>
          );
        })}
      </aside>
    </div>
  );
}

function Popover({ open, onClose, children, align }: { open: boolean; onClose: () => void; children: ReactNode; align: "left" | "right" }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.parentElement?.contains(e.target as Node)) onClose();
    };
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", h);
    window.addEventListener("keydown", k);
    return () => {
      document.removeEventListener("mousedown", h);
      window.removeEventListener("keydown", k);
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div ref={ref} role="menu" className={cx("absolute top-[42px] z-40 rounded-[10px] border border-line bg-surface p-1.5 shadow-menu", align === "left" ? "left-0 w-[260px]" : "right-0 w-[240px]")}>
      {children}
    </div>
  );
}

function Header({ onOpenNav }: { onOpenNav: () => void }) {
  const router = useRouter();
  const { me, logout } = useSession();
  const { toast } = useUi();
  const { data } = useShellData();
  const [pop, setPop] = useState<"ws" | "user" | null>(null);
  const [q, setQ] = useState("");
  const unread = data?.unread_notifications ?? 0;
  const wsName = me?.workspace.name ?? "Workspace";
  const initials = (me?.user.name ?? "?")
    .split(/\s+/)
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    router.push(`/tasks?q=${encodeURIComponent(q)}`);
  };
  const signOut = async () => {
    setPop(null);
    try {
      await logout();
      toast(DEMO_MODE ? "Signed out of the demo workspace." : "You have been signed out.", "info");
    } finally {
      router.push("/login");
    }
  };
  const item = "flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2.5 py-2 text-left text-sm text-ink hover:bg-line-soft hover:no-underline";

  return (
    <header className="sticky top-0 z-20 flex h-[60px] items-center gap-2.5 border-b border-line bg-surface px-[clamp(12px,2.5vw,24px)]">
      <button type="button" onClick={onOpenNav} aria-label="Open navigation" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-surface min-[980px]:hidden">
        <Icon name="menu" size={18} />
      </button>
      <div className="relative">
        <button
          type="button"
          onClick={() => setPop(pop === "ws" ? null : "ws")}
          aria-haspopup="menu"
          aria-expanded={pop === "ws"}
          className="flex h-9 items-center gap-2 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 text-sm font-medium hover:bg-subtle"
        >
          <span className="grid h-5 w-5 place-items-center rounded-[5px] bg-track text-[11px] font-semibold text-ink-3">{wsName[0]?.toUpperCase()}</span>
          <span className="hidden min-[760px]:inline">{wsName}</span>
          <Icon name="chevrons-up-down" size={14} className="text-muted" />
        </button>
        <Popover open={pop === "ws"} onClose={() => setPop(null)} align="left">
          <div className="px-2.5 py-2 text-xs text-muted">Workspaces</div>
          <div className="flex items-center gap-2.5 rounded-md bg-subtle px-2.5 py-2">
            <span className="grid h-[22px] w-[22px] place-items-center rounded-[5px] bg-track text-[11px] font-semibold">{wsName[0]?.toUpperCase()}</span>
            <span className="flex-1 font-medium">{wsName}</span>
            <Icon name="check" className="text-primary" />
          </div>
          <button type="button" role="menuitem" disabled className={cx(item, "text-faint hover:bg-transparent")}>
            <Icon name="plus" size={15} />
            Add workspace<span className="ml-auto text-[11.5px]">Coming later</span>
          </button>
        </Popover>
      </div>
      <form onSubmit={submit} role="search" className="relative hidden max-w-[420px] flex-1 min-[640px]:block">
        <Icon name="search" size={15} className="absolute left-[11px] top-[11px] text-faint" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search tasks"
          placeholder="Search tasks…"
          className="h-9 w-full rounded-lg border border-line bg-subtle pl-[34px] pr-3 text-sm"
        />
      </form>
      <div className="flex-1" />
      {DEMO_MODE ? (
        <span title="Demo data — no backend connected" className="inline-flex h-[26px] items-center gap-1.5 whitespace-nowrap rounded-md bg-warning-soft px-[9px] text-xs font-medium text-warning">
          <Icon name="flask-conical" size={13} />
          Demo
        </span>
      ) : (
        <span title="The AI agent engine is not installed yet (Phase 3)" className="inline-flex h-[26px] items-center gap-1.5 whitespace-nowrap rounded-md bg-warning-soft px-[9px] text-xs font-medium text-warning">
          <Icon name="server" size={13} />
          <span className="hidden min-[480px]:inline">Agent not installed</span>
        </span>
      )}
      <Link href="/help" aria-label="Help" title="Help" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-ink-3 hover:bg-line-soft hover:text-ink-3">
        <Icon name="circle-help" size={18} />
      </Link>
      <Link
        href="/notifications"
        aria-label={`Notifications, ${unread} unread`}
        title="Notifications"
        className="relative grid h-9 w-9 shrink-0 place-items-center rounded-lg text-ink-3 hover:bg-line-soft hover:text-ink-3"
      >
        <Icon name="bell" size={18} />
        {unread > 0 && (
          <span className="absolute right-0 top-0.5 grid h-[15px] min-w-[15px] place-items-center rounded-lg bg-danger px-[3px] text-[9.5px] font-semibold leading-none text-white shadow-[0_0_0_2px_#fff]">
            {unread}
          </span>
        )}
      </Link>
      <div className="relative">
        <button
          type="button"
          onClick={() => setPop(pop === "user" ? null : "user")}
          aria-haspopup="menu"
          aria-expanded={pop === "user"}
          aria-label="Account menu"
          className="h-[34px] w-[34px] shrink-0 rounded-full border-0 bg-primary text-[13px] font-semibold text-white"
        >
          {initials}
        </button>
        <Popover open={pop === "user"} onClose={() => setPop(null)} align="right">
          <div className="mb-1 border-b border-line-soft px-2.5 pb-2.5 pt-2">
            <div className="truncate font-semibold">{me?.user.name}</div>
            <div className="truncate text-[12.5px] text-muted">{DEMO_MODE ? "Sample profile — not a real account" : me?.user.email}</div>
          </div>
          <Link role="menuitem" href="/settings" onClick={() => setPop(null)} className={item}>
            <Icon name="user" size={15} className="text-muted" />
            Profile &amp; settings
          </Link>
          <Link role="menuitem" href="/security" onClick={() => setPop(null)} className={item}>
            <Icon name="lock" size={15} className="text-muted" />
            Security &amp; privacy
          </Link>
          <button type="button" role="menuitem" onClick={signOut} className={item}>
            <Icon name="log-out" size={15} className="text-muted" />
            Sign out
          </button>
        </Popover>
      </div>
    </header>
  );
}

/** Authenticated layout. Redirects to /login when the server says the session is missing or expired. */
export function AppShell({ children }: { children: ReactNode }) {
  const { me, loading, signedOut, error, refresh } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (signedOut) router.replace(`/login?next=${encodeURIComponent(pathname ?? "/overview")}`);
  }, [signedOut, router, pathname]);

  if (loading || signedOut) {
    return (
      <div className="mx-auto max-w-[480px] p-10">
        <Skeleton />
      </div>
    );
  }
  if (error || !me) {
    return (
      <div className="mx-auto flex max-w-[480px] flex-col items-start gap-2 p-10">
        <Icon name="wifi-off" size={20} className="text-danger" />
        <div className="font-semibold">We couldn&apos;t reach the server</div>
        <p className="text-[13.5px] text-muted">Nothing was changed. Check your connection and try again.</p>
        <button type="button" onClick={() => refresh()} className="h-8 rounded-[7px] border border-line-strong bg-surface px-3 text-[13px] font-medium">
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-start">
      <div className="hidden min-[980px]:block">
        <Sidebar />
      </div>
      <div className="flex min-h-[calc(100vh-34px)] min-w-0 flex-1 flex-col">
        <Header onOpenNav={() => setNavOpen(true)} />
        <main className="mx-auto w-full max-w-[1280px] flex-1 p-[clamp(16px,3vw,32px)]">{children}</main>
      </div>
      {navOpen && <MobileNav onClose={() => setNavOpen(false)} />}
    </div>
  );
}
