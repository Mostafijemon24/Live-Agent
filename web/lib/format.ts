// Formatting helpers. Dates come from the API as ISO strings in UTC and are
// shown in the user's browser locale, matching the prototype's "Oct 24, 09:12".

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n: number) => String(n).padStart(2, "0");

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtTimeSec(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** "09:20", "Yesterday", or "Oct 22" — used by notifications. */
export function fmtRelativeDay(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((startOf(now) - startOf(d)) / 86400000);
  if (diff <= 0) return fmtTime(iso);
  if (diff === 1) return "Yesterday";
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function fmtExpires(iso: string | null): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "Expired";
  const h = Math.round(ms / 3600000);
  if (h < 48) return `Expires in ${h} h`;
  return `Expires in ${Math.round(h / 24)} days`;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Title suggestion from a prompt — ported from the prototype's suggest(). */
export function suggestTitle(prompt: string): string {
  const w = prompt.replace(/[^\w\s&'-]/g, "").split(/\s+/).filter(Boolean);
  const t = w.slice(0, 7).join(" ");
  return t.charAt(0).toUpperCase() + t.slice(1) + (w.length > 7 ? "…" : "");
}

/** Task-type guess for the Overview quick task — ported from the prototype's guessType(). */
export function guessType(p: string) {
  if (/wordpress|website|plugin|\bsite\b/i.test(p)) return "website" as const;
  if (/seo|meta|content|blog|article/i.test(p)) return "seo_content" as const;
  if (/\bcode\b|test|function|bug/i.test(p)) return "code" as const;
  if (/csv|file|spreadsheet|excel/i.test(p)) return "file_analysis" as const;
  if (/browser|form|click/i.test(p)) return "browser" as const;
  if (/research|compare|competitor/i.test(p)) return "research" as const;
  return "custom" as const;
}

export const emailOk = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
export const passwordOk = (v: string) => v.length >= 10 && /\d/.test(v) && v.length <= 128;
