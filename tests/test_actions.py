from pathlib import Path

import pytest

from simon.actions import (
    create_action,
    get_action,
    interrupt_running_actions,
    list_actions_for_plan,
    transition_action,
)
from simon.goals import Goal, get_goal, insert_goal
from simon.plans import create_plan, get_plan
from simon.storage import initialize_storage


def _goal_and_plan(database_path: Path) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Investigar teste com falha",
        origin="USER",
        desired_state={"test": "passing"},
        success_criteria=({"kind": "test_passes", "test": "test_target"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {"id": "step_1", "description": "Executar o teste"},
            {
                "id": "step_2",
                "description": "Analisar a saída",
                "depends_on": ["step_1"],
            },
        ),
    )
    return goal, plan.id


def test_action_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _goal_and_plan(database_path)

    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_1",
        kind="test.run",
        input_data={"target": "test_target"},
    )

    assert action.status == "PENDING"
    assert get_action(database_path, action.id) == action
    assert list_actions_for_plan(database_path, plan_id) == (action,)


def test_action_lifecycle_keeps_execution_result_separate_from_goal_and_plan(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _goal_and_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_1",
        kind="test.run",
    )

    running = transition_action(database_path, action.id, "RUNNING")
    completed = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"exit_code": 0},
    )

    assert running.started_at is not None
    assert running.finished_at is None
    assert completed.status == "COMPLETED"
    assert completed.reported_result == {"exit_code": 0}
    assert completed.finished_at is not None

    stored_goal = get_goal(database_path, goal.id)
    stored_plan = get_plan(database_path, plan_id)
    assert stored_goal is not None
    assert stored_goal.status == "ACTIVE"
    assert stored_plan is not None
    assert stored_plan.status == "ACTIVE"


def test_action_persists_structured_failure(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _goal_and_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_1",
        kind="test.run",
    )
    transition_action(database_path, action.id, "RUNNING")

    failed = transition_action(
        database_path,
        action.id,
        "FAILED",
        failure={"kind": "process_exit", "exit_code": 1},
    )

    assert failed.status == "FAILED"
    assert failed.failure == {"kind": "process_exit", "exit_code": 1}
    assert failed.finished_at is not None


def test_action_rejects_plan_or_step_outside_target(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _goal_and_plan(database_path)

    with pytest.raises(ValueError, match="passo não encontrado"):
        create_action(
            database_path,
            goal_id=goal.id,
            plan_id=plan_id,
            step_id="step_missing",
            kind="test.run",
        )

    other_goal, other_plan_id = _goal_and_plan(database_path)
    with pytest.raises(ValueError, match="não pertence"):
        create_action(
            database_path,
            goal_id=goal.id,
            plan_id=other_plan_id,
            step_id="step_1",
            kind="test.run",
        )

    assert other_goal.id != goal.id


def test_running_actions_are_interrupted_after_runtime_loss(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _goal_and_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_1",
        kind="test.run",
    )
    transition_action(database_path, action.id, "RUNNING")

    interrupted = interrupt_running_actions(database_path)

    assert len(interrupted) == 1
    assert interrupted[0].id == action.id
    assert interrupted[0].status == "INTERRUPTED"
    assert interrupted[0].failure is not None
    assert interrupted[0].failure["kind"] == "runtime_restart"


def test_terminal_action_cannot_be_reopened(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _goal_and_plan(database_path)
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id="step_1",
        kind="test.run",
    )
    transition_action(database_path, action.id, "DENIED")

    with pytest.raises(ValueError, match="transição de action inválida"):
        transition_action(database_path, action.id, "RUNNING")
