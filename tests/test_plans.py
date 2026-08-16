from pathlib import Path

import pytest

from simon.goals import Goal, insert_goal, transition_goal
from simon.plans import (
    create_plan,
    get_active_plan,
    get_plan,
    list_plans_for_goal,
    transition_plan,
)
from simon.storage import initialize_storage


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Eliminar generation loop",
        origin="USER",
        desired_state={"issue": "generation_loop", "status": "resolved"},
        success_criteria=({"kind": "test_passes", "test": "mask_generation"},),
    )
    insert_goal(database_path, goal)
    return goal


def _steps(description: str = "Reproduzir o problema") -> tuple[dict[str, object], ...]:
    return (
        {"id": "step_1", "description": description},
        {
            "id": "step_2",
            "description": "Analisar o resultado",
            "depends_on": ["step_1"],
        },
    )


def test_plan_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    plan = create_plan(database_path, goal_id=goal.id, steps=_steps())
    restored = get_plan(database_path, plan.id)

    assert restored == plan
    assert restored is not None
    assert restored.revision == 1
    assert get_active_plan(database_path, goal.id) == plan


def test_new_plan_supersedes_previous_revision(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    first = create_plan(database_path, goal_id=goal.id, steps=_steps())
    second = create_plan(
        database_path,
        goal_id=goal.id,
        steps=_steps("Reproduzir com logging detalhado"),
    )

    stored_first = get_plan(database_path, first.id)
    assert stored_first is not None
    assert stored_first.status == "SUPERSEDED"
    assert second.revision == 2
    assert get_active_plan(database_path, goal.id) == second
    assert list_plans_for_goal(database_path, goal.id) == (stored_first, second)


def test_failed_plan_does_not_fail_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(database_path, goal_id=goal.id, steps=_steps())

    failed_plan = transition_plan(database_path, plan.id, "FAILED")

    assert failed_plan.status == "FAILED"
    assert get_active_plan(database_path, goal.id) is None
    assert transition_goal(database_path, goal.id, "PAUSED").status == "PAUSED"


def test_plan_cannot_be_created_for_terminal_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    transition_goal(database_path, goal.id, "CANCELLED")

    with pytest.raises(ValueError, match="goal terminal"):
        create_plan(database_path, goal_id=goal.id, steps=_steps())


def test_plan_rejects_invalid_step_dependencies(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    with pytest.raises(ValueError, match="ainda não definido"):
        create_plan(
            database_path,
            goal_id=goal.id,
            steps=(
                {
                    "id": "step_1",
                    "description": "Usar resultado futuro",
                    "depends_on": ["step_2"],
                },
                {"id": "step_2", "description": "Produzir o resultado"},
            ),
        )


def test_plan_rejects_invalid_dependency_type(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    with pytest.raises(TypeError, match="depends_on inválido"):
        create_plan(
            database_path,
            goal_id=goal.id,
            steps=(
                {
                    "id": "step_1",
                    "description": "Passo com dependência inválida",
                    "depends_on": "step_0",
                },
            ),
        )
