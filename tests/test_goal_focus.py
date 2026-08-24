from pathlib import Path

from simon.goal_focus import get_current_goal_focus, select_goal_focus
from simon.goals import Goal, insert_goal, transition_goal
from simon.resume import reconstruct_resume_state
from simon.storage import initialize_storage


def _goal(database_path: Path, title: str) -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"description": f"{title} concluído."},
        success_criteria=({"description": "Existe evidência suficiente."},),
    )
    insert_goal(database_path, goal)
    return goal


def test_goal_focus_persists_user_selection_with_turn_provenance(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path, "Investigar falha")

    focus = select_goal_focus(
        database_path,
        goal_id=goal.id,
        trace_id="evt_turno",
        selection_text="Escolho esse Goal",
    )

    assert focus.goal.id == goal.id
    assert focus.event.kind == "executive.goal_focus.selected"
    assert focus.event.source == "user"
    assert focus.event.trace_id == "evt_turno"
    assert focus.event.goal_id == goal.id
    assert focus.event.payload["selection_text"] == "Escolho esse Goal"
    current = get_current_goal_focus(database_path)
    assert current is not None
    assert current.event.id == focus.event.id
    assert current.goal.id == goal.id


def test_goal_focus_expires_when_selected_goal_is_no_longer_open(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path, "Investigar falha")
    select_goal_focus(
        database_path,
        goal_id=goal.id,
        trace_id="evt_turno",
        selection_text="Investigar falha",
    )

    transition_goal(database_path, goal.id, "COMPLETED")

    assert get_current_goal_focus(database_path) is None


def test_resume_uses_persisted_focus_but_explicit_goal_still_wins(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = _goal(database_path, "Primeiro")
    second = _goal(database_path, "Segundo")
    select_goal_focus(
        database_path,
        goal_id=first.id,
        trace_id="evt_turno",
        selection_text="Primeiro",
    )

    focused = reconstruct_resume_state(database_path)
    explicit = reconstruct_resume_state(database_path, goal_id=second.id)

    assert focused.selected is not None
    assert focused.selected.goal.id == first.id
    assert explicit.selected is not None
    assert explicit.selected.goal.id == second.id
