from pathlib import Path

import pytest

from simon.actions import create_action, list_actions_for_plan, transition_action
from simon.events import Event, append_event
from simon.goals import Goal, insert_goal, transition_goal
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Investigar falha",
        origin="USER",
        desired_state={"description": "A causa da falha é conhecida."},
        success_criteria=({"description": "Existe evidência da causa."},),
    )
    insert_goal(database_path, goal)
    return goal


def test_readiness_requires_active_plan(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    with pytest.raises(ValueError, match="não possui plan ACTIVE"):
        evaluate_active_plan(database_path, goal_id=goal.id)


def test_first_ready_step_is_selected_deterministically(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Obter contexto",
                "capability": "user.input.request",
            },
            {
                "id": "step_02",
                "description": "Analisar contexto",
                "capability": "analysis.text",
            },
        ),
    )

    result = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"user.input.request", "analysis.text"}),
    )

    assert result.plan == plan
    assert result.next_step is not None
    assert result.next_step.step_id == "step_01"
    assert result.next_step.state == "READY"
    assert result.steps[1].state == "READY"


def test_dependency_only_unlocks_after_verified_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Coletar evidência",
                "capability": "evidence.collect",
            },
            {
                "id": "step_02",
                "description": "Analisar evidência",
                "depends_on": ["step_01"],
                "capability": "analysis.text",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="evidence.collect",
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"captured": True},
    )

    before_verification = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"evidence.collect", "analysis.text"}),
    )
    assert before_verification.next_step is None
    assert before_verification.steps[0].state == "BLOCKED"
    assert before_verification.steps[0].blockers[0].kind == "VERIFICATION_PENDING"
    assert any(
        blocker.kind == "DEPENDENCY_NOT_VERIFIED"
        for blocker in before_verification.steps[1].blockers
    )

    evidence = Event.create(
        kind="test.evidence.observed",
        source="test",
        payload={"captured": True},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "A evidência foi capturada."},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"captured": True},
        strength=2,
    )

    after_verification = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"evidence.collect", "analysis.text"}),
    )
    assert after_verification.steps[0].state == "VERIFIED"
    assert after_verification.next_step is not None
    assert after_verification.next_step.step_id == "step_02"


def test_unresolved_preconditions_block_actionability(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Ler arquivo",
                "capability": "filesystem.read",
                "preconditions": ["O caminho do arquivo foi confirmado."],
            },
        ),
    )

    result = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"filesystem.read"}),
    )

    assert result.next_step is None
    assert result.steps[0].state == "BLOCKED"
    assert result.steps[0].blockers[0].kind == "PRECONDITION_UNRESOLVED"


def test_unavailable_capability_blocks_step_without_creating_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Ler arquivo",
                "capability": "file.read",
            },
        ),
    )

    result = evaluate_active_plan(database_path, goal_id=goal.id)

    assert result.next_step is None
    assert result.steps[0].blockers[0].kind == "CAPABILITY_UNAVAILABLE"
    assert result.steps[0].blockers[0].detail == "file.read"

    assert list_actions_for_plan(database_path, plan.id) == ()


def test_existing_attempt_requires_review_instead_of_silent_retry(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar teste",
                "capability": "process.run",
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
        failure={"kind": "process_exit", "exit_code": 1},
    )

    result = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"process.run"}),
    )

    assert result.next_step is None
    assert result.steps[0].blockers[0].kind == "PREVIOUS_ATTEMPT_REQUIRES_REVIEW"
    assert action.id in result.steps[0].blockers[0].detail


def test_non_active_goal_blocks_execution_even_with_active_plan(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Obter contexto",
                "capability": "user.input.request",
            },
        ),
    )
    transition_goal(database_path, goal.id, "PAUSED")

    result = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"user.input.request"}),
    )

    assert result.next_step is None
    assert result.steps[0].blockers[0].kind == "GOAL_NOT_ACTIVE"


def test_user_ask_with_persisted_preconditions_remains_blocked(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário o script e a falha observada.",
                "capability": "user.ask",
                "preconditions": ["Um contexto anterior precisa estar disponível."],
            },
        ),
    )

    result = evaluate_active_plan(database_path, goal_id=goal.id)

    assert result.available_capabilities == (
        "cognition.analyze",
        "file.patch",
        "process.run",
        "user.ask",
    )
    assert result.next_step is None
    assert result.steps[0].state == "BLOCKED"
    assert result.steps[0].blockers[0].kind == "PRECONDITION_UNRESOLVED"


def test_user_ask_without_preconditions_is_ready_by_default(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário o script.",
                "capability": "user.ask",
                "preconditions": [],
            },
        ),
    )

    result = evaluate_active_plan(database_path, goal_id=goal.id)

    assert result.next_step is not None
    assert result.next_step.step_id == "step_01"
    assert result.next_step.state == "READY"


def test_latest_attempt_controls_step_even_when_older_attempt_was_verified(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar tentativa.",
                "capability": "process.run",
            },
        ),
    )
    first = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    transition_action(database_path, first.id, "RUNNING")
    transition_action(database_path, first.id, "COMPLETED", reported_result={"ok": True})
    evidence = Event.create(
        kind="test.first_attempt.verified",
        source="test",
        payload={"ok": True},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=first.id,
        criteria=({"description": "primeira tentativa observada"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"ok": True},
        strength=2,
    )

    second = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    transition_action(database_path, second.id, "RUNNING")
    transition_action(
        database_path,
        second.id,
        "FAILED",
        failure={"kind": "runtime_failure"},
    )

    result = evaluate_active_plan(
        database_path,
        goal_id=goal.id,
        available_capabilities=frozenset({"process.run"}),
    )

    assert result.steps[0].state == "BLOCKED"
    assert result.steps[0].related_action_id is None
    assert result.steps[0].blockers[0].kind == "PREVIOUS_ATTEMPT_REQUIRES_REVIEW"
    assert second.id in result.steps[0].blockers[0].detail
