import json
import sqlite3
from pathlib import Path

import pytest

from simon.actions import Action, create_action, transition_action
from simon.events import Event, append_event
from simon.goals import Goal, insert_goal, transition_goal
from simon.plan_intake import materialize_plan_proposal
from simon.planning import PlanProposal, PlanStepProposal
from simon.plans import Plan, create_plan, get_active_plan, get_plan, list_plans_for_goal
from simon.storage import initialize_storage
from simon.verification import VerificationResult, create_verification_result


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Corrigir falha no script",
        origin="USER",
        desired_state={"description": "O script executa sem a falha relatada."},
        success_criteria=({"description": "A falha original não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    return goal


def _proposal_event(
    database_path: Path,
    goal: Goal,
    *,
    summary: str = "Obter evidência antes da correção.",
) -> Event:
    proposal = PlanProposal(
        summary=summary,
        steps=[
            PlanStepProposal(
                id="step_01",
                description="Obter o script e a falha observada do usuário.",
                kind="EPISTEMIC",
                preconditions=[],
                capability="user.ask",
                verification="Script e falha foram fornecidos e registrados.",
            ),
            PlanStepProposal(
                id="step_02",
                description="Analisar o material fornecido.",
                kind="EPISTEMIC",
                depends_on=["step_01"],
                capability="cognition.analyze",
                verification="Hipótese causal foi registrada com base na evidência.",
            ),
        ],
        open_questions=["Qual script está falhando?"],
    )
    event = Event.create(
        kind="cognition.plan_proposal.completed",
        source="cognition",
        payload={
            "model": "fake-model",
            "proposal": proposal.model_dump(mode="json"),
            "source_open_questions": ["Qual script está falhando?"],
        },
        trace_id="trc_plan_source",
        goal_id=goal.id,
    )
    append_event(database_path, event)
    return event


def test_materialization_persists_exact_plan_and_provenance(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    proposal_event = _proposal_event(database_path, goal)

    result = materialize_plan_proposal(
        database_path,
        proposal_event.id,
        trace_id="trc_materialize",
    )

    assert result.created is True
    assert result.plan.goal_id == goal.id
    assert result.plan.revision == 1
    assert result.plan.status == "ACTIVE"
    assert result.plan.steps[0]["kind"] == "EPISTEMIC"
    assert result.plan.steps[0]["capability"] == "user.ask"
    assert result.plan.steps[1]["depends_on"] == ["step_01"]
    assert get_active_plan(database_path, goal.id) == result.plan

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT source, payload_json, trace_id, goal_id
            FROM events
            WHERE kind = 'plan.proposal.materialized'
            """
        ).fetchone()

    assert row is not None
    payload = json.loads(str(row[1]))
    assert row[0] == "system"
    assert row[2] == "trc_materialize"
    assert row[3] == goal.id
    assert payload["proposal_event_id"] == proposal_event.id
    assert payload["proposal_trace_id"] == "trc_plan_source"
    assert payload["proposal_model"] == "fake-model"
    assert payload["plan_id"] == result.plan.id
    assert payload["plan_revision"] == 1
    assert payload["open_questions"] == ["Qual script está falhando?"]


def test_materialization_is_idempotent_per_proposal_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    proposal_event = _proposal_event(database_path, goal)

    first = materialize_plan_proposal(database_path, proposal_event.id)
    second = materialize_plan_proposal(database_path, proposal_event.id)

    assert first.created is True
    assert second.created is False
    assert second.plan == first.plan

    with sqlite3.connect(database_path) as connection:
        plan_count = connection.execute("SELECT COUNT(*) FROM plans").fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'plan.proposal.materialized'"
        ).fetchone()

    assert plan_count == (1,)
    assert event_count == (1,)


def test_new_materialized_proposal_supersedes_previous_plan_revision(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    first_event = _proposal_event(database_path, goal)
    first = materialize_plan_proposal(database_path, first_event.id).plan

    second_event = _proposal_event(
        database_path,
        goal,
        summary="Coletar evidência por outra estratégia.",
    )
    second = materialize_plan_proposal(database_path, second_event.id).plan

    restored_first = get_plan(database_path, first.id)
    assert restored_first is not None
    assert restored_first.status == "SUPERSEDED"
    assert second.revision == 2
    assert get_active_plan(database_path, goal.id) == second
    assert list_plans_for_goal(database_path, goal.id) == (restored_first, second)


def test_materialization_rejects_terminal_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    proposal_event = _proposal_event(database_path, goal)
    transition_goal(database_path, goal.id, "CANCELLED")

    with pytest.raises(ValueError, match="goal terminal"):
        materialize_plan_proposal(database_path, proposal_event.id)


def _failure_driven_proposal_event(
    database_path: Path,
    goal: Goal,
    *,
    plan_id: str,
    plan_revision: int,
    step_id: str,
    action_id: str,
    verification_id: str,
) -> Event:
    proposal = PlanProposal(
        summary="Substituir a estratégia que falhou.",
        steps=[
            PlanStepProposal(
                id="step_01",
                description="Executar uma estratégia alternativa.",
                kind="WORLD",
                capability="process.run",
                verification="Existe nova evidência observável da estratégia alternativa.",
            )
        ],
    )
    event = Event.create(
        kind="cognition.plan_proposal.completed",
        source="cognition",
        payload={
            "model": "fake-model",
            "proposal": proposal.model_dump(mode="json"),
            "source_active_plan_id": plan_id,
            "source_active_plan_revision": plan_revision,
            "source_failure_step_id": step_id,
            "source_failure_action_id": action_id,
            "source_failure_verification_id": verification_id,
            "source_failure_blocker_kind": "CRITERION_NOT_SATISFIED",
        },
        goal_id=goal.id,
    )
    append_event(database_path, event)
    return event


def _active_plan_with_negative_verification(
    database_path: Path,
    goal: Goal,
) -> tuple[Plan, Action, VerificationResult]:
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar a estratégia atual.",
                "kind": "EPISTEMIC",
                "capability": "cognition.analyze",
                "verification": "A análise sustenta a estratégia.",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
    )
    transition_action(database_path, action.id, "RUNNING")
    action = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"analysis_event_id": "evt_analysis"},
    )
    evidence = Event.create(
        kind="cognition.analysis.completed",
        source="cognition",
        payload={"action_id": action.id},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    verification = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A análise sustenta a estratégia."},),
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={"verdict": "NOT_SATISFIED"},
        strength=2,
    )
    return plan, action, verification


def test_failure_driven_materialization_revalidates_source_before_superseding(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan, action, verification = _active_plan_with_negative_verification(database_path, goal)
    proposal_event = _failure_driven_proposal_event(
        database_path,
        goal,
        plan_id=plan.id,
        plan_revision=plan.revision,
        step_id="step_01",
        action_id=action.id,
        verification_id=verification.id,
    )

    materialized = materialize_plan_proposal(database_path, proposal_event.id)

    assert materialized.created is True
    assert materialized.plan.revision == 2
    previous = get_plan(database_path, plan.id)
    assert previous is not None
    assert previous.status == "SUPERSEDED"


def test_failure_driven_materialization_rejects_stale_verification(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan, action, verification = _active_plan_with_negative_verification(database_path, goal)
    proposal_event = _failure_driven_proposal_event(
        database_path,
        goal,
        plan_id=plan.id,
        plan_revision=plan.revision,
        step_id="step_01",
        action_id=action.id,
        verification_id=verification.id,
    )
    newer_evidence = Event.create(
        kind="verification.review.updated",
        source="user",
        payload={"action_id": action.id},
        goal_id=goal.id,
    )
    append_event(database_path, newer_evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A análise sustenta a estratégia."},),
        status="ASSESSED",
        evidence_event_ids=(newer_evidence.id,),
        observed={"verdict": "UNCLEAR"},
        strength=2,
    )

    with pytest.raises(ValueError, match="obsoleta por nova Verification"):
        materialize_plan_proposal(database_path, proposal_event.id)

    current = get_active_plan(database_path, goal.id)
    assert current is not None
    assert current.id == plan.id
