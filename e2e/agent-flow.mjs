// End-to-end agent flow against the REAL backend and workers (not demo mode).
// Prereqs: API on :8000, web on :3000, the four workers running (python -m app.workers ...),
// MODEL_PROVIDER=mock (or a real local model), and a test site reachable by the tools worker.
// Development only: EGRESS_ALLOW_PRIVATE_NETWORKS/EGRESS_ALLOW_HTTP=true so the tools worker may
// read SITE_URL on this machine.
// Usage: node e2e/agent-flow.mjs [--shots <dir>]
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.WEB_URL ?? "http://localhost:3000";
const SITE = process.env.SITE_URL ?? "http://acme-demo.test:8099";
const SITE_HOST = new URL(SITE).hostname;
const OUTBOX = process.env.MAIL_OUTBOX_DIR ?? path.resolve("api/var/mail-outbox");
const shotsIdx = process.argv.indexOf("--shots");
const SHOTS = shotsIdx > 0 ? process.argv[shotsIdx + 1] : null;
const email = `agent-e2e-${Date.now()}@example.com`;
const password = "e2e-password-123";
const steps = [];
const consoleErrors = [];

function latestLink(to, route) {
  const files = fs.readdirSync(OUTBOX).filter((f) => f.endsWith(".eml")).sort();
  for (const f of files.reverse()) {
    const raw = fs.readFileSync(path.join(OUTBOX, f), "utf8");
    if (!raw.includes(`To: ${to}`)) continue;
    const m = raw.replace(/=\r?\n/g, "").match(new RegExp(`${route}\\?token=([A-Za-z0-9_-]+)`));
    if (m) return `${route}?token=${m[1]}`;
  }
  throw new Error(`no ${route} mail for ${to}`);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
const page = await ctx.newPage();
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(String(e)));
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

async function shot(name) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

async function step(name, fn) {
  try {
    await fn();
    steps.push(["PASS", name]);
  } catch (e) {
    steps.push(["FAIL", name, String(e.message).split("\n")[0]]);
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `FAIL-${name.replace(/\W+/g, "-")}.png`), fullPage: true });
    throw e;
  }
}

/** Same-origin API call from the signed-in page (session cookie + CSRF header). */
async function api(method, url, body) {
  return page.evaluate(
    async ([method, url, body]) => {
      const csrf = (document.cookie.match(/(?:^|; )(?:__Host-)?stw_csrf=([^;]+)/) || [])[1] || "";
      const r = await fetch("/api/v1" + url, {
        method,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      let data = null;
      try { data = await r.json(); } catch {}
      return { status: r.status, data };
    },
    [method, url, body],
  );
}

async function waitFor(fn, what, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  let last;
  while (Date.now() < end) {
    last = await fn();
    if (last) return last;
    await page.waitForTimeout(500);
  }
  throw new Error(`timed out waiting for ${what}`);
}

const taskState = async (id) => (await api("GET", `/tasks/${id}`)).data;

try {
  await step("register, verify and sign in", async () => {
    await page.goto(BASE + "/register");
    await page.getByLabel(/full name|your name|name/i).first().fill("Agent E2E");
    await page.getByLabel(/email/i).first().fill(email);
    await page.getByLabel(/^password/i).first().fill(password);
    await page.getByRole("checkbox").first().check();
    await page.getByRole("button", { name: /create workspace/i }).click();
    await page.waitForURL(/verify-email/);
    await page.goto(BASE + latestLink(email, "/verify-email"));
    await page.getByText(/verified/i).first().waitFor();
    await page.goto(BASE + "/login");
    await page.getByLabel(/email/i).first().fill(email);
    await page.getByLabel(/^password/i).first().fill(password);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await page.waitForURL(/onboarding|overview/);
  });

  await step("agent status shows the configured model and live workers", async () => {
    const s = (await api("GET", "/agent/status")).data;
    if (!s.provider?.configured) throw new Error("no model configured");
    const alive = s.workers.filter((w) => w.alive).map((w) => w.kind);
    for (const k of ["orchestrator", "tools", "deletion", "scheduler"]) if (!alive.includes(k)) throw new Error(`${k} not alive`);
    await page.goto(BASE + "/overview");
    await page.getByText(s.provider.label).first().waitFor();
    await shot("01-overview-agent-status");
  });

  await step("strict privacy mode with an allowlisted site", async () => {
    const r = await api("PATCH", "/workspace/settings", { privacy_mode: "strict", allowed_domains: [SITE_HOST] });
    if (r.status !== 200) throw new Error(`settings ${r.status}`);
  });

  let task;
  await step("create task → persisted → planned", async () => {
    const r = await api("POST", "/tasks", {
      prompt: `Run an SEO audit of ${SITE}/ and summarize the findings in a report.`,
      type: "website",
      priority: "normal",
      mode: "plan_only",
    });
    if (r.status !== 201) throw new Error(`create ${r.status}`);
    task = r.data;
    await waitFor(async () => (await taskState(task.id)).status === "awaiting_approval", "plan");
  });

  await step("plan review shows server-side policy decisions", async () => {
    await page.goto(`${BASE}/tasks/${task.id}/plan`);
    await page.getByText(/needs approval/i).first().waitFor();
    await page.getByText(SITE_HOST).first().waitFor();
    await shot("02-plan-review-policy");
  });

  await step("approve the plan in the UI", async () => {
    await page.getByRole("button", { name: /approve/i }).first().click();
    const dlg = page.getByRole("dialog");
    if (await dlg.count()) {
      for (const cb of await dlg.getByRole("checkbox").all()) await cb.check();
      await dlg.getByRole("button", { name: /approve/i }).last().click();
    }
    await waitFor(async () => ["needs_input", "running", "queued"].includes((await taskState(task.id)).status), "plan approval");
    await waitFor(async () => (await taskState(task.id)).waiting_for === "approval", "step approval request");
  });

  await step("site not contacted before the one-time approval", async () => {
    const t = await taskState(task.id);
    if (t.plan.steps[0].state !== "awaiting_approval") throw new Error(`step state ${t.plan.steps[0].state}`);
  });

  await step("approve the bound step approval in the UI", async () => {
    await page.goto(`${BASE}/approvals`);
    await page.getByText(/web\.inspect|seo\.audit/).first().waitFor();
    await shot("03-approval-bound-action");
    await page.getByRole("button", { name: /approve once/i }).first().click();
    const dlg = page.getByRole("dialog").last();
    for (const cb of await dlg.getByRole("checkbox").all()) await cb.check();
    await dlg.getByRole("button", { name: /approve/i }).last().click();
    await waitFor(async () => (await taskState(task.id)).status === "completed", "task completion", 60000);
  });

  await step("UI shows results, report and audit trail", async () => {
    await page.goto(`${BASE}/tasks/${task.id}`);
    await page.getByText(/completed/i).first().waitFor();
    const t = await taskState(task.id);
    if (!t.artifacts.length) throw new Error("no report artifact");
    const audit = t.plan.steps[0].output;
    if (!audit || audit.status !== 200) throw new Error("step output missing");
    await shot("04-task-completed");
    const acts = (await api("GET", "/activity?page_size=100")).data.items.map((a) => a.action);
    for (const a of ["plan.created", "approval.approve", "step.executed", "task.finished"]) if (!acts.includes(a)) throw new Error(`missing audit ${a}`);
    await page.goto(`${BASE}/reports`);
    await shot("05-activity-and-reports");
  });

  await step("unauthorized external transfer is blocked", async () => {
    const r = await api("POST", "/tasks", {
      prompt: "Inspect http://exfil.example.net/collect and write a report.",
      type: "website",
      priority: "normal",
      mode: "plan_only",
    });
    const id = r.data.id;
    await waitFor(async () => (await taskState(id)).status === "awaiting_approval", "plan");
    const t = await taskState(id);
    const s = t.plan.steps[0];
    if (s.state !== "blocked" || s.policy.outcome !== "deny") throw new Error("not blocked");
    await page.goto(`${BASE}/tasks/${id}/plan`);
    await page.getByText(/blocked by policy/i).first().waitFor();
    await shot("06-external-transfer-blocked");
  });

  await step("unauthorized deletion is blocked (agent can only propose)", async () => {
    const up = await page.evaluate(async () => {
      const csrf = (document.cookie.match(/(?:^|; )(?:__Host-)?stw_csrf=([^;]+)/) || [])[1] || "";
      const fd = new FormData();
      fd.append("file", new Blob(["url,status\n/,200\n"], { type: "text/csv" }), "old-crawl.csv");
      fd.append("collection", "Research");
      const r = await fetch("/api/v1/files", { method: "POST", body: fd, headers: { "X-CSRF-Token": decodeURIComponent(csrf) } });
      return r.json();
    });
    const r = await api("POST", "/tasks", {
      prompt: "Delete the attached file, it is obsolete.",
      type: "file_analysis",
      priority: "normal",
      mode: "plan_only",
      attachment_file_ids: [up.id],
    });
    const id = r.data.id;
    await waitFor(async () => (await taskState(id)).status === "awaiting_approval", "plan");
    const t = await taskState(id);
    await api("POST", `/tasks/${id}/plan/approve`, { selected_step_ids: t.plan.steps.filter((s) => s.state !== "blocked").map((s) => s.id) });
    await waitFor(async () => ["completed", "partially_completed"].includes((await taskState(id)).status), "deletion-proposal task", 60000);
    const f = await api("GET", `/files/${up.id}`);
    if (f.status !== 200) throw new Error(`file gone: ${f.status}`);
    const pend = (await api("GET", "/approvals?status=pending")).data.items.filter((a) => a.category === "record_deletion");
    if (!pend.length) throw new Error("no deletion approval waiting");
    // Approving without confirming the exact items is refused.
    const bad = await api("POST", `/approvals/${pend[0].id}/decision`, { decision: "approve", acknowledged: true, confirmed_items: [] });
    if (bad.status !== 422) throw new Error(`unconfirmed deletion approval → ${bad.status}`);
    await page.goto(`${BASE}/approvals`);
    await shot("07-deletion-needs-separate-approval");
  });

  await step("approved deletion runs in the deletion service and can be restored", async () => {
    const pend = (await api("GET", "/approvals?status=pending")).data.items.find((a) => a.category === "record_deletion");
    const r = await api("POST", `/approvals/${pend.id}/decision`, { decision: "approve", acknowledged: true, confirmed_items: pend.affected_items });
    if (r.status !== 200) throw new Error(`approve ${r.status}`);
    const fileId = (await api("GET", "/files")).data.items.find((x) => x.name === "old-crawl.csv").id;
    await waitFor(async () => (await api("GET", `/files/${fileId}`)).status === 410, "soft delete");
    await page.goto(`${BASE}/files`);
    await page.getByRole("button", { name: /recently deleted/i }).first().click().catch(() => {});
    await shot("08-recently-deleted");
    const rr = await api("POST", `/files/${fileId}/restore`);
    if (rr.status !== 202) throw new Error(`restore ${rr.status}`);
    await waitFor(async () => (await api("GET", `/files/${fileId}`)).status === 200, "restore");
  });

  await step("security page shows enforced controls", async () => {
    await page.goto(`${BASE}/security`);
    await page.getByText(/policy engine/i).first().waitFor();
    await shot("09-security");
  });
} catch {
  // reported below
} finally {
  for (const s of steps) console.log(s.join("  "));
  const real = consoleErrors.filter((e) => !/favicon|Failed to load resource: the server responded with a status of (404|409|410|422)/.test(e));
  if (real.length) console.log("console errors:", real.slice(0, 5));
  const failed = steps.some((s) => s[0] === "FAIL");
  console.log(failed ? "AGENT FLOW: FAILED" : `AGENT FLOW: ${steps.length}/${steps.length} passed`);
  await browser.close();
  process.exit(failed ? 1 : 0);
}
