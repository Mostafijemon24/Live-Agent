"""Explicit task status state machine.

This is the only place that decides whether a status change is legal. Services
call `assert_transition` before every update; tests cover every pair.

Phase 2 note: there is no planner or execution engine. User actions that would
make a task progress move it to `queued` with a `waiting_for` reason instead of
pretending it runs.
"""

from __future__ import annotations

from app.core.errors import ApiError
from app.domain.enums import TaskStatus as S

TERMINAL: frozenset[S] = frozenset({S.completed, S.failed, S.cancelled, S.partially_completed})

TRANSITIONS: dict[S, frozenset[S]] = {
    S.draft: frozenset({S.queued, S.cancelled}),
    S.queued: frozenset({S.planning, S.running, S.cancelled, S.failed}),
    S.planning: frozenset({S.awaiting_approval, S.queued, S.failed, S.cancelled}),
    S.awaiting_approval: frozenset({S.queued, S.running, S.planning, S.cancelled}),
    S.running: frozenset({S.paused, S.needs_input, S.completed, S.partially_completed, S.failed, S.cancelled}),
    S.needs_input: frozenset({S.queued, S.running, S.cancelled}),
    S.paused: frozenset({S.queued, S.running, S.cancelled}),
    S.completed: frozenset(),
    S.failed: frozenset(),
    S.cancelled: frozenset(),
    S.partially_completed: frozenset(),
}

# Which user-facing actions are offered in each status (mirrors the prototype's canPause/canResume/... rules).
ACTIONS: dict[S, tuple[str, ...]] = {
    S.draft: ("cancel",),
    S.queued: ("cancel",),
    S.planning: ("cancel",),
    S.awaiting_approval: ("approve_plan", "reject_plan", "revise_plan", "cancel"),
    S.running: ("pause", "cancel"),
    S.needs_input: ("answer", "cancel"),
    S.paused: ("resume", "cancel"),
    S.completed: (),
    S.failed: (),
    S.cancelled: (),
    S.partially_completed: (),
}

assert set(TRANSITIONS) == set(S), "every status needs a transition entry"


def can_transition(src: S, dst: S) -> bool:
    return dst in TRANSITIONS[src]


def assert_transition(src: S, dst: S) -> None:
    if not can_transition(src, dst):
        raise ApiError(
            409,
            "invalid_state_transition",
            f"A task that is {src.value.replace('_', ' ')} cannot become {dst.value.replace('_', ' ')}.",
            details={"from": src.value, "to": dst.value},
        )


def allowed_actions(status: S, has_plan: bool) -> list[str]:
    acts = list(ACTIONS[status])
    if status == S.awaiting_approval and not has_plan:
        acts = [a for a in acts if a not in ("approve_plan", "reject_plan", "revise_plan")]
    return acts


def require_action(status: S, action: str, has_plan: bool = True) -> None:
    if action not in allowed_actions(status, has_plan):
        raise ApiError(
            409,
            "action_not_allowed",
            f"You can't {action.replace('_', ' ')} a task that is {status.value.replace('_', ' ')}.",
            details={"status": status.value, "action": action},
        )
