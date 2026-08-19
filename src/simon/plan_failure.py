from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from simon.actions import Action, get_action
from simon.events import Event, get_event
from simon.step_readiness import StepBlocker, StepReadiness, evaluate_active_plan
from simon.verification import VerificationResult, get_verification_result

REPLANNING_BLOCKERS = frozenset(
    {
        "VERIFICATION_FAILED",
        "VERIFICATION_INCONCLUSIVE",
        "CRITERION_NOT_SATISFIED",
        "ASSESSMENT_INCONCLUSIVE",
    }
)


@dataclass(frozen=True, slots=True)
class PlanFailureContext:
    plan_id: str
    plan_revision: int
    step_id: str
    step_description: str
    capability: str | None
    blocker_kind: str
    action_id: str
    action_kind: str
    verification_id: str
    verification_status: str
    verification_criteria: tuple[dict[str, object], ...]
    verification_observed: dict[str, object]
    evidence_events: tuple[Event, ...]

    def to_model_payload(self) -> dict[str, object]:
        return {
            "active_plan": {
                "plan_id": self.plan_id,
                "revision": self.plan_revision,
            },
            "failed_step": {
                "step_id": self.step_id,
                "description": self.step_description,
                "capability": self.capability,
                "blocker_kind": self.blocker_kind,
            },
            "action": {
                "action_id": self.action_id,
                "kind": self.action_kind,
            },
            "verification": {
                "verification_id": self.verification_id,
                "status": self.verification_status,
                "criteria": list(self.verification_criteria),
                "observed": self.verification_observed,
            },
            "evidence_events": [
                {
                    "event_id": event.id,
                    "kind": event.kind,
                    "source": event.source,
                    "payload": event.payload,
                }
                for event in self.evidence_events
            ],
        }


def get_active_plan_failure_context(
    database_path: Path,
    *,
    goal_id: str,
) -> PlanFailureContext | None:
    """Retorna a falha verificável que justifica substituir o Plan ACTIVE atual."""
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)

    for step in readiness.steps:
        blocker = _replanning_blocker(step)
        if blocker is None:
            continue

        verification = get_verification_result(database_path, blocker.detail)
        if verification is None:
            raise ValueError(f"Verification de blocker não encontrada: {blocker.detail}")
        _validate_failure_verification(verification, blocker)

        action = get_action(database_path, verification.subject_id)
        if action is None:
            raise ValueError(
                "Verification de falha referencia Action inexistente: "
                f"{verification.subject_id}"
            )
        _validate_failure_action(
            action,
            plan_id=readiness.plan.id,
            step_id=step.step_id,
        )
        if action.kind == "user.ask":
            # user.ask já possui review/retry local explícito; replan não deve atropelar esse gate.
            continue

        evidence_events = tuple(
            _required_event(database_path, event_id)
            for event_id in verification.evidence_event_ids
        )
        return PlanFailureContext(
            plan_id=readiness.plan.id,
            plan_revision=readiness.plan.revision,
            step_id=step.step_id,
            step_description=step.description,
            capability=step.capability,
            blocker_kind=blocker.kind,
            action_id=action.id,
            action_kind=action.kind,
            verification_id=verification.id,
            verification_status=verification.status,
            verification_criteria=tuple(dict(item) for item in verification.criteria),
            verification_observed=dict(verification.observed),
            evidence_events=evidence_events,
        )

    return None


def _replanning_blocker(step: StepReadiness) -> StepBlocker | None:
    return next(
        (blocker for blocker in step.blockers if blocker.kind in REPLANNING_BLOCKERS),
        None,
    )


def _validate_failure_verification(
    verification: VerificationResult,
    blocker: StepBlocker,
) -> None:
    if verification.subject_type != "ACTION":
        raise ValueError("blocker de Plan não referencia Verification de Action")

    if blocker.kind == "VERIFICATION_FAILED":
        if verification.status != "FAILED":
            raise ValueError("VERIFICATION_FAILED diverge do status persistido")
        return
    if blocker.kind == "VERIFICATION_INCONCLUSIVE":
        if verification.status != "INCONCLUSIVE":
            raise ValueError("VERIFICATION_INCONCLUSIVE diverge do status persistido")
        return
    if blocker.kind == "CRITERION_NOT_SATISFIED":
        if (
            verification.status != "ASSESSED"
            or verification.observed.get("verdict") != "NOT_SATISFIED"
        ):
            raise ValueError("CRITERION_NOT_SATISFIED diverge do assessment persistido")
        return
    if blocker.kind == "ASSESSMENT_INCONCLUSIVE":
        if verification.status != "ASSESSED" or verification.observed.get("verdict") != "UNCLEAR":
            raise ValueError("ASSESSMENT_INCONCLUSIVE diverge do assessment persistido")
        return

    raise ValueError(f"blocker não justifica replanejamento: {blocker.kind}")


def _validate_failure_action(
    action: Action,
    *,
    plan_id: str,
    step_id: str,
) -> None:
    if action.plan_id != plan_id:
        raise ValueError("Verification de falha não pertence ao Plan ACTIVE")
    if action.step_id != step_id:
        raise ValueError("Verification de falha não pertence ao step bloqueado")
    if action.status != "COMPLETED":
        raise ValueError(
            "replanejamento por Verification exige Action COMPLETED: "
            f"{action.id} está {action.status}"
        )


def _required_event(database_path: Path, event_id: str) -> Event:
    event = get_event(database_path, event_id)
    if event is None:
        raise ValueError(f"Event de evidência não encontrado: {event_id}")
    return event
