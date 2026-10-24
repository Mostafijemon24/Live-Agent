// User-facing labels and badge colours, ported from the prototype's SM / RISK /
// WARN / CLS tables. Wire enums (snake_case) → labels and tones.
import type {
  ApprovalCategory,
  ApprovalStatus,
  ExecutionMode,
  FileClassification,
  FileStatus,
  IntegrationStatus,
  RiskLevel,
  StepRisk,
  StepState,
  TaskStatus,
  TaskType,
  ActivityType,
  PrivacyMode,
} from "@/lib/api/types";

export interface BadgeMeta {
  label: string;
  fg: string;
  bg: string;
  icon: string;
}

const N = { fg: "#475467", bg: "#F2F4F7" };
const BLUE = { fg: "#175CD3", bg: "#EFF8FF" };
const IND = { fg: "#3448C5", bg: "#EEF1FC" };
const AMB = { fg: "#B54708", bg: "#FFF6ED" };
const GRN = { fg: "#16803C", bg: "#ECFDF3" };
const RED = { fg: "#B42318", bg: "#FEF3F2" };

export const TASK_STATUS: Record<TaskStatus, BadgeMeta> = {
  draft: { label: "Draft", ...N, icon: "pencil" },
  queued: { label: "Queued", ...BLUE, icon: "clock" },
  planning: { label: "Planning", ...IND, icon: "loader" },
  awaiting_approval: { label: "Awaiting approval", ...AMB, icon: "hourglass" },
  running: { label: "Running", ...BLUE, icon: "play" },
  needs_input: { label: "Needs input", ...AMB, icon: "message-circle" },
  completed: { label: "Completed", ...GRN, icon: "circle-check" },
  failed: { label: "Failed", ...RED, icon: "circle-x" },
  paused: { label: "Paused", ...N, icon: "circle-pause" },
  cancelled: { label: "Cancelled", ...N, icon: "ban" },
  partially_completed: { label: "Partially completed", ...AMB, icon: "circle-dashed" },
};
export const TASK_STATUSES = Object.keys(TASK_STATUS) as TaskStatus[];

export const TASK_NEXT: Record<TaskStatus, string> = {
  draft: "Finish draft",
  queued: "Waiting to start",
  planning: "Plan being prepared",
  awaiting_approval: "Review plan",
  running: "View progress",
  needs_input: "Answer question",
  completed: "View report",
  failed: "See what went wrong",
  paused: "Resume or cancel",
  cancelled: "No action needed",
  partially_completed: "Review results",
};

export const APPROVAL_STATUS: Record<ApprovalStatus, BadgeMeta> = {
  pending: { label: "Pending", ...AMB, icon: "hourglass" },
  approved: { label: "Approved", ...GRN, icon: "circle-check" },
  rejected: { label: "Rejected", ...RED, icon: "circle-x" },
  changes_requested: { label: "Changes requested", ...IND, icon: "message-circle" },
  expired: { label: "Expired", ...N, icon: "clock" },
};

export const STEP_STATE: Record<StepState, BadgeMeta> = {
  done: { label: "Done", ...GRN, icon: "circle-check" },
  in_progress: { label: "In progress", ...BLUE, icon: "loader" },
  not_started: { label: "Not started", ...N, icon: "circle" },
  waiting_for_input: { label: "Waiting for input", ...AMB, icon: "message-circle" },
  skipped: { label: "Skipped", ...N, icon: "skip-forward" },
  failed: { label: "Failed", ...RED, icon: "circle-x" },
  paused: { label: "Paused", ...N, icon: "circle-pause" },
  cancelled: { label: "Cancelled", ...N, icon: "ban" },
};

export const FILE_STATUS: Record<FileStatus, BadgeMeta> = {
  uploading: { label: "Uploading", ...BLUE, icon: "upload" },
  unscanned: { label: "Not scanned", ...AMB, icon: "shield-alert" },
  scanning: { label: "Scanning", ...BLUE, icon: "scan" },
  processing: { label: "Processing", ...BLUE, icon: "loader" },
  ready: { label: "Ready", ...GRN, icon: "circle-check" },
  failed: { label: "Failed", ...RED, icon: "circle-x" },
  quarantined: { label: "Quarantined", ...RED, icon: "shield-alert" },
};

export const INTEGRATION_STATUS: Record<IntegrationStatus, BadgeMeta> = {
  demo: { label: "Demo", ...IND, icon: "flask-conical" },
  not_connected: { label: "Not connected", ...N, icon: "unplug" },
  backend_required: { label: "Backend required", ...AMB, icon: "server" },
  connected: { label: "Connected", ...GRN, icon: "circle-check" },
};

export const TASK_TYPES: { value: TaskType; label: string; icon: string }[] = [
  { value: "research", label: "Research", icon: "search" },
  { value: "website", label: "Website/WordPress", icon: "globe" },
  { value: "seo_content", label: "SEO/Content", icon: "file-text" },
  { value: "code", label: "Code", icon: "code" },
  { value: "browser", label: "Browser workflow", icon: "monitor" },
  { value: "file_analysis", label: "File analysis", icon: "file-spreadsheet" },
  { value: "custom", label: "Custom", icon: "sparkles" },
];
export const TASK_TYPE_LABEL = Object.fromEntries(TASK_TYPES.map((t) => [t.value, t.label])) as Record<TaskType, string>;
export const TASK_TYPE_ICON = Object.fromEntries(TASK_TYPES.map((t) => [t.value, t.icon])) as Record<TaskType, string>;

export const MODES: { value: ExecutionMode; label: string; description: string; disabled: boolean }[] = [
  { value: "plan_only", label: "Plan only", description: "The Agent prepares a plan and stops. Safe default.", disabled: false },
  { value: "prepare", label: "Prepare changes for review", description: "Drafts changes inside the workspace. Nothing is applied.", disabled: false },
  {
    value: "execute",
    label: "Execute approved steps",
    description: "Runs the steps you approve. Disabled until the execution engine and policy engine are installed (Phase 3).",
    disabled: true,
  },
];
export const MODE_LABEL = Object.fromEntries(MODES.map((m) => [m.value, m.label])) as Record<ExecutionMode, string>;

export const RISK_STEP: Record<StepRisk, { label: string; fg: string; bg: string }> = {
  read_only: { label: "Read only", ...GRN },
  workspace_only: { label: "Workspace only", ...N },
  prepare_only: { label: "Prepare only", ...IND },
  production_change: { label: "Production change", ...AMB },
  publish: { label: "Publish", ...AMB },
  external_transfer: { label: "External transfer", ...RED },
};

export const RISK_LEVEL: Record<RiskLevel, { label: string; color: string }> = {
  high: { label: "High", color: "#B42318" },
  medium: { label: "Medium", color: "#B54708" },
  low: { label: "Low", color: "#475467" },
};

export type Tone = "danger" | "warning" | "info" | "success";
export const TONE: Record<Tone, { fg: string; bg: string; border: string }> = {
  danger: { fg: "#B42318", bg: "#FEF3F2", border: "#FECDCA" },
  warning: { fg: "#B54708", bg: "#FFF6ED", border: "#FEDF89" },
  info: { fg: "#3448C5", bg: "#EEF1FC", border: "#C7D0F5" },
  success: { fg: "#16803C", bg: "#ECFDF3", border: "#ABEFC6" },
};

export const APPROVAL_CATEGORY: Record<ApprovalCategory, { label: string; tone: Tone; icon: string; head: string; body: string }> = {
  external_transfer: {
    label: "External data transfer",
    tone: "danger",
    icon: "send",
    head: "Data will leave your workspace",
    body: "Copies of the listed items would be sent to a service outside this workspace. Once sent, they cannot be recalled.",
  },
  production_change: {
    label: "Production website change",
    tone: "warning",
    icon: "globe",
    head: "This changes your live website",
    body: "Visitors may see the result immediately. A snapshot is taken first so the change can be undone.",
  },
  publish: {
    label: "Publish",
    tone: "warning",
    icon: "megaphone",
    head: "This will be visible to the public",
    body: "Published content can be indexed and copied by others, even if removed later.",
  },
  send_message: {
    label: "Send message",
    tone: "warning",
    icon: "mail",
    head: "A message will be sent outside the workspace",
    body: "Sent messages cannot be unsent. Check the recipient and content.",
  },
  record_deletion: {
    label: "Record deletion",
    tone: "danger",
    icon: "trash-2",
    head: "Items will be deleted",
    body: "This approval covers only the exact items listed below. Any change to the list needs a new approval.",
  },
  permission_change: {
    label: "Integration permission change",
    tone: "info",
    icon: "plug",
    head: "A connected tool will get new permissions",
    body: "The tool will be able to do more than before. You can revoke this later.",
  },
};

export const CLASSIFICATION: Record<FileClassification, { label: string; short: string; fg: string; bg: string; icon: string }> = {
  private: { label: "Private — workspace only", short: "Private", ...IND, icon: "lock" },
  approved_integration: { label: "Approved for selected integration", short: "Approved for selected integration", ...GRN, icon: "circle-check" },
  public: { label: "Public", short: "Public", ...BLUE, icon: "globe" },
  unknown: { label: "Unknown — sharing blocked", short: "Unknown", ...AMB, icon: "circle-help" },
};

export const FILE_TYPE_ICON: Record<string, string> = {
  CSV: "file-spreadsheet",
  XLSX: "file-spreadsheet",
  PDF: "file-text",
  DOCX: "file-text",
  ZIP: "file-archive",
  JS: "file-code",
  MD: "file-text",
  TXT: "file-text",
  JSON: "file-code",
  PNG: "file",
  JPG: "file",
};

export const ACTIVITY_ICON: Record<ActivityType, string> = {
  task: "plus",
  plan: "list-checks",
  approval: "shield-check",
  execution: "play",
  error: "circle-x",
  integration: "plug",
  security: "shield-alert",
  auth: "key-round",
  file: "file",
  settings: "settings",
};
export const ACTIVITY_LABEL: Record<ActivityType, string> = {
  task: "Task",
  plan: "Plan",
  approval: "Approval",
  execution: "Execution",
  error: "Error",
  integration: "Integration",
  security: "Security",
  auth: "Sign-in",
  file: "File",
  settings: "Settings",
};

export const PRIVACY_MODES: { value: PrivacyMode; label: string; description: string }[] = [
  {
    value: "strict",
    label: "Strict private mode",
    description: "Confidential data cannot leave the approved environment. Outside AI calls are blocked unless you approve a narrow exception.",
  },
  { value: "approval", label: "Approval required", description: "Every transfer outside the workspace needs your approval each time." },
  { value: "custom", label: "Custom policy", description: "Administrators choose allowed destinations and data classes. Advanced." },
];

export const TIMEZONES = ["Asia/Dhaka", "UTC", "Europe/London", "America/New_York"];
