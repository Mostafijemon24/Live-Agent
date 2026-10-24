# Design review — key decisions

## Principle
A trustworthy control panel for a future agent, not a chat clone. Every screen answers: what will the Agent do, what can it touch, does data leave, what needs me, what actually happened.

## Visual system
- **Type:** IBM Plex Sans (UI) + IBM Plex Mono (IDs, timestamps, logs, demo labels). Mono marks "system facts" so they read differently from prose.
- **Color tokens:** primary `#3448C5` (hover `#2A3AA8`, soft `#EEF1FC`), text `#172033`, secondary `#667085`, page `#F6F8FB`, surface `#FFFFFF`, border `#E4E7EC`, success `#16803C`, warning `#B54708`, danger `#B42318`, info `#175CD3`. Each status color has a matching tint for badges.
- **Shape:** 8 px controls, 10 px cards, 12 px dialogs. Shadows only on overlays (menus, dialogs, drawers).
- **Icons:** Lucide line icons throughout; icon-only buttons have `aria-label` + `title`.
- **Status never relies on color alone:** every badge has an icon and a text label.

## Honesty patterns
- Persistent dark **DEMO MODE** strip on every screen, plus a "Demo" header badge.
- KPIs carry a "DEMO DATA" tag and count only sample tasks — no charts, no fake real-time metrics.
- Features without a backend say so in place: "Backend required", "Not connected", "Coming later", "Not enforced — backend setup required".
- Every simulated success toast says it was simulated. Failed states stay failed — Retry explains why it can't safely retry rather than faking success.
- Planning ≠ completed: plans move Planning → Awaiting approval; only fully finished tasks show Completed; "Partially completed" exists.

## Approval design
- Two layers: the **plan** is approved as a whole (with per-step opt-out), and each high-impact step still needs its **own approval** at run time.
- Every approval shows action, reason, exact affected items, whether data leaves, destination, consequences, reversibility, expiry and task link.
- Category banners: external transfer and deletion (danger), production change / publish / send message (warning), permission change (info).
- "Approve once" only — no "always approve". Confirm requires acknowledging the simulation; deletion additionally requires confirming the exact item list.
- Deleting a file from Files creates a deletion approval rather than deleting.

## Privacy
- The "uploading ≠ sharing" notice is persistent on Files and repeated in the composer.
- New files default to **Unknown — sharing blocked** until classified.
- Privacy mode defaults to the safest option (Strict) and is labelled not enforced.

## Interaction & accessibility
- Visible focus ring on all controls; Escape closes dialogs/drawers/menus; dialogs use `role="dialog"` + `aria-modal`; switches use `role="switch"`; tabs use `role="tab"`.
- Field-level validation with `aria-invalid` and `role="alert"` messages; password visibility toggle.
- `prefers-reduced-motion` disables spinners/pulses; transitions are ≤ 200 ms.
- Destructive actions use outlined red buttons and always pass through a confirmation.

## Open questions for review
- Product name "Steward" is a placeholder.
- Timezone shown as Asia/Dhaka (GMT+6) by default — confirm.
- Should "Prepare changes for review" be the default mode for WordPress tasks instead of "Plan only"?
