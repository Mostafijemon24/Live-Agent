# Personal AI Agent Platform --- MVP UI/UX & Technical Design Specification

**ডকুমেন্টের উদ্দেশ্য:** এই specification-টি কোনো Cloud AI coding/design
agent-কে দিন, যাতে সে একটি polished, responsive, application-based AI
Agent Dashboard MVP তৈরি করে। প্রথম ধাপে frontend ও integration-ready
mock layer তৈরি হবে; পরে backend, AI orchestration, database এবং worker
যুক্ত করলে একই UI বাস্তবভাবে কাজ করবে।

**Deployment target:** Hostinger VPS\
**প্রধান ব্যবহারকারী:** non-technical user\
**প্রাথমিক পণ্যধারণা:** প্রতিটি ব্যবহারকারী লগইন করে নিজের private AI
workspace পাবেন; সেখানে task তৈরি, ফাইল যোগ, automation review,
approval, run history এবং reports দেখতে পারবেন।

> **গুরুত্বপূর্ণ:** এই document একটি product/design/implementation brief; এটি
> নিজে security certification বা production readiness নিশ্চিত করে না।
> Cloud AI-কে শুধু সুন্দর UI বানাতে নয়, নিচের security, privacy, modularity
> ও backend-contract শর্তগুলোও মানতে বলুন। Backend যুক্ত না হওয়া পর্যন্ত সব
> action স্পষ্টভাবে Demo/Mock হিসেবে দেখাতে হবে।

------------------------------------------------------------------------

## 1. Product vision

একটি পরিষ্কার, আধুনিক ও নির্ভরযোগ্য AI Agent web application তৈরি করুন,
যেখানে ব্যবহারকারীকে coding বা command line জানতে হবে না। ব্যবহারকারী
স্বাভাবিক ভাষায় কাজ বলবেন, অনুমোদিত ফাইল দেবেন, প্রয়োজনীয় integration যুক্ত
করবেন এবং Agent-এর পরিকল্পনা ও ফলাফল dashboard থেকে পরিচালনা করবেন।

সম্ভাব্য ভবিষ্যৎ কাজ: - WordPress website audit, debugging ও maintenance -
SEO research, content brief, metadata এবং report তৈরি - Code generation,
review ও isolated test - অনুমোদিত browser workflow ও web research -
Image/content generation workflow - Notion/CSV/Excel/text task source
থেকে কাজ import - Social media draft ও publishing workflow --- **প্রথমে
approval required** - Scheduled/recurring tasks, notifications ও audit
reports

প্রথম MVP-তে এগুলোর প্রতিটি বাস্তবে চালু আছে এমন ভান করা যাবে না। UI-তে
feature status হবে **Available**, **Backend required**, **Coming
later**, অথবা **Demo data**---যেটি সত্য।

## 2. Design goals

1.  **Non-technical first:** কাজ শুরু করতে সহজ; technical configuration
    advanced settings-এর মধ্যে থাকবে।
2.  **Professional SaaS UI:** শান্ত, minimal, premium, consistent
    typography ও spacing; অতিরিক্ত gradient, glowing effects, emoji ও
    decorative cards নয়।
3.  **Action clarity:** প্রতিটি গুরুত্বপূর্ণ action-এর অবস্থা, অনুমতি ও পরবর্তী
    ধাপ স্পষ্ট।
4.  **Trust & privacy by design:** ব্যবহারকারী বুঝবেন কোন ফাইল
    local/private, কোন data বাইরে পাঠানোর অনুরোধ করছে, কোন action
    approval-এর অপেক্ষায়।
5.  **Backend-ready architecture:** mock data ও UI components পরে real
    API-তে যুক্ত করা যাবে; UI-তে business logic গুঁজে দেওয়া যাবে না।
6.  **Accessible & responsive:** keyboard-friendly, visible focus,
    readable contrast, mobile/tablet/desktop support।
7.  **Scalable UI patterns:** pagination, filters, server-side search,
    loading/empty/error states; বিশাল dataset browser-এ একসঙ্গে লোড নয়।
8.  **No false claims:** backend না থাকলে task সত্যিই চালানো, ফাইল মুছে
    ফেলা, data sync, AI response বা publishing হয়েছে---এমন দেখানো যাবে
    না।

## 3. Visual design system

### Style

-   Product feel: modern B2B SaaS / AI operations workspace.
-   Layout: left navigation sidebar + top header + main content area.
-   Use a neutral background, white/light surfaces, subtle borders,
    restrained shadows.
-   Suggested palette:
    -   Primary: deep indigo/blue `#3448C5` (buttons, selected
        navigation)
    -   Main text: `#172033`
    -   Secondary text: `#667085`
    -   Page background: `#F6F8FB`
    -   Surface: `#FFFFFF`
    -   Border: `#E4E7EC`
    -   Success: `#16803C`
    -   Warning: `#B54708`
    -   Danger: `#B42318`
-   Use CSS variables/design tokens so colors can be changed centrally.
-   Typography: Inter or another readable modern sans-serif with
    appropriate fallback.
-   Rounded corners should be moderate and consistent (8--12px). Avoid
    excessive pill-shaped containers.
-   Use Lucide-style consistent line icons. Icon-only controls require
    accessible labels/tooltips.
-   Motion should be subtle, respect `prefers-reduced-motion`, and never
    block interaction.
-   Include light theme initially; structure tokens so dark mode can be
    added later.

### Responsive layout

-   Desktop: fixed/collapsible sidebar, header, wide content area.
-   Tablet: collapsible sidebar and responsive grids.
-   Mobile: drawer navigation, single-column cards, sticky primary
    action only where helpful.
-   Do not use horizontal scrolling for the overall page. Wide data
    tables should switch to responsive list/card layouts or provide a
    contained scroll region.

## 4. Main information architecture

Sidebar navigation: 1. **Overview** 2. **AI Agent / New Task** 3.
**Tasks** 4. **Approvals** 5. **Files & Knowledge** 6. **Automations**
7. **Integrations** 8. **Reports & Activity** 9. **Security & Privacy**
10. **Settings** 11. **Help & Getting Started**

Top header: - Workspace selector (for future multi-workspace support) -
Global search (search only accessible records) - Notifications - Help -
User avatar/menu - Optional environment badge: Demo / Connected / Needs
setup

Avoid showing features that do not exist. If a menu item is
future-facing, mark it as "Setup required" or place it in a feature
roadmap section.

## 5. Authentication and first-run experience

Create polished screens for: - Sign up - Sign in - Forgot password -
Reset password - Email verification - Session expired - Unauthorized /
access denied

Authentication UI requirements: - Email + password initially; optional
OAuth buttons must be clearly disabled until configured. - Password
visibility toggle, field-level validation, loading/error/success
states. - Do not store credentials, tokens, or session secrets in
localStorage. - The frontend must be designed to use secure, HttpOnly,
Secure, SameSite cookies when the backend supports them. - Do not
implement a fake client-only login as real authentication. Demo mode
must be visibly labeled and must not imply user data is protected. -
Include terms/privacy links as placeholders that are easy to replace
with real policy URLs. - Rate-limit, CSRF protection, password hashing,
email verification, secure session management and account recovery
belong to backend implementation, not frontend-only code.

### Onboarding wizard

After registration, guide the user through a short, skippable setup: 1.
"What do you want your AI Agent to help with?" (WordPress, SEO/content,
research, coding, browser workflows, other) 2. "Where should it work?"
(workspace files, connected apps, approved websites) --- permissions
explained in plain language. 3. "How should it handle important
actions?" Default: ask before external sharing, publishing, sending
messages, changing production systems or deleting records. 4. "Connect
tools later" --- allow skip. 5. Show a clear summary of what is and is
not configured.

Never ask for API keys in ordinary chat or display secrets after save.
Integrations should use a secure backend connection flow.

## 6. Overview dashboard

The first screen should answer: **What is my Agent doing, what needs my
approval, and what happened recently?**

### Header area

-   Greeting: "Your workspace"
-   Subtitle with current workspace status
-   Primary CTA: **Create task**
-   Secondary CTA: **Import task list**

### KPI cards (only if backed by data; otherwise label as demo)

-   Tasks in progress
-   Awaiting approval
-   Completed this week
-   Needs attention

### Main sections

-   **Agent status:** Not connected / Ready / Working / Paused / Error.
    Explain the status in simple terms.
-   **Quick task input:** multiline prompt with example suggestions;
    "Plan task" action.
-   **Pending approvals:** count, risk label, short summary, Review
    button.
-   **Recent tasks:** title, status, created date, last update, Open
    details.
-   **Activity timeline:** task created, plan prepared, approval
    requested, execution completed, error, integration changed.
-   **Setup checklist:** verify account, choose privacy defaults,
    connect an integration, run a safe demo task.

Avoid fabricated real-time metrics. Include proper skeleton/loading,
no-data/empty, partial-error and retry states.

## 7. Create task flow

### Task composer

Provide a spacious, approachable task creation screen with: - Task title
(optional; generate suggestion from prompt) - "What would you like the
Agent to do?" large textarea - Task type selector: Research,
Website/WordPress, SEO/Content, Code, Browser workflow, File analysis,
Custom - File attachment control with accepted file types and size limit
shown from configuration - Optional source selection: workspace file,
imported CSV, connected integration - Priority: Normal / High (do not
allow arbitrary unlimited priority levels) - Execution mode: - **Plan
only** (safe default) - **Prepare changes for review** - **Execute
approved steps** (disabled until backend/policy is configured) - "Create
task" button

### Task lifecycle

Use a consistent state model:
`Draft → Queued → Planning → Awaiting approval → Running → Completed`
Additional states: `Paused`, `Needs input`, `Failed`, `Cancelled`,
`Partially completed`.

Do not use "Completed" if the task only generated a plan. Show the
specific completed stage.

### Plan review

Before a consequential task runs, show: - Goal and interpretation -
Step-by-step plan - Tools/integrations required - Files/data to be
accessed - External destinations that may receive data - Potentially
destructive or irreversible steps - Estimated usage/cost when the
backend can calculate it - Required approvals - "Approve selected
steps", "Edit plan", "Reject", "Ask a question"

Approval must be enforced server-side later. A hidden/disabled button or
frontend state is not a security boundary.

## 8. Tasks list and task details

### Tasks list

-   Search, filters (status, type, date, integration), sorting and
    pagination.
-   Table on desktop; cards/list on mobile.
-   Columns: task, status, type, created, updated, next action.
-   Bulk actions must be conservative; no bulk delete.
-   "Cancel" is available only if backend says the task can be
    cancelled.
-   Never show a destructive action without an explicit confirmation
    step.

### Task detail view

Tabs/sections: 1. Summary 2. Plan & steps 3. Inputs & attachments 4.
Approval history 5. Run logs 6. Outputs / artifacts 7. Audit events

Each step shows state, timestamps, tool used, outcome and error details
suitable for a nontechnical user. Add a "Copy error details" action that
excludes secrets and private file contents by default.

## 9. Approvals center

Build a dedicated approvals queue. Each item should clearly say: - What
action is requested - Why approval is required - What exact data or
records are affected - Whether data leaves the workspace - External
destination/service - Number and type of records affected - Whether the
action is reversible - Expiration time if relevant - Requested by / task
reference

Approval categories: - External data transfer - Publish/send/share -
Production website change - Database modification - Record deletion -
Integration permission change - High-impact browser action

### Approval rules

-   Default deny for external transfer of confidential data.
-   No file or record deletion without explicit approval.
-   No database `DELETE`, `TRUNCATE`, destructive migration, bulk
    overwrite, or irreversible action via a general-purpose AI worker
    role.
-   For deletion requests, require a preview of the exact affected
    records/count, target, reason and scope. Approval must be specific
    to that operation, not a reusable blanket permission.
-   Approval should expire and be bound to the exact action
    payload/hash, user, tenant and target. Any material change to the
    action requires new approval.
-   Provide **Approve once**, **Reject**, and **Request changes** where
    appropriate. Avoid "Always approve" for destructive/external-sharing
    actions.
-   Log who approved what, when, and the exact scope. Do not expose
    another tenant's approval history.

## 10. Files & Knowledge

Design a file workspace with: - Drag-and-drop upload and browse
controls - File name, type, size, uploaded date, scan/processing
status - Folders or collections - Search and filters - Processing
states: Uploading, Scanning, Ready, Processing, Failed, Quarantined -
File preview for supported safe formats - Clear upload size/type limits
from backend configuration - Empty state with examples

### Privacy labels

Every file/knowledge item should have a clear classification: - Private
--- workspace only - Approved for selected integration - Public -
Unknown --- sharing blocked until classified

Show a persistent notice: **"Adding a file to your workspace does not
automatically authorize sending it to an external AI provider or
connected app."**

### Security behavior

-   File access is tenant-scoped and checked server-side on every
    request.
-   Do not put private file contents in public URLs, browser analytics,
    client logs, error trackers or unprotected caches.
-   Validate file type/size server-side; scan uploads; prevent path
    traversal and executable upload risks.
-   Store file bytes in private storage, not in a public web root.
-   Use short-lived signed links only when needed and only after
    authorization.
-   File deletion requires explicit confirmation and an auditable
    operation. If retention/legal requirements apply, explain the
    policy.
-   The UI must not claim "local-only" if files are actually uploaded to
    the VPS or external provider; display the real storage/processing
    location.

## 11. Automations

Automation list and creation wizard: - Name - Trigger (manual, schedule,
supported event) - Task/template - Scope and allowed tools - Data
classification rules - Approval policy - Last run / next run -
Enabled/paused status

Show timezone explicitly. Provide pause/resume and run history. Avoid
unlimited schedules or tight polling defaults. Scheduled runs must use
queue/backpressure and idempotency keys on the backend.

For the first MVP, use mock examples and mark scheduler integration as
backend-required if it does not exist.

## 12. Integrations

Integration cards can include WordPress, Notion, Google Drive, email,
browser runtime, and AI model provider, but only display a **Connect**
action when a real connection flow exists.

Each integration card: - Logo/icon and name - Connected / Not connected
/ Error / Needs re-authentication - Permission scope in plain language -
Last sync/check - Manage / Disconnect - Data destination and sharing
notice

Security requirements: - Do not request or display raw passwords/API
keys in general-purpose chat. - Store credentials encrypted server-side
or use a dedicated secrets manager; never bundle secrets in frontend
code. - Use least-privilege scopes and per-integration authorization. -
Support revocation and reconnection. - Do not imply an integration is
connected when using mock data. - External sharing must be independently
checked by policy engine; a connected integration is not blanket
permission to share every file.

## 13. Reports & Activity

-   Task completion reports with summary, outcomes, artifacts,
    unresolved issues and next steps.
-   Filterable audit/activity log.
-   Export report only if backend permits it; warn if it contains
    confidential content.
-   Logs should redact tokens, passwords, cookies, API keys and
    unnecessary personal data.
-   Distinguish AI-generated summary from verified execution results.
-   Provide timestamps with timezone and stable task IDs.
-   Include failure details and retry option only when retry is
    safe/idempotent.

## 14. Security & Privacy center

This is a first-class product area, not a buried settings page.

Show: - Workspace privacy mode - External AI/provider data policy -
Connected integrations and granted scopes - Recent approvals - Recent
blocked transfers - Session/device list (when backend supports it) -
Export data request - Account deletion request - Retention policy -
Security events

### Privacy modes

Offer understandable modes, but never imply a stronger guarantee than
the actual backend enforces: 1. **Strict private mode:** confidential
data cannot leave the approved environment; external model/API calls
blocked unless an explicit, narrowly scoped exception is approved.
Requires enforceable backend egress controls. 2. **Approval required:**
external transfer requires approval each time. 3. **Custom policy:**
advanced users/admins configure allowlisted destinations and data
classes.

Default to the safest available mode. If the selected mode is not
technically enforced yet, label it **Not enforced --- backend setup
required** and do not present it as active protection.

### Security UI

-   Display a visible "Security configuration incomplete" warning when
    backend controls are missing.
-   Provide a setup checklist for secure cookies, CSRF, rate limiting,
    tenant isolation, encrypted secrets, backups, audit log, outbound
    network policy and deletion protection.
-   Never expose server paths, environment variables, raw stack traces
    or secrets to normal users.

## 15. Settings

Sections: - Profile - Workspace - Appearance - Notifications - Privacy &
security - AI behavior - Connected tools - Usage and limits - Billing
(future/disabled unless implemented) - Account management

AI behavior controls: - Ask before sharing outside workspace --- ON by
default - Ask before publishing/sending --- ON by default - Ask before
changing production systems --- ON by default - Ask before deleting
files/records --- ON by default - Restrict work to selected folders ---
ON by default - Allowlist domains for browser tasks - Allowed tool
permissions

These are user-facing preferences only; the backend policy engine must
enforce them. A user should not be able to grant themselves
organization-admin privileges through client-side fields.

## 16. Notifications and help

Notification types: - Approval requested - Task completed/failed - Agent
needs more information - Integration disconnected - Security policy
blocked an action - Usage limit reached

Help center: - Plain-language explanations - "What can the Agent
access?" - "When does data leave my workspace?" - "Why is approval
needed?" - "How do I stop a task?" - "What happens when I delete a
file?" - Contact/support link placeholder

## 17. Required UI states

Every data-driven page must include: - Loading/skeleton - Empty state -
Success state - Validation error - Network/server error with safe
retry - Permission denied - Session expired - Backend not configured -
Demo/mock mode - Partial failure - Mobile layout

Avoid blank screens and silent failures. Error copy should explain what
happened and the safest next action.

## 18. Technical implementation guidance for the Cloud AI builder

Build a maintainable, production-minded frontend that can be connected
to a separate backend later.

### Suggested frontend stack

Use **Next.js + TypeScript + Tailwind CSS + a consistent accessible
component library (such as shadcn/ui) + Lucide icons**, unless the
current environment has a stronger established stack. Use stable,
mutually compatible versions and document exact versions.

### Architecture

-   Feature-based folders: `auth`, `dashboard`, `tasks`, `approvals`,
    `files`, `automations`, `integrations`, `reports`, `security`,
    `settings`.
-   Shared design system/components in `components/ui` and
    `components/shared`.
-   API access layer in `lib/api`; no direct `fetch()` scattered through
    UI components.
-   Domain types and schemas in `types` / `schemas`.
-   Environment/config handling in one place.
-   Keep business rules out of presentational components.
-   Separate API DTOs from view models.
-   Validate incoming API payloads.
-   Centralize error handling and request IDs.
-   Use pagination and filters in API contracts; avoid fetching all
    records.
-   Use server components where suitable, client components only for
    interactivity.
-   Avoid overengineering micro-frontends for the MVP.

### Mock/real API adapter

Implement an explicit adapter boundary: - `MockAgentApi` ---
deterministic, clearly labelled demo data for UI development. -
`HttpAgentApi` --- real REST API implementation to be wired later. -
`AgentApi` interface --- shared contract consumed by UI. - A single
environment/config switch chooses mock or real API. - Never silently
fall back from real API errors to mock success; that would mislead
users. - In mock mode, show a persistent **Demo mode --- no real actions
are being executed** banner. - Mock mode must not accept or retain real
secrets or confidential files.

Example conceptual interface (adapt it to the codebase rather than
blindly copying):

``` ts
interface AgentApi {
  getDashboard(): Promise<DashboardSummary>;
  listTasks(query: TaskQuery): Promise<Paginated<Task>>;
  createTask(input: CreateTaskInput): Promise<Task>;
  getTask(taskId: string): Promise<TaskDetail>;
  cancelTask(taskId: string): Promise<void>;
  listApprovals(): Promise<ApprovalRequest[]>;
  approveAction(approvalId: string, input: ApprovalDecision): Promise<void>;
  rejectAction(approvalId: string, input: ApprovalDecision): Promise<void>;
  listFiles(query: FileQuery): Promise<Paginated<WorkspaceFile>>;
  listActivity(query: ActivityQuery): Promise<Paginated<AuditEvent>>;
  getSecurityStatus(): Promise<SecurityStatus>;
}
```

## 19. Backend contract and future API integration

The MVP UI must be designed around a documented REST API contract. It
does not need to implement the backend now, but must provide an
`API_CONTRACT.md` alongside the UI.

Suggested API routes (final routes can be improved if documented
consistently): - `POST /api/v1/auth/register` -
`POST /api/v1/auth/login` - `POST /api/v1/auth/logout` -
`POST /api/v1/auth/forgot-password` -
`POST /api/v1/auth/reset-password` - `GET /api/v1/me` -
`GET /api/v1/dashboard` - `GET /api/v1/tasks` - `POST /api/v1/tasks` -
`GET /api/v1/tasks/{task_id}` - `POST /api/v1/tasks/{task_id}/cancel` -
`GET /api/v1/tasks/{task_id}/events` - `GET /api/v1/approvals` -
`POST /api/v1/approvals/{approval_id}/approve` -
`POST /api/v1/approvals/{approval_id}/reject` - `GET /api/v1/files` -
`POST /api/v1/files` - `GET /api/v1/activity` -
`GET /api/v1/security/status` - `GET /api/v1/integrations` -
`POST /api/v1/integrations/{integration_id}/connect` -
`DELETE /api/v1/integrations/{integration_id}` --- only for
disconnecting the user's integration, not general data deletion; enforce
authorization and confirmation.

API contract must define: - Request/response schemas and validation
errors - Pagination format - Authentication/session strategy -
Tenant/workspace scoping - Rate limits - Idempotency for task creation
and consequential operations - Approval token/payload binding - Error
format and request/correlation IDs - Task status/event model - File
upload constraints - Versioning and compatibility - No secrets or
confidential content in error responses

## 20. Backend/security architecture assumptions to document

The UI should anticipate this future architecture: - Reverse proxy/TLS
in front of application services - Stateless web/API instances behind a
load balancer when scaling is needed - Durable job queue for
long-running tasks; workers separate from web requests - Database with
tenant-level authorization and least-privilege roles - Private
file/object storage - Cache only safe, properly scoped data; no public
caching of private workspace data - Centralized audit events and
monitoring - Secrets managed server-side - Outbound network
policy/egress gateway for external AI providers and integrations -
Isolated browser/code execution workers with restricted
filesystem/network access - Backups and tested restore procedures - Rate
limits, quotas, queue backpressure, retries and idempotency - Horizontal
scaling and load testing when traffic grows

**Scale note:** Do not promise "millions of concurrent users" from the
UI design or a single VPS. Design the app to be stateless and
horizontally scalable, then validate actual capacity with load, spike,
soak and failure tests. A Hostinger VPS can be a starting deployment
target; production scaling may require multiple nodes, managed services,
external object storage, a queue and a load balancer depending on
measured demand. Keep deployment instructions specific to the selected
VPS plan and available resources.

## 21. Hostinger VPS deployment readiness

Include a `DEPLOYMENT.md` with: - Required Node.js/runtime version -
Build and start commands - Environment variable names only (never real
secrets) - Domain and HTTPS assumptions - Reverse proxy setup
assumptions (e.g. Nginx or Caddy) - Health-check endpoint expectations -
Process management (e.g. systemd or supported process manager) - Log
location and safe rotation guidance - Backup/restore notes for frontend
configuration and uploaded artifacts if any - Upgrade/rollback steps -
Firewall ports to expose (normally only SSH/HTTP/HTTPS as required;
never expose database/Redis publicly) - Deployment smoke-test checklist

Do not include real API keys, passwords, private IPs, or production
credentials in generated files. Do not expose development ports
publicly. Do not run the frontend as root. Prefer a non-root deployment
user and least-privilege permissions.

## 22. Performance and scale-conscious frontend

-   Use route-level code splitting and lazy-load heavy sections.
-   Optimize images and fonts; avoid unnecessarily large bundles.
-   Add pagination/virtualization for genuinely large lists.
-   Use debounced search with server-side filtering.
-   Cache only non-sensitive data with explicit cache keys scoped to
    tenant/user as appropriate.
-   Ensure task polling has bounded frequency and exponential backoff;
    prefer server-sent events/WebSockets only when backend supports
    them.
-   Add request cancellation for navigation changes.
-   Provide rate-limit/queue messages in the UI.
-   Never claim that frontend caching or a load balancer alone makes the
    product scalable.

## 23. Accessibility, quality and acceptance criteria

The MVP is acceptable only if: - All primary navigation items work. -
Core task flow can be demonstrated in mock mode without a backend. -
Every mock action is clearly labelled and cannot be mistaken for real
execution. - Login/register pages have validation and error states, but
demo auth is not represented as secure production auth. - The UI is
responsive at mobile, tablet and desktop widths. - Keyboard navigation
and focus indicators work. - Components have accessible labels; color is
not the only status indicator. - No private content or secrets are
hardcoded into source. - No dangerous action is executable without a
clear confirmation/review flow. - File sharing/deletion UI communicates
exact scope and consequences. - API calls are isolated behind the API
adapter. - `API_CONTRACT.md`, `README.md`, `.env.example` and
`DEPLOYMENT.md` are included. - Lint, typecheck, tests and production
build run successfully. - No placeholder links/buttons silently do
nothing; they either work in demo mode, show "backend required", or are
disabled with an explanation. - No fake charts/metrics are shown as real
data. - Error states are helpful and do not leak stack traces or
secrets.

## 24. Required deliverables from the Cloud AI builder

Create a complete runnable frontend project containing: 1. Polished
responsive dashboard and all pages in Sections 5--16. 2. Reusable design
system and components. 3. Mock data and deterministic demo workflows. 4.
`AgentApi` interface plus `MockAgentApi` and `HttpAgentApi` adapter
skeleton. 5. `API_CONTRACT.md`. 6. `README.md` with local setup, scripts
and project structure. 7. `.env.example` containing placeholder variable
names only. 8. `DEPLOYMENT.md` for Hostinger VPS. 9.
`SECURITY_AND_PRIVACY.md` describing what is enforced now versus
backend-required. 10. Tests for core UI flows and API adapter behavior.
11. Lint/typecheck/build scripts. 12. A final implementation report
listing completed screens, known limitations, commands run, test results
and backend work still required.

## 25. Exact instructions to the AI builder

Follow this process: 1. Inspect the existing project/repository before
changing anything. 2. If there is existing code, preserve working
functionality and report proposed major changes before destructive
rewrites. 3. Implement the design system and app shell first. 4. Build
the main task and approval flows using mock data. 5. Implement all
required loading, empty, error, permission and demo states. 6. Define
API interfaces and write the API contract before wiring screens to mock
services. 7. Add responsive and accessibility behavior. 8. Add
documentation and tests. 9. Run lint, typecheck, tests and production
build; fix failures instead of claiming success. 10. Provide a final
report with exact files changed, commands run, actual test outcomes,
unresolved risks and clear instructions for the next backend integration
step.

Do not: - Claim the AI Agent is fully functional before the backend
exists. - Put API secrets or private credentials in frontend code. -
implement frontend-only authorization as a security boundary. - allow
confidential data to be sent externally by default. - enable
file/database record deletion without explicit, scoped approval. -
expose the app, database or Redis publicly with development settings. -
silently replace failed real API calls with mock successes. - claim
millions of users are supported without load-test evidence. - use
destructive database operations to "clean up" a project without explicit
authorization.

------------------------------------------------------------------------

## Final product principle

**Build the dashboard as a trustworthy control panel for a future AI
agent---not as a fake AI demo.** The user must always be able to
understand what the Agent intends to do, what it can access, whether
data will leave the workspace, which actions require approval, what
actually happened, and how to stop or review it.
