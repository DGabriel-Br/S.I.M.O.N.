from pathlib import Path

from simon.actions import create_action, transition_action
from simon.events import Event, append_event
from simon.goals import Goal, insert_goal
from simon.plan_failure import get_active_plan_failure_context
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Corrigir falha",
        origin="USER",
        desired_state={"description": "A falha deixa de ocorrer."},
        success_criteria=({"description": "A falha não é reproduzida."},),
    )
    insert_goal(database_path, goal)
    return goal


def _completed_analysis(database_path: Path) -> tuple[Goal, object, object, Event]:
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar a saída observada.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A análise identifica uma causa sustentada pela evidência.",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
        input_data={"verification": "A análise identifica uma causa sustentada pela evidência."},
    )
    transition_action(database_path, action.id, "RUNNING")
    completed = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"analysis_event_id": "evt_analysis"},
    )
    evidence = Event.create(
        kind="cognition.analysis.completed",
        source="cognition",
        payload={"action_id": completed.id, "summary": "A evidência não sustenta a hipótese."},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    return goal, plan, completed, evidence


def test_failure_context_exposes_negative_assessment_as_replanning_evidence(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan, action, evidence = _completed_analysis(database_path)
    verification = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A análise sustenta o critério."},),
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={
            "assessment_type": "cognition.analyze.semantic",
            "verdict": "NOT_SATISFIED",
            "rationale": "A hipótese atual não explica a saída observada.",
        },
        strength=2,
    )

    context = get_active_plan_failure_context(database_path, goal_id=goal.id)

    assert context is not None
    assert context.plan_id == plan.id
    assert context.plan_revision == plan.revision
    assert context.step_id == "step_01"
    assert context.action_id == action.id
    assert context.verification_id == verification.id
    assert context.blocker_kind == "CRITERION_NOT_SATISFIED"
    assert context.evidence_events == (evidence,)
    payload = context.to_model_payload()
    assert payload["verification"]["status"] == "ASSESSED"  # type: ignore[index]


def test_failure_context_ignores_assessment_waiting_for_confirmation(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _, action, evidence = _completed_analysis(database_path)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A análise sustenta o critério."},),
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={
            "assessment_type": "cognition.analyze.semantic",
            "verdict": "SATISFIED",
        },
        strength=2,
    )

    assert get_active_plan_failure_context(database_path, goal_id=goal.id) is None


def test_failure_context_does_not_turn_operational_failure_into_automatic_replan(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script.",
                "kind": "WORLD",
                "capability": "process.run",
                "verification": "Existe uma execução observável.",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(
        database_path,
        action.id,
        "FAILED",
        failure={"kind": "spawn_error", "message": "executável ausente"},
    )

    assert get_active_plan_failure_context(database_path, goal_id=goal.id) is None


def test_failure_context_preserves_user_ask_local_retry_path(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Perguntar ao usuário pelo dado ausente.",
                "kind": "EPISTEMIC",
                "capability": "user.ask",
                "verification": "O dado fornecido satisfaz a necessidade do step.",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="user.ask",
    )
    transition_action(database_path, action.id, "WAITING")
    action = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"response_event_id": "evt_response"},
    )
    evidence = Event.create(
        kind="user.response.received",
        source="user",
        payload={"action_id": action.id, "response": "não sei"},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "O dado fornecido satisfaz a necessidade do step."},),
        status="ASSESSED",
        evidence_event_ids=(evidence.id,),
        observed={"assessment_type": "user.ask.semantic", "verdict": "NOT_SATISFIED"},
        strength=2,
    )

    assert get_active_plan_failure_context(database_path, goal_id=goal.id) is None
