"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError, type Me } from "@/lib/api";
import { Icon } from "@/components/ui/Icon";
import { Button, Modal } from "@/components/ui";

// ------------------------------------------------------------------ toasts
export type ToastTone = "info" | "success" | "danger";
interface ToastItem {
  id: number;
  text: string;
  tone: ToastTone;
}
interface UiCtx {
  toast: (text: string, tone?: ToastTone) => void;
  /** The prototype's "backend" modal: explains a feature that is not available yet. */
  notice: (title: string, body: string) => void;
  rail: boolean;
  setRail: (v: boolean) => void;
  compactRows: boolean;
}
const Ui = createContext<UiCtx | null>(null);
export function useUi(): UiCtx {
  const v = useContext(Ui);
  if (!v) throw new Error("useUi outside provider");
  return v;
}

function readPref(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function UiProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [modal, setModal] = useState<{ title: string; body: string } | null>(null);
  const [rail, setRailState] = useState(false);
  const [compactRows, setCompact] = useState(false);

  useEffect(() => {
    // Only harmless UI preferences are stored locally — never credentials or data.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate from localStorage after mount
    setRailState(readPref("steward.rail"));
    setCompact(readPref("steward.compact"));
  }, []);

  const toast = useCallback((text: string, tone: ToastTone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  const notice = useCallback((title: string, body: string) => setModal({ title, body }), []);
  const setRail = useCallback((v: boolean) => {
    setRailState(v);
    try {
      localStorage.setItem("steward.rail", v ? "1" : "0");
    } catch {
      /* storage unavailable */
    }
  }, []);

  const value = useMemo(() => ({ toast, notice, rail, setRail, compactRows }), [toast, notice, rail, setRail, compactRows]);
  const TC = { success: "#75E0A7", danger: "#FDA29B", info: "#A4BCFD" };
  const TI = { success: "circle-check", danger: "circle-alert", info: "info" };

  return (
    <Ui.Provider value={value}>
      {children}
      {modal && (
        <Modal
          title={modal.title}
          onClose={() => setModal(null)}
          footer={
            <Button variant="primary" onClick={() => setModal(null)} className="px-4">
              Got it
            </Button>
          }
        >
          <div className="flex gap-3 p-5">
            <Icon name="server" size={20} className="mt-0.5 text-warning" />
            <p className="text-ink-2 [text-wrap:pretty]">{modal.body}</p>
          </div>
        </Modal>
      )}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-5 bottom-5 z-[90] flex flex-col items-end gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto flex max-w-[420px] items-start gap-2.5 rounded-[10px] bg-ink px-3.5 py-3 text-[13.5px] text-white shadow-[0_12px_24px_-8px_rgba(16,24,40,.35)]"
          >
            <Icon name={TI[t.tone]} size={16} className="mt-0.5" style={{ color: TC[t.tone] }} />
            <span className="flex-1 [text-wrap:pretty]">{t.text}</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
              className="border-0 bg-transparent px-0.5 text-line-strong"
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </Ui.Provider>
  );
}

// ------------------------------------------------------------------ session
interface SessionCtx {
  me: Me | null;
  loading: boolean;
  /** true when /me answered 401 — not signed in. */
  signedOut: boolean;
  error: unknown;
  refresh: () => Promise<unknown>;
  setMe: (me: Me | null) => void;
  logout: () => Promise<void>;
}
const Session = createContext<SessionCtx | null>(null);
export function useSession(): SessionCtx {
  const v = useContext(Session);
  if (!v) throw new Error("useSession outside provider");
  return v;
}

function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(),
    retry: (count, err) => !(isApiError(err) && (err.status === 401 || err.status === 403)) && count < 2,
    staleTime: 60_000,
  });
  const signedOut = isApiError(q.error) && q.error.status === 401;
  const setMe = useCallback((me: Me | null) => qc.setQueryData(["me"], me), [qc]);
  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      qc.clear();
    }
  }, [qc]);
  const value = useMemo<SessionCtx>(
    () => ({ me: q.data ?? null, loading: q.isLoading, signedOut, error: signedOut ? null : q.error, refresh: q.refetch, setMe, logout }),
    [q.data, q.isLoading, signedOut, q.error, q.refetch, setMe, logout],
  );
  return <Session.Provider value={value}>{children}</Session.Provider>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: (count, err) => !(isApiError(err) && err.status >= 400 && err.status < 500) && count < 2,
          },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <UiProvider>
        <SessionProvider>{children}</SessionProvider>
      </UiProvider>
    </QueryClientProvider>
  );
}
