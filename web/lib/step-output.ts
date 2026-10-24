/**
 * Turns a tool's step output (untrusted data: web page text, file contents, model output)
 * into plain "key: value" lines for display. Never produces HTML; React escapes the text.
 * Keys starting with "_" are internal and skipped. Output is capped in depth, items and length.
 */
export function outputLines(output: Record<string, unknown> | null | undefined, maxLines = 60): string[] {
  if (!output) return [];
  const lines: string[] = [];
  const clip = (s: string) => (s.length > 300 ? s.slice(0, 299) + "…" : s);
  const fmt = (v: unknown): string => {
    if (v === null || v === undefined) return "—";
    if (typeof v === "string") return clip(v.replace(/\s+/g, " "));
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
    return clip(JSON.stringify(v));
  };
  const walk = (obj: Record<string, unknown>, prefix: string, depth: number) => {
    for (const [k, v] of Object.entries(obj)) {
      if (lines.length >= maxLines) return;
      if (k.startsWith("_")) continue;
      const key = prefix + k.replace(/_/g, " ");
      if (Array.isArray(v) && depth < 2) {
        lines.push(`${key}: ${fmt(v)}`);
        for (const item of v.slice(0, 10)) {
          if (lines.length >= maxLines) return;
          if (item && typeof item === "object" && !Array.isArray(item)) {
            lines.push(
              "  • " +
                Object.entries(item as Record<string, unknown>)
                  .filter(([ik]) => !ik.startsWith("_"))
                  .map(([ik, iv]) => `${ik.replace(/_/g, " ")}: ${fmt(iv)}`)
                  .join(" · "),
            );
          } else lines.push(`  • ${fmt(item)}`);
        }
      } else if (v && typeof v === "object" && !Array.isArray(v) && depth < 2) {
        walk(v as Record<string, unknown>, `${key} › `, depth + 1);
      } else lines.push(`${key}: ${fmt(v)}`);
    }
  };
  walk(output, "", 0);
  if (lines.length >= maxLines) lines.push("… (more in the run log / report)");
  return lines;
}
