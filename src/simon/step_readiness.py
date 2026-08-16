from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.actions import Action, list_actions_for_plan
from simon.capabilities import available_capability_ids
from simon.goals import get_goal
from simon.plans import Plan, get_active_plan
from simon.verification import VerificationResult, list_verification_results

StepState = Literal["READY", "BLOCKED", "IN_PROGRESS", "VERIFIED"]


@dataclass(frozen=True, slots=True)
class StepBlocker:
    kind: str
    detail: str


@dataclass(frozen=True, slots=True)
class StepReadiness:
    step_id: str
    description: str
    capability: str | None
    state: StepState
    blockers: tuple[StepBlocker, ...]
    related_action_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlanReadiness:
    plan: Plan
    available_capabilities: tuple[str, ...]
    next_step: StepReadiness | None
    steps: tuple[StepReadiness, ...]


def evaluate_active_plan(
    database_path: Path,
    *,
    goal_id: str,
    available_capabilities: frozenset[str] | None = None,
) -> PlanReadiness:
    goal = get_goal(database_path, goal_id)
    if goal is None:
        raise ValueError(f"goal não encontrado: {goal_id}")

    plan = get_active_plan(database_path, goal_id)
    if plan is None:
        raise ValueError(f"goal não possui plan ACTIVE: {goal_id}")

    capabilities = (
        available_capability_ids()
        if available_capabilities is None
        else available_capabilities
    )
    actions = list_actions_for_plan(database_path, plan.id)
    actions_by_step: dict[str, list[Action]] = {}
    for action in actions:
        actions_by_step.setdefault(action.step_id, []).append(action)

    verified_steps = {
        step_id
        for step_id, step_actions in actions_by_step.items()
        if _verified_action(database_path, step_actions) is not None
    }

    assessments: list[StepReadiness] = []
    for raw_step in plan.steps:
        step_id = _required_text(raw_step, "id")
        description = _required_text(raw_step, "description")
        capability = _optional_text(raw_step.get("capability"))
        step_actions = actions_by_step.get(step_id, [])

        verified_action = _verified_action(database_path, step_actions)
        if verified_action is not None:
            assessments.append(
                StepReadiness(
                    step_id=step_id,
                    description=description,
                    capability=capability,
                    state="VERIFIED",
                    blockers=(),
                    related_action_id=verified_action.id,
                )
            )
            continue

        active_action = _latest_action_with_statuses(
            step_actions,
            {"PENDING", "RUNNING", "WAITING"},
        )
        if active_action is not None:
            assessments.append(
                StepReadiness(
                    step_id=step_id,
                    description=description,
                    capability=capability,
                    state="IN_PROGRESS",
                    blockers=(),
                    related_action_id=active_action.id,
                )
            )
            continue

        blockers: list[StepBlocker] = []

        if goal.status != "ACTIVE":
            blockers.append(
                StepBlocker(
                    kind="GOAL_NOT_ACTIVE",
                    detail=f"goal está {goal.status}",
                )
            )

        dependencies = _dependencies(raw_step)
        for dependency in dependencies:
            if dependency not in verified_steps:
                blockers.append(
                    StepBlocker(
                        kind="DEPENDENCY_NOT_VERIFIED",
                        detail=dependency,
                    )
                )

        completed_unverified = _latest_action_with_statuses(step_actions, {"COMPLETED"})
        if completed_unverified is not None:
            latest_verification = _latest_verification_result(
                database_path,
                completed_unverified,
            )
            if latest_verification is None:
                blockers.append(
                    StepBlocker(
                        kind="VERIFICATION_PENDING",
                        detail=completed_unverified.id,
                    )
                )
            else:
                blockers.extend(_verification_blockers(latest_verification))

        unsuccessful = _latest_action_with_statuses(
            step_actions,
            {"FAILED", "BLOCKED", "DENIED", "INTERRUPTED", "CANCELLED"},
        )
        if unsuccessful is not None:
            blockers.append(
                StepBlocker(
                    kind="PREVIOUS_ATTEMPT_REQUIRES_REVIEW",
                    detail=f"{unsuccessful.id}: {unsuccessful.status}",
                )
            )

        if capability != "user.ask":
            for precondition in _preconditions(raw_step):
                blockers.append(
                    StepBlocker(
                        kind="PRECONDITION_UNRESOLVED",
                        detail=precondition,
                    )
                )

        if capability is None:
            blockers.append(
                StepBlocker(
                    kind="CAPABILITY_UNSPECIFIED",
                    detail="o passo não declara capability",
                )
            )
        elif capability not in capabilities:
            blockers.append(
                StepBlocker(
                    kind="CAPABILITY_UNAVAILABLE",
                    detail=capability,
                )
            )

        assessments.append(
            StepReadiness(
                step_id=step_id,
                description=description,
                capability=capability,
                state="BLOCKED" if blockers else "READY",
                blockers=tuple(blockers),
            )
        )

    next_step = next((step for step in assessments if step.state == "READY"), None)
    return PlanReadiness(
        plan=plan,
        available_capabilities=tuple(sorted(capabilities)),
        next_step=next_step,
        steps=tuple(assessments),
    )


def _verified_action(database_path: Path, actions: list[Action]) -> Action | None:
    for action in reversed(actions):
        if action.status != "COMPLETED":
            continue
        results = list_verification_results(
            database_path,
            subject_type="ACTION",
            subject_id=action.id,
        )
        if any(result.status == "VERIFIED" for result in results):
            return action
    return None


def _latest_action_with_statuses(actions: list[Action], statuses: set[str]) -> Action | None:
    for action in reversed(actions):
        if action.status in statuses:
            return action
    return None


def _required_text(step: dict[str, object], key: str) -> str:
    value = step.get(key)
    if not isinstance(value, str):
        raise TypeError(f"passo persistido possui {key} com tipo inválido")
    if not value.strip():
        raise ValueError(f"passo persistido possui {key} vazio")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("capability persistida possui tipo inválido")
    normalized = value.strip()
    return normalized or None


def _dependencies(step: dict[str, object]) -> tuple[str, ...]:
    value = step.get("depends_on", ())
    if not isinstance(value, (list, tuple)):
        raise TypeError("depends_on persistido possui tipo inválido")
    dependencies: list[str] = []
    for dependency in value:
        if not isinstance(dependency, str):
            raise TypeError("depends_on persistido possui valor com tipo inválido")
        if not dependency.strip():
            raise ValueError("depends_on persistido possui valor vazio")
        dependencies.append(dependency.strip())
    return tuple(dependencies)


def _preconditions(step: dict[str, object]) -> tuple[str, ...]:
    value = step.get("preconditions", ())
    if not isinstance(value, (list, tuple)):
        raise TypeError("preconditions persistidas possuem tipo inválido")
    preconditions: list[str] = []
    for precondition in value:
        if not isinstance(precondition, str):
            raise TypeError("precondition persistida possui valor com tipo inválido")
        if not precondition.strip():
            raise ValueError("precondition persistida possui valor vazio")
        preconditions.append(precondition.strip())
    return tuple(preconditions)


def _latest_verification_result(
    database_path: Path,
    action: Action,
) -> VerificationResult | None:
    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
    )
    return results[-1] if results else None


def _verification_blockers(result: VerificationResult) -> tuple[StepBlocker, ...]:
    if result.status == "ASSESSED":
        verdict = result.observed.get("verdict")
        if verdict == "SATISFIED":
            return (
                StepBlocker(
                    kind="ASSESSED_SATISFIED_REQUIRES_CONFIRMATION",
                    detail=result.id,
                ),
            )
        if verdict == "NOT_SATISFIED":
            return (
                StepBlocker(
                    kind="CRITERION_NOT_SATISFIED",
                    detail=result.id,
                ),
            )
        if verdict == "UNCLEAR":
            return (
                StepBlocker(
                    kind="ASSESSMENT_INCONCLUSIVE",
                    detail=result.id,
                ),
            )
        return (
            StepBlocker(
                kind="VERIFICATION_ASSESSED",
                detail=result.id,
            ),
        )

    if result.status == "FAILED":
        return (StepBlocker(kind="VERIFICATION_FAILED", detail=result.id),)
    if result.status == "INCONCLUSIVE":
        return (StepBlocker(kind="VERIFICATION_INCONCLUSIVE", detail=result.id),)
    if result.status == "VERIFIED":
        return ()
    return (StepBlocker(kind="VERIFICATION_REQUIRES_REVIEW", detail=result.id),)

