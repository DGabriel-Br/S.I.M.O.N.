from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from simon.events import Event, append_event, get_event
from simon.goals import OPEN_STATUSES, Goal, get_goal


@dataclass(frozen=True, slots=True)
class GoalFocus:
    event: Event
    goal: Goal


def select_goal_focus(
    database_path: Path,
    *,
    goal_id: str,
    trace_id: str,
    selection_text: str,
) -> GoalFocus:
    """Persiste a escolha foreground do usuário sem executar trabalho do Goal."""
    goal = get_goal(database_path, goal_id)
    if goal is None:
        raise ValueError(f"goal não encontrado: {goal_id}")
    if goal.status not in OPEN_STATUSES:
        raise ValueError(f"goal não está aberto para foco foreground: {goal_id} ({goal.status})")
    if not trace_id.strip():
        raise ValueError("seleção de Goal exige trace_id do turno humano")
    if not selection_text.strip():
        raise ValueError("seleção de Goal exige o texto original do turno")

    event = Event.create(
        kind="executive.goal_focus.selected",
        source="user",
        payload={
            "selected_goal_id": goal.id,
            "selected_goal_title": goal.title,
            "selected_goal_status": goal.status,
            "selection_text": selection_text.strip(),
        },
        trace_id=trace_id.strip(),
        goal_id=goal.id,
    )
    append_event(database_path, event)
    return GoalFocus(event=event, goal=goal)


def get_current_goal_focus(database_path: Path) -> GoalFocus | None:
    """Retorna a seleção foreground mais recente somente enquanto o Goal estiver aberto."""
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'executive.goal_focus.selected'
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    event = get_event(database_path, str(row[0]))
    if event is None or event.goal_id is None:
        return None

    goal = get_goal(database_path, event.goal_id)
    if goal is None or goal.status not in OPEN_STATUSES:
        return None
    return GoalFocus(event=event, goal=goal)
