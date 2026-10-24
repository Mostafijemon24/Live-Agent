import type { TaskStatus } from "@/lib/api/types";

/** The prototype's dec().open rule: plans under review open the plan screen, everything else the detail page. */
export function taskHref(t: { id: string; status: TaskStatus }): string {
  return t.status === "awaiting_approval" || t.status === "planning" ? `/tasks/${t.id}/plan` : `/tasks/${t.id}`;
}

/** Example prompt used by the "Run a safe demo task" checklist item (prototype setupItems). */
export const WORDPRESS_EXAMPLE =
  "Audit my WordPress website for performance and SEO problems, prepare a report, and show me recommended fixes before changing anything.";
