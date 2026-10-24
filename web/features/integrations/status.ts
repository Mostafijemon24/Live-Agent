import type { Integration } from "@/lib/api/types";
import { INTEGRATION_STATUS, type BadgeMeta } from "@/lib/labels";

const NOT_BUILT: BadgeMeta = { label: "Not built yet", fg: "#475467", bg: "#F2F4F7", icon: "circle-dashed" };
const CHECKING: BadgeMeta = { label: "Checking…", fg: "#175CD3", bg: "#EFF8FF", icon: "loader" };

/** WordPress is "checking" between connect and the worker's verification result. */
export function isChecking(i: Integration): boolean {
  return i.key === "wordpress" && i.status === "not_connected" && !!i.site_url;
}

export function integrationBadge(i: Integration): BadgeMeta {
  if (!i.operational && i.key !== "ai_provider" && i.status !== "demo") return NOT_BUILT;
  if (isChecking(i)) return CHECKING;
  return INTEGRATION_STATUS[i.status];
}
