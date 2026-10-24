# Steward — AI Agent Workspace (Phase 1 design prototype)

Design-first, interactive prototype of a multi-user AI agent workspace for non-technical users. **No backend, authentication, AI, database or integration is implemented.** Every result is deterministic sample data.

## Open and preview
- Open `Steward AI Agent Workspace.dc.html` in the project preview (or any modern browser). No install, build or secrets needed.
- Start at the landing page → **Try the demo workspace** → sign-up → email verification (simulated) → onboarding → Overview.
- Shortcut: **Sign in** with any email/password. Use the password `error` to preview the failed sign-in state.
- The current screen is remembered in `localStorage` (`steward.route`) — only the route name, never form data or credentials.
- Tweaks: `startCollapsed` (sidebar rail), `compactRows` (denser tables).

## Screens (20)
1 Landing · 2 Register · 3 Login · 4 Forgot / reset password (+ email verification) · 5 Onboarding wizard (5 steps) · 6 Overview · 7 New task composer · 8 Plan review & approval · 9 Tasks list (search, 5 filters, sort, pagination, mobile cards) · 10 Task detail (7 tabs) · 11 Approvals center · 12 Files & Knowledge (+ file drawer) · 13 Automations (+ 5-step wizard) · 14 Integrations (+ manage drawer) · 15 Reports & Activity · 16 Security & Privacy · 17 Settings (8 sections) · 18 Notifications · 19 Help & Getting Started · 20 System states gallery + full-page 404.

## Responsive behaviour
- ≥ 980 px: fixed, collapsible sidebar. < 980 px: navigation drawer, tables switch to cards.
- Search hides below 640 px; layouts use wrapping flex/grid — no horizontal page scroll.

## Proposed production stack (Phase 2)
This environment can't run a Next.js toolchain, so Phase 1 is delivered as a single self-contained prototype file. When approved, port to:
- Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui + lucide-react.
- Feature folders: `features/{auth,dashboard,tasks,approvals,files,automations,integrations,reports,security,settings}`; shared UI in `components/ui` and `components/shared`; API layer in `lib/api` (`AgentApi` interface, `MockAgentApi`, `HttpAgentApi`, one env switch); schemas in `schemas/`.
- Design tokens (colors, radii, spacing) move to Tailwind config / CSS variables — values listed in `DESIGN_REVIEW.md`.

## Checks
Lint, typecheck and build do not apply to this prototype format (no package.json / toolchain). They will be set up and run in Phase 2. The prototype was loaded and checked for console errors.

See also: `DESIGN_REVIEW.md`, `BACKEND_READINESS.md`, `MOCK_ONLY.md`.
