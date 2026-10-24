import { describe, expect, it } from "vitest";
import {
  APPROVAL_CATEGORY,
  CLASSIFICATION,
  EXECUTION_STATE,
  IMPACT,
  INTEGRATION_STATUS,
  POLICY_OUTCOME,
  STEP_STATE,
} from "./labels";

// Keep in sync with lib/api/types.ts (and the backend enums). A missing label would render "undefined".
const CLASSES = ["public", "internal", "confidential", "unknown"];
const STEP_STATES = ["not_started", "in_progress", "done", "failed", "paused", "waiting_for_input", "skipped", "cancelled", "awaiting_approval", "blocked", "rejected"];
const EXEC = ["not_executed", "blocked_until_phase3", "simulated", "pending_execution", "executed", "execution_failed", "invalidated"];
const CATEGORIES = ["external_transfer", "production_change", "publish", "send_message", "record_deletion", "permission_change", "code_execution"];
const INTEG = ["demo", "not_connected", "backend_required", "connected", "error"];
const IMPACTS = ["none", "workspace_write", "external_read", "external_transfer", "publish", "send_message", "production_change", "sensitive_change", "delete", "permission_change"];

describe("labels cover every wire value", () => {
  it.each([
    ["classification", CLASSIFICATION, CLASSES],
    ["step state", STEP_STATE, STEP_STATES],
    ["execution state", EXECUTION_STATE, EXEC],
    ["approval category", APPROVAL_CATEGORY, CATEGORIES],
    ["integration status", INTEGRATION_STATUS, INTEG],
    ["impact", IMPACT, IMPACTS],
    ["policy outcome", POLICY_OUTCOME, ["allow", "require_approval", "deny"]],
  ])("%s", (_name, table, values) => {
    expect(Object.keys(table).sort()).toEqual([...values].sort());
    for (const v of values) expect((table as Record<string, unknown>)[v]).toBeTruthy();
  });

  it("uses plain, honest wording for the sensitive cases", () => {
    expect(CLASSIFICATION.confidential.label).toMatch(/never leaves without approval/i);
    expect(CLASSIFICATION.unknown.label).toMatch(/sharing blocked/i);
    expect(STEP_STATE.blocked.label).toBe("Blocked by policy");
    expect(EXECUTION_STATE.pending_execution.label).toBe("Approved — waiting to run");
    expect(EXECUTION_STATE.executed.label).toBe("Used");
    expect(EXECUTION_STATE.invalidated.label).toBe("No longer valid — action changed");
  });
});
