from pathlib import Path

import pytest

from simon.actions import create_action, transition_action
from simon.events import Event, append_event
from simon.experiences import (
    add_action_to_experience,
    add_event_to_experience,
    add_verification_to_experience,
    close_experience,
    create_experience,
    get_experience,
    list_open_experiences,
    resume_experience,
    suspend_active_experiences,
    suspend_experience,
)
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


def _goal(database_path: Path, title: str = "Investigar falha") -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"test": "passing"},
        success_criteria=({"kind": "test_passes"},),
    )
    insert_goal(database_path, goal)
    return goal


def _completed_action(database_path: Path, goal: Goal) -> str:
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
    return completed.id


def test_experience_connects_goal_events_actions_and_verification(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    experience = create_experience(
        database_path,
        title="Testar hipótese do erro",
        goal_id=goal.id,
    )

    event = Event.create(
        kind="test.observed",
        source="test_runner",
        payload={"passed": True},
        goal_id=goal.id,
        experience_id=experience.id,
    )
    append_event(database_path, event)
    action_id = _completed_action(database_path, goal)
    verification = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"kind": "test_passes"},),
        status="VERIFIED",
        evidence_event_ids=(event.id,),
        observed={"passed": True},
        strength=2,
    )

    add_event_to_experience(database_path, experience.id, event.id)
    add_action_to_experience(database_path, experience.id, action_id)
    linked = add_verification_to_experience(database_path, experience.id, verification.id)

    assert linked.event_ids == (event.id,)
    assert linked.action_ids == (action_id,)
    assert linked.verification_ids == (verification.id,)
    assert get_experience(database_path, experience.id) == linked


def test_experience_lifecycle_separates_session_state_from_outcome(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    experience = create_experience(
        database_path,
        title="Investigar hipótese",
        goal_id=goal.id,
    )

    suspended = suspend_experience(database_path, experience.id)
    resumed = resume_experience(database_path, experience.id)
    closed = close_experience(
        database_path,
        experience.id,
        outcome="FAILURE",
        summary="A hipótese testada não explicou a falha.",
    )

    assert suspended.status == "SUSPENDED"
    assert resumed.status == "ACTIVE"
    assert closed.status == "CLOSED"
    assert closed.outcome == "FAILURE"
    assert closed.ended_at is not None
    assert closed.summary == "A hipótese testada não explicou a falha."

    with pytest.raises(ValueError, match="não está suspensa"):
        resume_experience(database_path, experience.id)


def test_experience_can_be_nested_and_survives_new_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    parent = create_experience(
        database_path,
        title="Investigar falha",
        goal_id=goal.id,
    )
    child = create_experience(
        database_path,
        title="Testar hipótese A",
        goal_id=goal.id,
        parent_experience_id=parent.id,
    )

    stored = get_experience(database_path, child.id)

    assert stored == child
    assert stored is not None
    assert stored.parent_experience_id == parent.id
    assert list_open_experiences(database_path) == (parent, child)


def test_experience_rejects_reference_from_another_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first_goal = _goal(database_path, "Primeiro goal")
    second_goal = _goal(database_path, "Segundo goal")
    experience = create_experience(
        database_path,
        title="Experiência do primeiro goal",
        goal_id=first_goal.id,
    )
    action_id = _completed_action(database_path, second_goal)

    with pytest.raises(ValueError, match="não pertence ao goal"):
        add_action_to_experience(database_path, experience.id, action_id)


def test_closed_experience_accepts_late_evidence_but_not_new_actions(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    experience = create_experience(
        database_path,
        title="Experiência curta",
        goal_id=goal.id,
    )
    close_experience(database_path, experience.id, outcome="INCONCLUSIVE")

    late_event = Event.create(
        kind="late.observation",
        source="test",
        goal_id=goal.id,
        experience_id=experience.id,
    )
    append_event(database_path, late_event)
    with_late_event = add_event_to_experience(database_path, experience.id, late_event.id)

    action_id = _completed_action(database_path, goal)
    verification = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"kind": "test_passes"},),
        status="VERIFIED",
        evidence_event_ids=(late_event.id,),
        observed={"passed": True},
        strength=2,
    )
    with_late_verification = add_verification_to_experience(
        database_path, experience.id, verification.id
    )

    assert with_late_event.status == "CLOSED"
    assert with_late_verification.verification_ids == (verification.id,)

    with pytest.raises(ValueError, match="não aceita novas actions"):
        add_action_to_experience(database_path, experience.id, action_id)


def test_event_explicitly_linked_to_another_experience_is_rejected(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    first = create_experience(database_path, title="Primeira", goal_id=goal.id)
    second = create_experience(database_path, title="Segunda", goal_id=goal.id)
    event = Event.create(
        kind="observation",
        source="test",
        goal_id=goal.id,
        experience_id=first.id,
    )
    append_event(database_path, event)

    with pytest.raises(ValueError, match="outra experience"):
        add_event_to_experience(database_path, second.id, event.id)


def test_runtime_loss_suspends_only_active_experiences(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    active = create_experience(database_path, title="Ativa")
    suspended = create_experience(database_path, title="Já suspensa")
    suspend_experience(database_path, suspended.id)

    recovered = suspend_active_experiences(database_path)

    assert tuple(item.id for item in recovered) == (active.id,)
    stored_active = get_experience(database_path, active.id)
    stored_suspended = get_experience(database_path, suspended.id)
    assert stored_active is not None and stored_active.status == "SUSPENDED"
    assert stored_suspended is not None and stored_suspended.status == "SUSPENDED"
