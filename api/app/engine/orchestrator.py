"""Orchestrator: plans tasks and advances approved plans one step at a time.

It never runs tools itself. For each step it re-evaluates the policy with fresh settings,
re-verifies any approval binding, then hands the step to the tool runner queue.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import (
    ApprovalCategory,
    ApprovalStatus,
    DataClass,
    ExecutionState,
    JobQueue,
    RiskLevel,
    StepState,
    TaskStatus,
    WaitingFor,
)
from app.engine import queue as Q
from app.engine.canonical import args_hash as compute_args_hash
from app.engine.canonical import canonical_json, sha256_hex
from app.engine.env import build_env
from app.engine.planner import PlanError, make_plan
from app.engine.policy import POLICY_VERSION, Decision, evaluate_model_transfer, evaluate_step
from app.engine.providers import ModelError, ModelGateway
from app.engine.records import audit, event, notify, transition
from app.engine.tools import REGISTRY
from app.engine.tools.base import PlanEnv
from app.models import ApprovalRequest, Artifact, Task, TaskStep
from app.services.approvals import new_approval, verify_binding

MODEL_PLAN_OP = "model.plan"
TERMINAL = {TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled, TaskStatus.partially_completed}


class RetryLater(Exception):
    """The job should be retried with backoff (transient failure)."""


def _lock_task(db: Session, workspace_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
    return db.execute(
        select(Task).where(Task.workspace_id == workspace_id, Task.id == task_id).with_for_update()
    ).scalar_one_or_none()


def current_steps(db: Session, task: Task, lock: bool = False) -> list[TaskStep]:
    q = (
        select(TaskStep)
        .where(
            TaskStep.workspace_id == task.workspace_id,
            TaskStep.task_id == task.id,
            TaskStep.plan_version == task.plan_version,
        )
        .order_by(TaskStep.position)
    )
    if lock:
        q = q.with_for_update()
    return list(db.execute(q).scalars())


# ---------------------------------------------------------------- planning
def _plan_binding(task: Task, env: PlanEnv, gw: ModelGateway, feedback: str | None) -> tuple[str, list[str]]:
    info = gw.info
    bound = {
        "prompt_sha256": sha256_hex(task.prompt),
        "title": task.title,
        "attachments": sorted(str(f) for f in env.attached_files),
        "provider": info.label,
        "model": info.model,
        "feedback_sha256": sha256_hex(feedback or ""),
    }
    return compute_args_hash(MODEL_PLAN_OP, bound), [info.label]


def handle_plan(db: Session, job: Q.ClaimedJob, settings: Settings) -> None:
    assert job.task_id is not None
    task = _lock_task(db, job.workspace_id, job.task_id)
    if task is None or TaskStatus(task.status) != TaskStatus.queued:
        return  # stale or duplicate job: nothing to do
    feedback = job.payload.get("feedback")
    env = build_env(db, task, settings)
    gw = ModelGateway(db, settings)
    if not gw.info.configured:
        task.waiting_for = WaitingFor.planning_service.value
        event(
            db,
            task,
            "task.waiting",
            "No approved AI model is configured, so the task waits. Nothing was sent anywhere.",
            "warn",
        )
        audit(
            db,
            task.workspace_id,
            "task.waiting_for_model",
            "task",
            f"T-{task.number}: waiting — no model configured",
            task_id=task.id,
            job_id=job.id,
        )
        return

    decision = evaluate_model_transfer(env, DataClass(task.data_classification), "The task text and attachment names")
    authorised = False
    approval: ApprovalRequest | None = None
    if decision.outcome == "deny":
        task.error_message = decision.reasons[0]
        transition(db, task, TaskStatus.failed, "Planning blocked by policy: " + decision.reasons[0])
        audit(
            db,
            task.workspace_id,
            "policy.blocked",
            "security",
            f"T-{task.number}: {decision.reasons[0]}",
            task_id=task.id,
            job_id=job.id,
            metadata={"reason": decision.reasons[0], "rules": decision.rules},
        )
        return
    if decision.outcome == "require_approval":
        bound_hash, targets = _plan_binding(task, env, gw, feedback)
        approval = db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.workspace_id == task.workspace_id,
                ApprovalRequest.task_id == task.id,
                ApprovalRequest.operation == MODEL_PLAN_OP,
                ApprovalRequest.args_hash == bound_hash,
            )
            .order_by(ApprovalRequest.requested_at.desc())
            .limit(1)
            .with_for_update()
        ).scalar_one_or_none()
        if approval is not None and approval.status == ApprovalStatus.pending.value:
            task.waiting_for = WaitingFor.approval.value
            return
        ok = approval is not None and (
            verify_binding(
                db,
                approval,
                workspace_id=task.workspace_id,
                operation=MODEL_PLAN_OP,
                args_hash=bound_hash,
                targets=targets,
                step_id=None,
                policy_version=POLICY_VERSION,
            )
            is None
        )
        if not ok:
            if approval is not None and approval.status == ApprovalStatus.approved.value:
                approval.execution_state = ExecutionState.invalidated.value
            a = new_approval(
                db,
                workspace_id=task.workspace_id,
                requested_by=task.created_by,
                actor_user_id=None,
                category=ApprovalCategory.external_transfer,
                title=f"Send T-{task.number} to {gw.info.label} for planning",
                reason="The agent needs the AI model to plan this task. " + " ".join(decision.reasons),
                affected=["Task title and description", *[f.name for f in env.attached_files.values()][:5]],
                leaves=True,
                destination=f"{gw.info.label} ({gw.info.model})",
                scope_summary="Task text and the names of attached files (not their contents)",
                consequences="The provider receives this text under its own terms. Secrets matching known patterns are redacted first.",
                reversible="No — once sent, the provider has the text.",
                risk=RiskLevel.medium,
                task_id=task.id,
                operation=MODEL_PLAN_OP,
                args_hash=bound_hash,
                targets=targets,
                policy_version=POLICY_VERSION,
            )
            task.waiting_for = WaitingFor.approval.value
            event(
                db,
                task,
                "approval.requested",
                f"Waiting for approval to send the task to {gw.info.label} (request #{a.number}).",
                "warn",
            )
            return
        authorised = True
    else:
        authorised = decision.data_leaves

    transition(db, task, TaskStatus.planning, f"Planning with {gw.info.label}")
    db.flush()
    try:
        result = make_plan(
            gw,
            workspace_id=task.workspace_id,
            task_id=task.id,
            title=task.title,
            prompt=task.prompt,
            task_type=task.type,
            mode=task.mode,
            env=env,
            settings=settings,
            external_transfer_authorised=authorised,
            feedback=feedback,
        )
    except ModelError as e:
        if e.retryable and job.attempts < job.max_attempts:
            transition(
                db,
                task,
                TaskStatus.queued,
                f"The AI model is unavailable ({e.code}); retrying shortly",
                WaitingFor.planning_service,
            )
            db.commit()
            raise RetryLater(e.code) from None
        task.error_message = e.message
        transition(db, task, TaskStatus.failed, f"Planning failed: {e.message}")
        return
    except PlanError as e:
        task.error_message = e.message
        transition(db, task, TaskStatus.failed, f"Planning failed: {e.message}")
        audit(
            db,
            task.workspace_id,
            "plan.invalid_output",
            "error",
            f"T-{task.number}: {e.message}",
            task_id=task.id,
            job_id=job.id,
        )
        return

    if approval is not None:
        approval.execution_state = ExecutionState.executed.value
    version = task.plan_version + 1
    blocked = needs = 0
    for st in result.steps:
        tool = REGISTRY[st.tool_id]
        outcome = st.decision.outcome
        blocked += outcome == "deny"
        needs += outcome == "require_approval"
        db.add(
            TaskStep(
                workspace_id=task.workspace_id,
                task_id=task.id,
                plan_version=version,
                position=st.position,
                step_key=st.key,
                title=st.goal,
                description=st.expected_output or st.goal,
                tool=tool.label,
                tool_id=st.tool_id,
                risk=st.risk,
                requires_approval=outcome == "require_approval",
                state=StepState.blocked.value if outcome == "deny" else StepState.not_started.value,
                selected=outcome != "deny",
                args=st.args,
                args_hash=st.args_hash,
                permissions=st.permissions,
                classifications=st.classifications,
                destinations=st.destinations,
                impact=st.impact,
                policy=st.decision.to_json(),
                idempotent=st.idempotent,
                expected_output=st.expected_output,
                timeout_seconds=st.timeout_seconds,
                max_attempts=st.max_attempts,
                error=st.decision.reasons[0] if outcome == "deny" else None,
            )
        )
    task.plan_version = version
    task.plan_summary = result.summary or None
    sources = sorted(
        {d for st in result.steps for d in st.destinations} | {f.name for f in env.attached_files.values()}
    )
    task.plan_meta = {
        "data_sources": sources[:20],
        "destination": "This workspace (report and step results)",
        "provider": gw.info.label,
        "model": gw.info.model,
        "provider_location": gw.info.location,
        "repaired": result.repaired,
        "ignored_model_fields": result.ignored_fields,
        "policy_version": POLICY_VERSION,
    }
    msg = f"Plan ready: {len(result.steps)} steps"
    if needs:
        msg += f", {needs} will ask for approval"
    if blocked:
        msg += f", {blocked} blocked by policy"
    transition(db, task, TaskStatus.awaiting_approval, msg)
    if result.ignored_fields:
        event(
            db,
            task,
            "plan.note",
            f"{result.ignored_fields} extra fields in the model's plan were ignored (the server decides permissions and approvals).",
            "note",
        )
    audit(
        db,
        task.workspace_id,
        "plan.created",
        "plan",
        f"T-{task.number}: {msg}",
        task_id=task.id,
        job_id=job.id,
        metadata={"steps": len(result.steps), "blocked": blocked, "needs_approval": needs, "version": version},
    )
    notify(
        db,
        task.workspace_id,
        task.created_by,
        "Plan ready",
        "list-checks",
        f"T-{task.number}: plan ready for review",
        f"/tasks/{task.id}/plan",
    )


# ---------------------------------------------------------------- execution
def _step_approval(db: Session, task: Task, step: TaskStep, decision: Decision, env: PlanEnv) -> ApprovalRequest:
    tool = REGISTRY[step.tool_id or ""]
    leaves = decision.data_leaves
    dest = ", ".join(step.destinations) or "This workspace"
    a = new_approval(
        db,
        workspace_id=task.workspace_id,
        requested_by=task.created_by,
        actor_user_id=None,
        category=ApprovalCategory(decision.approval_category or ApprovalCategory.external_transfer.value),
        # Server-written title; the model's wording is labelled as such in the reason.
        title=f"T-{task.number} step {step.step_key}: {tool.label}"[:300],
        reason=" ".join(decision.reasons) + f" AI-written goal: “{step.title[:200]}”.",
        # The exact, complete arguments (bounded by each tool's schema) — never truncated.
        affected=[f"{k}: {v if isinstance(v, str) else canonical_json(v)}" for k, v in (step.args or {}).items()]
        or [tool.label],
        leaves=leaves,
        destination=dest,
        scope_summary=f"{tool.label} · data: {', '.join(step.classifications) or 'none'}",
        consequences=tool.description,
        reversible="No"
        if leaves or step.impact in ("publish", "send_message", "production_change")
        else "The result stays in this workspace.",
        risk=RiskLevel.high
        if step.impact in ("production_change", "publish", "send_message", "sensitive_change")
        else RiskLevel.medium,
        task_id=task.id,
        step_id=step.id,
        operation=step.tool_id,
        args_hash=step.args_hash,
        targets=list(step.destinations),
        policy_version=POLICY_VERSION,
    )
    step.approval_id = a.id
    return a


def handle_execute(db: Session, job: Q.ClaimedJob, settings: Settings) -> None:
    assert job.task_id is not None
    task = _lock_task(db, job.workspace_id, job.task_id)
    if task is None:
        return
    status = TaskStatus(task.status)
    if status in TERMINAL or status in (
        TaskStatus.paused,
        TaskStatus.awaiting_approval,
        TaskStatus.planning,
        TaskStatus.needs_input,
    ):
        return
    if status == TaskStatus.queued:
        transition(db, task, TaskStatus.running, "Execution started")
    steps = current_steps(db, task, lock=True)
    if any(s.state == StepState.in_progress.value for s in steps):
        return  # a tool is running; it queues the next execute when it finishes
    env = build_env(db, task, settings)
    for k, s in ((s.step_key, s) for s in steps if s.state == StepState.done.value):
        env.step_outputs_classification[k] = str((s.output or {}).get("_classification", "confidential"))

    for step in steps:
        if not step.selected or step.state != StepState.not_started.value:
            continue
        tool = REGISTRY.get(step.tool_id or "")
        args_obj: Any = None
        integrity_error: str | None = None
        if tool is not None:
            try:
                args_obj = tool.args_model.model_validate(step.args)
            except ValidationError:
                integrity_error = "The stored arguments are no longer valid; the step will not run."
            if args_obj is not None and compute_args_hash(step.tool_id or "", step.args) != step.args_hash:
                integrity_error = "The step's arguments changed after planning; the step will not run."
        if integrity_error is not None:
            decision = Decision("deny", [integrity_error], rules=["integrity.args_hash"])
        else:
            decision = evaluate_step(tool, args_obj, env, settings, task.mode)
        step.policy = decision.to_json()
        if decision.outcome == "deny":
            step.state = StepState.blocked.value
            step.error = decision.reasons[0]
            event(db, task, "step.blocked", f"Step {step.step_key} blocked: {decision.reasons[0]}", "warn")
            audit(
                db,
                task.workspace_id,
                "policy.blocked",
                "security",
                f"T-{task.number} step {step.step_key} blocked: {decision.reasons[0]}",
                task_id=task.id,
                job_id=job.id,
                target_type="step",
                target_id=str(step.id),
                metadata={"reason": decision.reasons[0], "tool": step.tool_id, "rules": decision.rules},
            )
            continue
        if decision.outcome == "require_approval":
            a = db.get(ApprovalRequest, step.approval_id) if step.approval_id else None
            if a is not None and a.status == ApprovalStatus.pending.value:
                step.state = StepState.awaiting_approval.value
                transition(
                    db,
                    task,
                    TaskStatus.needs_input,
                    f"Waiting for approval of step {step.step_key}",
                    WaitingFor.approval,
                )
                return
            usable = (
                a is not None
                and a.status == ApprovalStatus.approved.value
                and (
                    verify_binding(
                        db,
                        a,
                        workspace_id=task.workspace_id,
                        operation=step.tool_id or "",
                        args_hash=step.args_hash,
                        targets=list(step.destinations),
                        step_id=step.id,
                        policy_version=POLICY_VERSION,
                    )
                    is None
                )
            )
            if not usable:
                if a is not None and a.status == ApprovalStatus.approved.value:
                    a.execution_state = ExecutionState.invalidated.value
                    event(
                        db,
                        task,
                        "approval.invalidated",
                        f"The approval for step {step.step_key} no longer matches the action; a new approval is needed.",
                        "warn",
                    )
                new = _step_approval(db, task, step, decision, env)
                step.state = StepState.awaiting_approval.value
                transition(
                    db,
                    task,
                    TaskStatus.needs_input,
                    f"Waiting for approval of step {step.step_key} (request #{new.number})",
                    WaitingFor.approval,
                )
                return
        # allowed (or approved): hand over to the isolated tool runner
        step.state = StepState.in_progress.value
        Q.enqueue(
            db,
            workspace_id=task.workspace_id,
            kind="tool.run",
            queue=JobQueue.tools,
            task_id=task.id,
            step_id=step.id,
            dedupe_key=f"tool:{step.id}:{step.approval_id or '-'}:{step.attempts}",
            max_attempts=max(1, step.max_attempts),
            payload={"plan_version": task.plan_version},
            settings=settings,
            internal=True,
        )
        event(db, task, "step.queued", f"Step {step.step_key} queued: {step.title}")
        return
    _finalize(db, task, steps, job)


def _finalize(db: Session, task: Task, steps: list[TaskStep], job: Q.ClaimedJob) -> None:
    # Steps blocked at planning time were never part of the approved run (selected=False);
    # steps blocked or rejected during the run count against completion.
    selected = [s for s in steps if s.selected]
    done = [s for s in selected if s.state == StepState.done.value]
    not_done = [s for s in selected if s.state != StepState.done.value]
    if selected and len(done) == len(selected):
        dst, verdict = TaskStatus.completed, "All steps finished"
    elif done:
        dst, verdict = TaskStatus.partially_completed, f"{len(done)} of {len(selected)} steps finished"
    else:
        dst, verdict = TaskStatus.failed, "No step could be completed"
    arts = (
        db.execute(select(Artifact.name).where(Artifact.workspace_id == task.workspace_id, Artifact.task_id == task.id))
        .scalars()
        .all()
    )
    issues = "; ".join(f"{s.step_key} {s.state}: {(s.error or '')[:120]}" for s in not_done) or "None"
    task.report = {
        "summary": f"{verdict}. " + " ".join(str((s.output or {}).get("_summary", ""))[:200] for s in done)[:1500],
        "open_issues": issues[:1500],
        "next_step": (
            f"Review the report{'s' if len(arts) > 1 else ''}: {', '.join(arts)[:300]}"
            if arts
            else "Review the step results."
        )
        if dst != TaskStatus.failed
        else "Check the blocked or failed steps, adjust settings or the task, and create a new plan.",
    }
    if dst == TaskStatus.failed:
        task.error_message = issues[:500]
    transition(db, task, dst, verdict)
    notify(
        db,
        task.workspace_id,
        task.created_by,
        "Task finished" if dst != TaskStatus.failed else "Task failed",
        "circle-check" if dst == TaskStatus.completed else "triangle-alert",
        f"T-{task.number}: {verdict}",
        f"/tasks/{task.id}",
    )
    audit(
        db,
        task.workspace_id,
        "task.finished",
        "execution",
        f"T-{task.number}: {verdict}",
        task_id=task.id,
        job_id=job.id,
        metadata={"status": dst.value, "done": len(done), "total": len(selected)},
    )


def on_dead(db: Session, job: Q.ClaimedJob, error: str) -> None:
    """A planning/execution job exhausted its retries: fail the task visibly."""
    if job.task_id is None:
        return
    task = _lock_task(db, job.workspace_id, job.task_id)
    if task is None or TaskStatus(task.status) in TERMINAL:
        return
    task.error_message = f"Background job failed: {error}"[:500]
    if TaskStatus(task.status) == TaskStatus.planning or TaskStatus(task.status) == TaskStatus.queued:
        transition(db, task, TaskStatus.failed, "The planner could not finish after several attempts")
    elif TaskStatus(task.status) in (TaskStatus.running, TaskStatus.needs_input, TaskStatus.paused):
        transition(db, task, TaskStatus.failed, "Execution could not continue after several attempts")
