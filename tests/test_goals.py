from pathlib import Path

import pytest

from simon.goals import Goal, get_goal, insert_goal, list_open_goals, transition_goal
from simon.storage import initialize_storage


def _goal() -> Goal:
    return Goal.create(
        title="Eliminar generation loop",
        origin="USER",
        desired_state={"issue": "generation_loop", "status": "resolved"},
        success_criteria=(
            {"kind": "test_passes", "test": "mask_generation"},
            {"kind": "no_regression"},
        ),
    )


def test_goal_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal()

    insert_goal(database_path, goal)
    restored = get_goal(database_path, goal.id)

    assert restored == goal


def test_open_goal_can_wait_and_resume(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal()
    insert_goal(database_path, goal)

    waiting = transition_goal(database_path, goal.id, "WAITING")
    resumed = transition_goal(database_path, goal.id, "ACTIVE")

    assert waiting.status == "WAITING"
    assert resumed.status == "ACTIVE"
    assert list_open_goals(database_path) == (resumed,)


def test_terminal_goal_cannot_be_reopened(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal()
    insert_goal(database_path, goal)

    completed = transition_goal(database_path, goal.id, "COMPLETED")

    assert completed.status == "COMPLETED"
    assert list_open_goals(database_path) == ()
    with pytest.raises(ValueError, match="transição de goal inválida"):
        transition_goal(database_path, goal.id, "ACTIVE")


def test_goal_requires_desired_state_and_success_criteria() -> None:
    with pytest.raises(ValueError, match="estado desejado"):
        Goal.create(
            title="Goal sem estado",
            origin="USER",
            desired_state={},
            success_criteria=({"kind": "test_passes"},),
        )

    with pytest.raises(ValueError, match="critérios de sucesso"):
        Goal.create(
            title="Goal sem critério",
            origin="USER",
            desired_state={"status": "resolved"},
            success_criteria=(),
        )
