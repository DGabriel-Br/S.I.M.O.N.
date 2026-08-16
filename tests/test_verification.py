from pathlib import Path

import pytest

from simon.actions import create_action, transition_action
from simon.events import Event, append_event
from simon.goals import Goal, get_goal, insert_goal
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.verification import (
    create_verification_result,
    get_verification_result,
    list_verification_results,
)


def _goal_plan_and_completed_action(database_path: Path) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Corrigir teste",
        origin="USER",
        desired_state={"test": "passing"},
        success_criteria=({"kind": "test_passes", "test": "test_target"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_1", "description": "Executar o teste"},),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="test.run",
    )
    transition_action(database_path, action.id, "RUNNING")
    completed = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"exit_code": 0},
    )
    return goal, completed.id


def _evidence_event(database_path: Path, goal_id: str, *, passed: bool) -> Event:
    event = Event.create(
        kind="test.observed",
        source="test_runner",
        payload={"target": "test_target", "passed": passed},
        goal_id=goal_id,
    )
    append_event(database_path, event)
    return event


def test_verification_result_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _goal_plan_and_completed_action(database_path)
    evidence = _evidence_event(database_path, goal.id, passed=True)

    result = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"kind": "test_passes", "test": "test_target"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"passed": True},
        strength=2,
    )

    assert get_verification_result(database_path, result.id) == result
    assert list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    ) == (result,)


def test_verification_requires_terminal_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Executar teste",
        origin="USER",
        desired_state={"test": "passing"},
        success_criteria=({"kind": "test_passes"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_1", "description": "Executar teste"},),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="test.run",
    )
    transition_action(database_path, action.id, "RUNNING")
    evidence = _evidence_event(database_path, goal.id, passed=True)

    with pytest.raises(ValueError, match="estado terminal"):
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=({"kind": "test_passes"},),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"passed": True},
            strength=2,
        )


def test_verification_rejects_missing_evidence_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _goal_plan_and_completed_action(database_path)

    with pytest.raises(ValueError, match="Event de evidência não encontrado"):
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action_id,
            criteria=({"kind": "test_passes"},),
            status="VERIFIED",
            evidence_event_ids=("evt_missing",),
            observed={"passed": True},
            strength=2,
        )


def test_new_evidence_creates_new_result_without_rewriting_history(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _goal_plan_and_completed_action(database_path)
    first_evidence = _evidence_event(database_path, goal.id, passed=False)

    inconclusive = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"kind": "test_passes"},),
        status="INCONCLUSIVE",
        evidence_event_ids=(first_evidence.id,),
        observed={"runner_output": "incomplete"},
        strength=1,
    )

    second_evidence = _evidence_event(database_path, goal.id, passed=True)
    verified = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"kind": "test_passes"},),
        status="VERIFIED",
        evidence_event_ids=(second_evidence.id,),
        observed={"passed": True},
        strength=2,
    )

    assert list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    ) == (inconclusive, verified)


def test_goal_can_be_verified_without_automatic_state_transition(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Confirmar estado final",
        origin="USER",
        desired_state={"service": "healthy"},
        success_criteria=({"kind": "health_check"},),
    )
    insert_goal(database_path, goal)
    evidence = Event.create(
        kind="service.health_observed",
        source="health_check",
        payload={"healthy": True},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)

    result = create_verification_result(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
        criteria=goal.success_criteria,
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"healthy": True},
        strength=2,
    )

    stored_goal = get_goal(database_path, goal.id)
    assert result.subject_type == "GOAL"
    assert stored_goal is not None
    assert stored_goal.status == "ACTIVE"


def test_verification_validates_status_strength_and_criteria(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _goal_plan_and_completed_action(database_path)
    evidence = _evidence_event(database_path, goal.id, passed=True)

    with pytest.raises(ValueError, match="precisa de critérios"):
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action_id,
            criteria=(),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"passed": True},
            strength=2,
        )

    with pytest.raises(ValueError, match="status de verification inválido"):
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action_id,
            criteria=({"kind": "test_passes"},),
            status="UNKNOWN",
            evidence_event_ids=(evidence.id,),
            observed={"passed": True},
            strength=2,
        )

    with pytest.raises(ValueError, match="strength precisa estar entre"):
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action_id,
            criteria=({"kind": "test_passes"},),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"passed": True},
            strength=6,
        )


def test_verification_rejects_waiting_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Aguardar resposta",
        origin="USER",
        desired_state={"response": "received"},
        success_criteria=({"kind": "response_received"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_1", "description": "Perguntar ao usuário"},),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="user.ask",
    )
    transition_action(database_path, action.id, "WAITING")
    evidence = Event.create(kind="user.question.asked", source="system")
    append_event(database_path, evidence)

    with pytest.raises(ValueError, match="estado terminal"):
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=({"kind": "response_received"},),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"response": "pending"},
            strength=1,
        )
