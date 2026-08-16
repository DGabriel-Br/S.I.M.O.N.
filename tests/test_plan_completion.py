from pathlib import Path

import pytest

from simon.actions import create_action, transition_action
from simon.events import Event, append_event, get_event
from simon.goals import Goal, get_goal, insert_goal
from simon.plan_completion import complete_verified_plan
from simon.plans import create_plan, get_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Concluir estratégia",
        origin="USER",
        desired_state={"description": "A estratégia foi executada."},
        success_criteria=({"description": "Os resultados foram observados."},),
    )
    insert_goal(database_path, goal)
    return goal


def _verified_plan(database_path: Path, goal: Goal, *, steps: int = 2) -> tuple[str, ...]:
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=tuple(
            {
                "id": f"step_{index:02d}",
                "description": f"Executar passo {index}",
                "capability": "test.capability",
            }
            for index in range(1, steps + 1)
        ),
    )
    action_ids: list[str] = []
    for index in range(1, steps + 1):
        action = create_action(
            database_path,
            goal_id=goal.id,
            plan_id=plan.id,
            step_id=f"step_{index:02d}",
            kind="test.capability",
        )
        transition_action(database_path, action.id, "RUNNING")
        transition_action(database_path, action.id, "COMPLETED", reported_result={"ok": True})
        evidence = Event.create(
            kind="test.step.observed",
            source="test",
            payload={"step_id": f"step_{index:02d}"},
            goal_id=goal.id,
        )
        append_event(database_path, evidence)
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=({"description": "O passo terminou corretamente."},),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"ok": True},
            strength=2,
        )
        action_ids.append(action.id)
    return tuple(action_ids)


def test_plan_completion_requires_every_step_verified(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {"id": "step_01", "description": "Primeiro", "capability": "test.capability"},
            {"id": "step_02", "description": "Segundo", "capability": "test.capability"},
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="test.capability",
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(database_path, action.id, "COMPLETED", reported_result={"ok": True})
    evidence = Event.create(kind="test.observed", source="test", goal_id=goal.id)
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "Primeiro verificado"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"ok": True},
        strength=2,
    )

    with pytest.raises(ValueError, match=r"step_02=BLOCKED"):
        complete_verified_plan(database_path, goal_id=goal.id)

    persisted = get_plan(database_path, plan.id)
    assert persisted is not None
    assert persisted.status == "ACTIVE"


def test_plan_completion_marks_plan_completed_without_completing_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    action_ids = _verified_plan(database_path, goal)

    receipt = complete_verified_plan(database_path, goal_id=goal.id, trace_id="trc_test")

    assert receipt.created is True
    assert receipt.plan.status == "COMPLETED"
    assert receipt.verified_step_ids == ("step_01", "step_02")
    persisted_goal = get_goal(database_path, goal.id)
    assert persisted_goal is not None
    assert persisted_goal.status == "ACTIVE"

    event = get_event(database_path, receipt.completion_event_id)
    assert event is not None
    assert event.kind == "plan.completed"
    assert event.trace_id == "trc_test"
    assert event.payload["verified_action_ids"] == list(action_ids)
    assert event.payload["goal_status_after_completion"] == "ACTIVE"


def test_plan_completion_is_idempotent(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    _verified_plan(database_path, goal, steps=1)

    first = complete_verified_plan(database_path, goal_id=goal.id)
    second = complete_verified_plan(database_path, goal_id=goal.id)

    assert first.created is True
    assert second.created is False
    assert second.plan.id == first.plan.id
    assert second.completion_event_id == first.completion_event_id


def test_plan_completion_rolls_back_status_if_event_insert_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    _verified_plan(database_path, goal, steps=1)

    def fail_event(*args: object, **kwargs: object) -> None:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("simon.plan_completion._insert_event", fail_event)

    with pytest.raises(RuntimeError, match="falha simulada"):
        complete_verified_plan(database_path, goal_id=goal.id)

    from simon.plans import get_active_plan

    active = get_active_plan(database_path, goal.id)
    assert active is not None
    assert active.status == "ACTIVE"
