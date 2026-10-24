# Mock-only functionality

Everything below runs in browser memory and resets on reload. Nothing is sent anywhere.

- **Auth:** sign-up, sign-in, forgot/reset password, email verification — validation only; no account, session or email. Password `error` simulates failure.
- **Agent:** no AI. Plans are fixed templates per task type; "Planning" is a 1.6 s timer. Plan revisions don't change the plan.
- **Task execution:** status changes (approve, pause, resume, cancel, answer) are state flips. Step progress, logs and artifacts are generated from the status.
- **Retry:** intentionally not simulated — explains backend requirement.
- **Approvals:** approve/reject/request changes only update status and activity.
- **Files:** no real upload or file reading. "Add sample file" fakes Uploading → Scanning → Processing → Ready. Classification changes are local. Deletion creates an approval request only.
- **Automations:** saved locally; scheduled ones stay paused; "Run now" queues a sample task that never runs.
- **Integrations:** none connected. WordPress shows a "Demo" sandbox label; Connect always explains backend requirement. No credentials are collected.
- **Reports/Activity/Notifications:** sample data plus events from your demo actions. Export/download are backend-required notices.
- **Security & Privacy / Settings:** preferences only, labelled not enforced. Export and account-deletion requests are notices.
- **Counts on Overview:** derived from sample tasks, labelled Demo data.
- **Persistence:** only the current screen name is stored (`localStorage: steward.route`).
