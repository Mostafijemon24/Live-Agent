// Phase 1 prototype sample data, copied verbatim from
// project/Steward AI Agent Workspace.dc.html (script, lines 1503–1909).
// Labels are kept exactly as in the prototype; mock.ts maps them onto the
// wire enums. Stamps like "Oct 24, 09:12" are anchored to "today" in mock.ts
// (Oct 24 = today, Oct 23 = yesterday, …).
// Used only by MockAgentApi (NEXT_PUBLIC_DEMO_MODE=true).

export interface RawStep {
  t: string;
  tool: string;
  risk: string;
  d: string;
  approval?: boolean;
}

export type PlanKind = "wp" | "content" | "data";

export const PLANS: Record<PlanKind, RawStep[]> = {
  wp: [
    { t: "Read site structure and page list", tool: "WordPress (read-only)", risk: "Read only", d: "Lists pages, posts, theme and active plugins. No changes." },
    { t: "Measure loading speed on 25 key pages", tool: "Browser runtime", risk: "Read only", d: "Opens public pages the way a visitor would." },
    { t: "Check titles, descriptions, headings and broken links", tool: "Agent analysis", risk: "Read only", d: "Compares each page against common SEO guidelines." },
    { t: "Write a report with prioritised fixes", tool: "Workspace", risk: "Workspace only", d: "Saved privately to Files & Knowledge." },
    { t: "Prepare proposed changes (not applied)", tool: "Workspace", risk: "Prepare only", d: "Drafts changes to robots.txt and caching settings for your review." },
    {
      t: "Apply approved fixes to the live website",
      tool: "WordPress (write)",
      risk: "Production change",
      d: "Runs only after a separate approval. A snapshot is taken first so it can be undone.",
      approval: true,
    },
  ],
  content: [
    { t: "Read the source pages and brief", tool: "Workspace files", risk: "Read only", d: "Uses only files attached to this task." },
    { t: "Research search intent and related topics", tool: "Agent analysis", risk: "Read only", d: "Uses public search results." },
    { t: "Draft the content", tool: "Agent analysis", risk: "Workspace only", d: "Drafts are saved privately in this workspace." },
    { t: "Check length, tone and duplicates", tool: "Agent analysis", risk: "Workspace only", d: "" },
    { t: "Publish approved drafts to the website", tool: "WordPress (write)", risk: "Publish", d: "Runs only after a separate approval. Previous versions are kept.", approval: true },
  ],
  data: [
    { t: "Open the attached files", tool: "Workspace files", risk: "Read only", d: "Files stay in private workspace storage." },
    { t: "Check file structure and data quality", tool: "Agent analysis", risk: "Read only", d: "" },
    { t: "Analyse and group the content", tool: "Agent analysis", risk: "Workspace only", d: "" },
    { t: "Write a summary of findings", tool: "Workspace", risk: "Workspace only", d: "" },
    {
      t: "Send large files to an external AI provider if needed",
      tool: "External AI provider",
      risk: "External transfer",
      d: "Only if you approve. Blocked by default for Private and Unknown files.",
      approval: true,
    },
  ],
};

export const KIND: Record<PlanKind, { files: string[]; dest: string }> = {
  wp: {
    files: ["Page and plugin list from the WordPress demo sandbox", "Public pages of the website"],
    dest: "Your WordPress website — final step only, after a separate approval",
  },
  content: {
    files: ["Files attached to this task", "Public search results"],
    dest: "Your WordPress website — publishing step only, after a separate approval",
  },
  data: { files: ["Files attached to this task"], dest: "External AI provider — blocked unless you approve the last step" },
};

/** [name, kind, provenance label] */
export const ARTS: Record<PlanKind, [string, string, string][]> = {
  wp: [
    ["Site audit report (sample).pdf", "Report", "AI-generated summary"],
    ["Checked pages (sample).csv", "Data", "Verified execution result"],
  ],
  content: [
    ["Drafts (sample).docx", "Draft", "AI-generated summary"],
    ["Quality checks (sample).csv", "Data", "Verified execution result"],
  ],
  data: [
    ["Findings summary (sample).md", "Report", "AI-generated summary"],
    ["Grouped rows (sample).csv", "Data", "Verified execution result"],
  ],
};

export interface RawTask {
  id: string;
  title: string;
  status: string;
  type: string;
  created: string;
  updated: string;
  priority: string;
  mode: string;
  integ: string;
  prompt: string;
  q?: string;
  err?: string;
  attach?: string[];
  report?: { sum: string; open: string; next: string };
}

export const TASKS: RawTask[] = (
  [
    ["T-1048", "WordPress performance & SEO audit", "Awaiting approval", "Website/WordPress", "Oct 24, 09:12", "Oct 24, 09:20", "High", "Prepare changes for review", "WordPress (demo)", "Audit my WordPress website for performance and SEO problems, prepare a report, and show me recommended fixes before changing anything."],
    ["T-1047", "Draft meta descriptions for 12 service pages", "Running", "SEO/Content", "Oct 24, 08:40", "Oct 24, 09:18", "Normal", "Prepare changes for review", "WordPress (demo)", "Write new meta descriptions for the 12 service pages, under 155 characters each, and prepare them for my review."],
    ["T-1046", "Summarise competitor pricing pages", "Needs input", "Research", "Oct 24, 08:02", "Oct 24, 09:05", "Normal", "Plan only", "None", "Compare the pricing pages of three competitors and summarise the differences in a table."],
    ["T-1045", "Check plugin update compatibility", "Completed", "Website/WordPress", "Oct 23, 15:10", "Oct 23, 16:45", "Normal", "Plan only", "WordPress (demo)", "Check whether pending plugin updates are compatible with the current theme and PHP version."],
    ["T-1044", "Analyse Q3 support tickets", "Failed", "File analysis", "Oct 23, 13:30", "Oct 23, 13:52", "Normal", "Plan only", "None", "Group the Q3 support tickets by topic and list the five most common problems."],
    ["T-1043", "Clean up unused media files", "Paused", "Website/WordPress", "Oct 23, 10:15", "Oct 23, 11:02", "Normal", "Prepare changes for review", "WordPress (demo)", "Find media files that are not used on any page and propose which ones can be removed."],
    ["T-1042", "Write tests for the contact form validator", "Completed", "Code", "Oct 22, 17:20", "Oct 22, 17:58", "Normal", "Plan only", "None", "Write unit tests for the contact form validator and run them in an isolated sandbox."],
    ["T-1041", "Weekly uptime and SSL certificate check", "Queued", "Browser workflow", "Oct 22, 09:00", "Oct 22, 09:00", "Normal", "Plan only", "None", "Check that the website is reachable and the SSL certificate is valid for at least 30 more days."],
    ["T-1040", "Content brief: local SEO landing page", "Draft", "SEO/Content", "Oct 21, 14:05", "Oct 21, 14:05", "Normal", "Plan only", "None", "Prepare a content brief for a local SEO landing page."],
    ["T-1039", "Publish blog post draft to staging", "Cancelled", "SEO/Content", "Oct 21, 11:30", "Oct 21, 12:10", "Normal", "Prepare changes for review", "WordPress (demo)", "Publish the approved blog post draft to the staging site."],
    ["T-1038", "Research schema markup options", "Partially completed", "Research", "Oct 20, 16:00", "Oct 20, 16:40", "Normal", "Plan only", "None", "Research which schema markup types fit a service business website."],
    ["T-1037", "Review image alt text across the site", "Planning", "SEO/Content", "Oct 24, 09:22", "Oct 24, 09:22", "Normal", "Plan only", "WordPress (demo)", "Review image alt text across the site and suggest improvements."],
  ] as const
).map((a) => ({
  id: a[0],
  title: a[1],
  status: a[2],
  type: a[3],
  created: a[4],
  updated: a[5],
  priority: a[6],
  mode: a[7],
  integ: a[8],
  prompt: a[9],
}));
TASKS[2].q = "Which three competitors should I compare? Add their website addresses.";
TASKS[4].err =
  "The file has rows with a different number of columns, so it could not be read reliably. Nothing was changed. Fix the file or upload a cleaned copy, then start a new task.";
TASKS[4].attach = ["support-tickets-q3-sample.csv"];
TASKS[3].report = {
  sum: "9 of 11 pending plugin updates look compatible with the current theme and PHP version.",
  open: "2 plugins may conflict with the theme and need a manual test on a staging site.",
  next: "Create a task to test the 2 plugins on staging.",
};
TASKS[6].report = {
  sum: "12 tests written. In the isolated demo sandbox, 11 pass and 1 fails on an empty phone field.",
  open: "The validator accepts an empty phone number when it is marked required.",
  next: "Review the failing case before any code change.",
};
TASKS[10].report = {
  sum: "3 schema types compared: LocalBusiness, Service and FAQPage.",
  open: "FAQPage research is incomplete — one source was unavailable.",
  next: "Re-run the FAQPage step when the source is reachable.",
};

export interface RawApproval {
  id: string;
  cat: string;
  title: string;
  task: string;
  why: string;
  affected: string[];
  leaves: boolean;
  dest: string;
  count: string;
  consequence: string;
  reversible: string;
  expires: string;
  requested: string;
  status: string;
  risk: string;
  decided?: string;
  note?: string;
}

export const APPROVALS: RawApproval[] = [
  { id: "A-311", cat: "External data transfer", title: "Send 3 files to an external AI provider", task: "T-1046", why: "The Agent wants a larger model to summarise long competitor documents it could not process inside the workspace.", affected: ["competitor-notes-sample.docx", "pricing-export-sample.csv", "meeting-notes-sample.txt"], leaves: true, dest: "External AI model provider (not configured)", count: "3 files · 2.4 MB", consequence: "Copies of these files would be processed by a third-party service under its own data policy.", reversible: "No — data sent externally cannot be recalled.", expires: "Expires in 23 h", requested: "Oct 24, 09:05", status: "Pending", risk: "High" },
  { id: "A-310", cat: "Production website change", title: "Update robots.txt and caching settings on the live site", task: "T-1048", why: "The audit found search engines are blocked from 2 sections and page caching is turned off.", affected: ["robots.txt", "Caching plugin: page cache (on)", "Caching plugin: cache lifetime (1 h)"], leaves: false, dest: "WordPress site (demo sandbox)", count: "1 file · 2 settings", consequence: "Search engines can index the 2 sections; pages should load faster. Visitors may briefly see cached content.", reversible: "Yes — a snapshot is taken before changes.", expires: "Expires in 2 days", requested: "Oct 24, 09:20", status: "Pending", risk: "High" },
  { id: "A-309", cat: "Publish", title: "Publish 12 new meta descriptions", task: "T-1047", why: "You asked for meta descriptions to be prepared for review before publishing.", affected: ["12 service pages (meta description field only)"], leaves: false, dest: "WordPress site (demo sandbox)", count: "12 records", consequence: "Search results may show the new descriptions after the next crawl.", reversible: "Yes — previous descriptions are kept.", expires: "Expires in 3 days", requested: "Oct 24, 09:18", status: "Pending", risk: "Medium" },
  { id: "A-308", cat: "Send message", title: "Email the compatibility summary to 1 recipient", task: "T-1045", why: "The task asked to share the summary when finished.", affected: ["Compatibility summary (1 page)"], leaves: true, dest: "Email to recipient@example.com", count: "1 message", consequence: "The recipient receives the summary text. No attachments.", reversible: "No — sent emails cannot be unsent.", expires: "Expires in 1 day", requested: "Oct 23, 16:45", status: "Pending", risk: "Medium" },
  { id: "A-307", cat: "Record deletion", title: "Delete 4 unused media files", task: "T-1043", why: "These files are not used on any page or post.", affected: ["old-banner-2019.jpg", "header-v1.png", "promo-draft.gif", "unused-icon.svg"], leaves: false, dest: "WordPress media library (demo sandbox)", count: "4 files · 3.1 MB", consequence: "Any external link that points directly to these files would break.", reversible: "Partly — files stay in trash for 30 days, then are permanently removed.", expires: "Expires in 2 days", requested: "Oct 23, 11:02", status: "Pending", risk: "High" },
  { id: "A-306", cat: "Integration permission change", title: "Allow read-only access to one Notion database", task: "", why: "Needed to import tasks from a task list.", affected: ["1 Notion database (read-only)"], leaves: false, dest: "Notion (not connected)", count: "1 database", consequence: "The Agent could read task titles and descriptions.", reversible: "Yes — revoke at any time.", expires: "—", requested: "Oct 23, 15:58", status: "Approved (simulated)", risk: "Low", decided: "Oct 23, 16:02" },
  { id: "A-305", cat: "External data transfer", title: "Send support tickets to an external AI provider", task: "T-1044", why: "The file was too large to analyse inside the workspace.", affected: ["support-tickets-q3-sample.csv"], leaves: true, dest: "External AI model provider (not configured)", count: "1 file · 8.1 MB", consequence: "Customer messages would be processed by a third party.", reversible: "No — data sent externally cannot be recalled.", expires: "—", requested: "Oct 23, 11:20", status: "Rejected", risk: "High", decided: "Oct 23, 11:40", note: "Contains customer personal data." },
];

export interface RawFile {
  id: string;
  name: string;
  type: string;
  size: string;
  up: string;
  status: string;
  cls: string;
  coll: string;
  err?: string;
}

export const FILES: RawFile[] = [
  { id: "F1", name: "site-crawl-sample.csv", type: "CSV", size: "1.2 MB", up: "Oct 24, 08:55", status: "Ready", cls: "Private", coll: "Website audits" },
  { id: "F2", name: "brand-guidelines-sample.pdf", type: "PDF", size: "4.8 MB", up: "Oct 22, 10:14", status: "Ready", cls: "Approved for selected integration", coll: "SEO & content" },
  { id: "F3", name: "support-tickets-q3-sample.csv", type: "CSV", size: "8.1 MB", up: "Oct 23, 13:28", status: "Failed", cls: "Private", coll: "Support data", err: "Rows have inconsistent columns." },
  { id: "F4", name: "competitor-notes-sample.docx", type: "DOCX", size: "640 KB", up: "Oct 24, 08:01", status: "Processing", cls: "Unknown", coll: "Research" },
  { id: "F5", name: "pricing-export-sample.csv", type: "CSV", size: "1.5 MB", up: "Oct 24, 08:01", status: "Scanning", cls: "Unknown", coll: "Research" },
  { id: "F6", name: "press-kit-sample.zip", type: "ZIP", size: "22 MB", up: "Oct 21, 09:40", status: "Quarantined", cls: "Unknown", coll: "SEO & content", err: "Archive contains an executable file." },
  { id: "F7", name: "form-validator-sample.js", type: "JS", size: "12 KB", up: "Oct 22, 17:15", status: "Ready", cls: "Private", coll: "Code" },
  { id: "F8", name: "public-faq-sample.md", type: "MD", size: "18 KB", up: "Oct 20, 15:30", status: "Ready", cls: "Public", coll: "SEO & content" },
  { id: "F9", name: "meeting-notes-sample.txt", type: "TXT", size: "260 KB", up: "Oct 24, 08:02", status: "Ready", cls: "Unknown", coll: "Research" },
];

/** COLLS without the synthetic "All files" entry. */
export const COLLECTIONS = ["Website audits", "SEO & content", "Research", "Support data", "Code"];

export interface RawAutomation {
  id: string;
  name: string;
  trigger: string;
  when: string;
  tz: string;
  template: string;
  tools: string;
  cls: string;
  policy: string;
  last: string;
  next: string;
  status: string;
  created: string; // not in the prototype; added so created_at is stable
}

export const AUTOS: RawAutomation[] = [
  { id: "AU-3", name: "Weekly site health check", trigger: "Schedule", when: "Every Monday at 08:00", tz: "Asia/Dhaka (GMT+6)", template: "WordPress audit (read-only)", tools: "WordPress (read-only), Browser runtime", cls: "Private files only", policy: "Ask before any change", last: "Never run", next: "Not scheduled — scheduler requires backend", status: "Paused", created: "Oct 22, 10:40" },
  { id: "AU-2", name: "Monthly SEO summary", trigger: "Schedule", when: "1st of each month at 09:00", tz: "Asia/Dhaka (GMT+6)", template: "SEO report", tools: "Agent analysis, Workspace", cls: "Private files only", policy: "Ask before publishing or sending", last: "Never run", next: "Not scheduled — scheduler requires backend", status: "Paused", created: "Oct 21, 10:00" },
  { id: "AU-1", name: "Plugin update review", trigger: "Manual", when: "When you start it", tz: "Asia/Dhaka (GMT+6)", template: "Plugin compatibility check", tools: "WordPress (read-only)", cls: "No files", policy: "Ask before any change", last: "Oct 23, 15:10 (demo)", next: "Runs when you start it", status: "Enabled", created: "Oct 20, 09:30" },
];

export interface RawIntegration {
  id: string; // wire key
  name: string;
  icon: string;
  status: string;
  scope: string;
  last: string;
  dest: string;
  scopes: string[];
}

// Prototype ids wp/notion/drive/email/browser/ai → wire keys below.
export const INTEGS: RawIntegration[] = [
  { id: "wordpress", name: "WordPress", icon: "globe", status: "Demo", scope: "Read pages, posts and plugins. Changes only after a separate approval.", last: "Demo sandbox — no real website", dest: "Your WordPress website", scopes: ["Read pages and posts", "Read plugin and theme list", "Prepare changes (not applied)", "Write changes — only with per-action approval"] },
  { id: "notion", name: "Notion", icon: "notebook", status: "Not connected", scope: "Import tasks from one selected database, read-only.", last: "Never", dest: "Notion workspace you choose", scopes: ["Read one selected database"] },
  { id: "cloud_storage", name: "Cloud storage", icon: "cloud", status: "Not connected", scope: "Read files from folders you choose. No upload without approval.", last: "Never", dest: "Your cloud storage account", scopes: ["Read selected folders", "Upload — only with per-action approval"] },
  { id: "email", name: "Email", icon: "mail", status: "Not connected", scope: "Send messages you approve one by one. Cannot read your inbox.", last: "Never", dest: "Recipients you approve", scopes: ["Send approved messages"] },
  { id: "browser", name: "Browser automation", icon: "monitor", status: "Backend required", scope: "Opens allowlisted websites in an isolated browser.", last: "Never", dest: "Allowlisted domains only", scopes: ["Visit allowlisted domains", "Fill forms — only with approval"] },
  { id: "ai_provider", name: "AI model provider", icon: "cpu", status: "Backend required", scope: "Processes task text. Files are sent only with approval.", last: "Never", dest: "Provider chosen by your administrator", scopes: ["Process task text", "Process files — per-action approval"] },
];

/** [stamp, type label, text, task ref, machine action] */
export const ACT: [string, string, string, string, string][] = [
  ["Oct 24, 09:22", "Task", "Task T-1037 created — preparing a plan", "T-1037", "task.created"],
  ["Oct 24, 09:20", "Plan", "Plan prepared for T-1048 — waiting for your review", "T-1048", "plan.prepared"],
  ["Oct 24, 09:18", "Execution", "T-1047: step 3 of 5 started (demo)", "T-1047", "execution.step_started"],
  ["Oct 24, 09:05", "Security", "Sending 3 files to an external AI provider held for approval", "T-1046", "security.held_for_approval"],
  ["Oct 24, 09:05", "Task", "T-1046 needs your input: which competitors to compare", "T-1046", "task.needs_input"],
  ["Oct 23, 16:45", "Execution", "T-1045 completed — compatibility report saved", "T-1045", "execution.completed"],
  ["Oct 23, 16:02", "Approval", "A-306 approved (simulated): read-only Notion access", "", "approval.approved"],
  ["Oct 23, 14:22", "Security", "Browser step blocked: domain not on allowlist", "T-1041", "security.blocked"],
  ["Oct 23, 13:52", "Error", "T-1044 failed: the file could not be read reliably", "T-1044", "task.failed"],
  ["Oct 23, 11:40", "Approval", "A-305 rejected: send support tickets externally", "T-1044", "approval.rejected"],
  ["Oct 23, 11:02", "Task", "T-1043 paused by Demo User", "T-1043", "task.paused"],
  ["Oct 22, 17:58", "Execution", "T-1042 completed — 12 tests written", "T-1042", "execution.completed"],
  ["Oct 22, 10:30", "Integration", "WordPress demo sandbox added (sample)", "", "integration.added"],
];

export interface RawNote {
  id: string;
  type: string;
  icon: string;
  text: string;
  /** prototype shows "09:20" / "Yesterday" / "Oct 22"; full stamps chosen to match. */
  stamp: string;
  unread: boolean;
  target: { kind: "plan" | "task" | "approval" | "integrations" | "usage"; ref?: string };
}

export const NOTES: RawNote[] = [
  { id: "N1", type: "Approval requested", icon: "hourglass", text: "Plan for T-1048 is ready for review", stamp: "Oct 24, 09:20", unread: true, target: { kind: "plan", ref: "T-1048" } },
  { id: "N2", type: "Agent needs more information", icon: "message-circle", text: "T-1046: which three competitors should be compared?", stamp: "Oct 24, 09:05", unread: true, target: { kind: "task", ref: "T-1046" } },
  { id: "N3", type: "Security policy blocked an action", icon: "shield-alert", text: "Sending 3 files externally is on hold until you decide", stamp: "Oct 24, 09:05", unread: true, target: { kind: "approval", ref: "A-311" } },
  { id: "N4", type: "Task completed", icon: "circle-check", text: "T-1045 plugin compatibility check finished", stamp: "Oct 23, 16:45", unread: false, target: { kind: "task", ref: "T-1045" } },
  { id: "N5", type: "Task failed", icon: "circle-x", text: "T-1044 could not read the support tickets file", stamp: "Oct 23, 13:52", unread: false, target: { kind: "task", ref: "T-1044" } },
  { id: "N6", type: "Integration disconnected", icon: "unplug", text: "Cloud storage is not connected — backend required", stamp: "Oct 22, 10:30", unread: false, target: { kind: "integrations" } },
  { id: "N7", type: "Usage limit reached", icon: "gauge", text: "Example only: usage alerts appear here once the backend tracks usage", stamp: "Oct 21, 09:00", unread: false, target: { kind: "usage" } },
];

export const BLOCKED: { t: string; text: string; reason: string }[] = [
  { t: "Oct 24, 09:05", text: "Send 3 files to an external AI provider", reason: "2 files are classified Unknown — held for approval" },
  { t: "Oct 23, 14:22", text: "Open unlisted-domain.example in browser task", reason: "Domain is not on the allowlist" },
  { t: "Oct 23, 11:20", text: "Send support tickets to an external AI provider", reason: "Rejected by Demo User — contains personal data" },
];

/** [key, label] */
export const CHECK: [string, string][] = [
  ["session_cookies", "Secure, HttpOnly session cookies"],
  ["csrf", "CSRF protection"],
  ["rate_limiting", "Rate limiting on sign-in and task creation"],
  ["tenant_isolation", "Tenant isolation checked on every request"],
  ["secrets_storage", "Encrypted secrets storage"],
  ["backups", "Automated backups with tested restore"],
  ["audit_log", "Tamper-evident audit log"],
  ["outbound_policy", "Outbound network policy for AI providers"],
  ["deletion_protection", "Deletion protection and retention rules"],
];

export const RETENTION: { label: string; value: string }[] = [
  { label: "Task logs", value: "Kept 90 days (proposed)" },
  { label: "Deleted files", value: "Kept 30 days, then permanently removed" },
  { label: "Audit events", value: "Kept 1 year (proposed)" },
  { label: "This demo", value: "Stores nothing beyond your current browser tab" },
];

export const AI_PROVIDER_POLICY = [
  "Task text may be processed by an AI provider once one is configured.",
  "Files are never sent without a per-action approval.",
  "Private and Unknown files are blocked from external transfer by default.",
  "Provider: not configured. Its retention and training policy will be shown here.",
].join("\n");

export const UPLOAD_TYPES = ["PDF", "DOCX", "CSV", "XLSX", "TXT", "MD"];
export const UPLOAD_MAX_BYTES = 25 * 1024 * 1024;
