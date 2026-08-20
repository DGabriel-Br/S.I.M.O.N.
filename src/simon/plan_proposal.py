from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from simon.context import CognitiveContext, build_cognitive_context
from simon.events import Event, append_event
from simon.goal_intake import get_goal_acceptance_open_questions
from simon.goal_verification import GoalAssessmentContext, get_latest_goal_assessment_context
from simon.goals import OPEN_STATUSES, Goal, get_goal
from simon.model_provider import ModelProvider, ModelProviderError, StructuredModelResult
from simon.plan_failure import PlanFailureContext, get_active_plan_failure_context
from simon.planning import PlanProposal, propose_plan
from simon.plans import get_active_plan
from simon.step_readiness import PlanReadiness, evaluate_active_plan


class PlanProposalGateError(RuntimeError):
    """A proposta é legítima em abstrato, mas o estado atual exige outro passo primeiro."""


@dataclass(frozen=True, slots=True)
class PendingPlanProposal:
    event_id: str
    source_goal_assessment_id: str | None
    source_completed_plan_id: str | None
    source_active_plan_id: str | None
    source_active_plan_revision: int | None
    source_failure_verification_id: str | None


@dataclass(frozen=True, slots=True)
class PlanProposalReceipt:
    goal: Goal
    context: CognitiveContext
    result: StructuredModelResult[PlanProposal]
    proposal_event: Event
    goal_assessment: GoalAssessmentContext | None
    plan_failure: PlanFailureContext | None
    open_questions: tuple[str, ...]


def find_latest_pending_plan_proposal(
    database_path: Path,
    *,
    goal_id: str,
) -> PendingPlanProposal | None:
    with sqlite3.connect(database_path) as connection:
        proposal_rows = connection.execute(
            """
            SELECT id, payload_json
            FROM events
            WHERE kind = 'cognition.plan_proposal.completed' AND goal_id = ?
            ORDER BY occurred_at DESC, id DESC
            """,
            (goal_id,),
        ).fetchall()
        materialized_rows = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE kind = 'plan.proposal.materialized' AND goal_id = ?
            """,
            (goal_id,),
        ).fetchall()

    materialized_ids: set[str] = set()
    for (payload_json,) in materialized_rows:
        payload = json.loads(str(payload_json))
        if not isinstance(payload, dict):
            continue
        proposal_event_id = payload.get("proposal_event_id")
        if isinstance(proposal_event_id, str) and proposal_event_id:
            materialized_ids.add(proposal_event_id)

    for event_id, payload_json in proposal_rows:
        normalized_event_id = str(event_id)
        if normalized_event_id in materialized_ids:
            continue
        payload = json.loads(str(payload_json))
        if not isinstance(payload, dict):
            raise TypeError(f"proposta de Plan possui payload inválido: {normalized_event_id}")
        return PendingPlanProposal(
            event_id=normalized_event_id,
            source_goal_assessment_id=_optional_text(payload.get("source_goal_assessment_id")),
            source_completed_plan_id=_optional_text(payload.get("source_completed_plan_id")),
            source_active_plan_id=_optional_text(payload.get("source_active_plan_id")),
            source_active_plan_revision=_optional_int(payload.get("source_active_plan_revision")),
            source_failure_verification_id=_optional_text(
                payload.get("source_failure_verification_id")
            ),
        )
    return None


def ensure_plan_proposal_allowed(database_path: Path, *, goal_id: str) -> None:
    _proposal_state(database_path, goal_id=goal_id)


def propose_plan_for_goal(
    database_path: Path,
    provider: ModelProvider,
    *,
    model: str,
    goal_id: str,
) -> PlanProposalReceipt:
    goal, goal_assessment, plan_failure = _proposal_state(
        database_path,
        goal_id=goal_id,
    )

    desired_description = goal.desired_state.get("description")
    context_query = " ".join(
        part
        for part in (
            goal.title,
            desired_description if isinstance(desired_description, str) else "",
            *(
                str(criterion.get("description", ""))
                for criterion in goal.success_criteria
                if isinstance(criterion, dict)
            ),
        )
        if part.strip()
    )
    if not context_query:
        context_query = goal.title

    context = build_cognitive_context(database_path, text=context_query)
    intake_open_questions = get_goal_acceptance_open_questions(database_path, goal.id)
    open_questions = () if goal_assessment is not None else intake_open_questions
    trace_id = f"trc_{uuid4().hex}"

    append_event(
        database_path,
        Event.create(
            kind="cognition.context.built",
            source="cognition",
            payload={
                "purpose": "plan",
                "goal_ids": [item.id for item in context.goals],
                "entity_ids": [entity.id for entity in context.entities],
                "claim_ids": [claim.id for claim in context.claims],
                "memory_ids": [memory.id for memory in context.memories],
            },
            trace_id=trace_id,
            goal_id=goal.id,
        ),
    )

    try:
        result = propose_plan(
            provider,
            model=model,
            goal=goal,
            open_questions=open_questions,
            context=context,
            goal_assessment=goal_assessment,
            plan_failure=plan_failure,
        )
    except (ModelProviderError, TypeError, ValueError) as exc:
        append_event(
            database_path,
            Event.create(
                kind="cognition.plan_proposal.failed",
                source="cognition",
                payload={"model": model, "error": str(exc)},
                trace_id=trace_id,
                goal_id=goal.id,
            ),
        )
        raise

    proposal_event = Event.create(
        kind="cognition.plan_proposal.completed",
        source="cognition",
        payload={
            "model": result.model,
            "proposal": result.output.model_dump(mode="json"),
            "source_open_questions": list(open_questions),
            "source_goal_assessment_id": (
                goal_assessment.verification_id if goal_assessment is not None else None
            ),
            "source_completed_plan_id": (
                goal_assessment.plan_id if goal_assessment is not None else None
            ),
            "source_active_plan_id": (
                plan_failure.plan_id if plan_failure is not None else None
            ),
            "source_active_plan_revision": (
                plan_failure.plan_revision if plan_failure is not None else None
            ),
            "source_failure_step_id": (
                plan_failure.step_id if plan_failure is not None else None
            ),
            "source_failure_action_id": (
                plan_failure.action_id if plan_failure is not None else None
            ),
            "source_failure_verification_id": (
                plan_failure.verification_id if plan_failure is not None else None
            ),
            "source_failure_blocker_kind": (
                plan_failure.blocker_kind if plan_failure is not None else None
            ),
            "prompt_eval_count": result.prompt_eval_count,
            "eval_count": result.eval_count,
            "total_duration_ns": result.total_duration_ns,
            "repair_count": result.repair_count,
        },
        trace_id=trace_id,
        goal_id=goal.id,
    )
    append_event(database_path, proposal_event)

    return PlanProposalReceipt(
        goal=goal,
        context=context,
        result=result,
        proposal_event=proposal_event,
        goal_assessment=goal_assessment,
        plan_failure=plan_failure,
        open_questions=open_questions,
    )


def _proposal_state(
    database_path: Path,
    *,
    goal_id: str,
) -> tuple[Goal, GoalAssessmentContext | None, PlanFailureContext | None]:
    goal = get_goal(database_path, goal_id)
    if goal is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    if goal.status not in OPEN_STATUSES:
        raise ValueError(f"goal não está aberto: {goal.status}")

    plan_failure: PlanFailureContext | None = None
    active_plan = get_active_plan(database_path, goal.id)
    if active_plan is not None:
        plan_failure = get_active_plan_failure_context(database_path, goal_id=goal.id)
        if plan_failure is None:
            readiness = evaluate_active_plan(database_path, goal_id=goal.id)
            raise PlanProposalGateError(_active_plan_replanning_gate_message(readiness))

    goal_assessment = get_latest_goal_assessment_context(database_path, goal.id)
    if goal_assessment is not None and goal_assessment.verdict == "SATISFIED":
        raise PlanProposalGateError("assessment de Goal SATISFIED aguarda goal-complete")

    return goal, goal_assessment, plan_failure


def _active_plan_replanning_gate_message(readiness: PlanReadiness) -> str:
    if readiness.next_step is not None:
        return (
            f"Plan ACTIVE {readiness.plan.id} ainda possui step executável: "
            f"{readiness.next_step.step_id}"
        )

    pending = next((step for step in readiness.steps if step.state != "VERIFIED"), None)
    if pending is None:
        return f"Plan ACTIVE {readiness.plan.id} já está totalmente VERIFIED; use plan-complete"
    if pending.state == "IN_PROGRESS":
        return f"Plan ACTIVE {readiness.plan.id} possui step em andamento: {pending.step_id}"

    blockers = ", ".join(blocker.kind for blocker in pending.blockers) or "BLOCKED"
    return (
        f"Plan ACTIVE {readiness.plan.id} requer resolução local no step "
        f"{pending.step_id}: {blockers}"
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("campo opcional de proposta deveria ser texto")
    normalized = value.strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("campo opcional de proposta deveria ser inteiro")
    return value
