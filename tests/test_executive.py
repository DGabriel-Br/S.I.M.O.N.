from __future__ import annotations

import sqlite3
from pathlib import Path

from simon.actions import create_action, transition_action
from simon.attention import AttentionSignals, assess_observation_attention, open_attention_item
from simon.cli import main
from simon.events import Event, append_event
from simon.executive import decide_next
from simon.goals import Goal, insert_goal, transition_goal
from simon.perception import record_observation
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.user_ask import dispatch_next_user_ask
from simon.verification import create_verification_result


def _goal(database_path: Path, title: str = "Corrigir script") -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"script": "working"},
        success_criteria=({"kind": "script_runs"},),
    )
    insert_goal(database_path, goal)
    return goal


def _plan(database_path: Path, goal: Goal, *, capability: str) -> object:
    return create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": f"Executar step com {capability}",
                "kind": "EPISTEMIC" if capability != "process.run" else "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": capability,
                "verification": "evidência observável",
                "intent_role": "ANALYZE" if capability == "cognition.analyze" else "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
    )


def _evidence(database_path: Path, goal_id: str, kind: str = "test.evidence") -> Event:
    event = Event.create(
        kind=kind,
        source="tool",
        payload={"ok": True},
        goal_id=goal_id,
    )
    append_event(database_path, event)
    return event


def _verified_action(
    database_path: Path,
    *,
    goal: Goal,
    plan_id: str,
    step_id: str,
    kind: str,
) -> str:
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan_id,
        step_id=step_id,
        kind=kind,
    )
    completed = transition_action(
        database_path,
        action.id,
        "RUNNING",
    )
    completed = transition_action(
        database_path,
        completed.id,
        "COMPLETED",
        reported_result={"ok": True},
    )
    event = _evidence(database_path, goal.id)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=completed.id,
        criteria=({"kind": "done"},),
        status="VERIFIED",
        evidence_event_ids=(event.id,),
        observed={"ok": True},
        strength=3,
    )
    return completed.id


def test_executive_requires_goal_selection_when_multiple_goals_are_open(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = _goal(database_path, "Primeiro")
    second = _goal(database_path, "Segundo")

    decision = decide_next(database_path)

    assert decision.outcome == "NEEDS_GOAL_SELECTION"
    assert decision.operation is None
    assert {candidate.goal_id for candidate in decision.goal_candidates} == {
        first.id,
        second.id,
    }


def test_executive_requires_authorization_for_ready_process_run(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = _plan(database_path, goal, capability="process.run")

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert decision.operation == "plan.run"
    assert decision.goal_id == goal.id
    assert decision.plan_id == plan.id
    assert decision.step_id == "step_01"
    assert decision.capability == "process.run"
    assert decision.action_id is None


def test_executive_proceeds_with_ready_cognition_without_choosing_model(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    _plan(database_path, goal, capability="cognition.analyze")

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "PROCEED"
    assert decision.operation == "plan.analyze"
    assert decision.requires_model is True
    assert decision.capability == "cognition.analyze"


def test_executive_waits_for_real_user_response_to_user_ask(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Obter do usuário a mensagem de erro",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "usuário forneceu a mensagem",
                "intent_role": "COLLECT",
                "intent_actor": "USER",
            },
        ),
    )
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "NEEDS_USER_INPUT"
    assert decision.operation == "action.answer"
    assert decision.action_id == dispatch.action.id
    assert decision.step_id == "step_01"


def test_executive_selects_objective_verification_after_completed_process(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = _plan(database_path, goal, capability="process.run")
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    running = transition_action(database_path, action.id, "RUNNING")
    completed = transition_action(
        database_path,
        running.id,
        "COMPLETED",
        reported_result={"exit_code": 0},
    )

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "PROCEED"
    assert decision.operation == "process.verify"
    assert decision.action_id == completed.id
    assert decision.reason_code == "verification_pending"


def test_executive_requires_confirmation_for_satisfied_action_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = _plan(database_path, goal, capability="cognition.analyze")
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
    )
    running = transition_action(database_path, action.id, "RUNNING")
    completed = transition_action(
        database_path,
        running.id,
        "COMPLETED",
        reported_result={"analysis": "ok"},
    )
    event = _evidence(database_path, goal.id)
    assessment = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=completed.id,
        criteria=({"kind": "analysis"},),
        status="ASSESSED",
        evidence_event_ids=(event.id,),
        observed={"verdict": "SATISFIED"},
        strength=2,
    )

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "NEEDS_USER_CONFIRMATION"
    assert decision.operation == "verification.confirm"
    assert decision.action_id == completed.id
    assert decision.verification_id == assessment.id


def test_executive_requires_retry_authorization_after_failed_process(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = _plan(database_path, goal, capability="process.run")
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )
    running = transition_action(database_path, action.id, "RUNNING")
    failed = transition_action(
        database_path,
        running.id,
        "FAILED",
        failure={"kind": "spawn_failed"},
    )

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert decision.operation == "process.retry"
    assert decision.action_id == failed.id
    assert [blocker.kind for blocker in decision.blockers] == [
        "PREVIOUS_ATTEMPT_REQUIRES_REVIEW"
    ]


def test_executive_routes_negative_cognition_assessment_to_replanning(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = _plan(database_path, goal, capability="cognition.analyze")
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
    )
    running = transition_action(database_path, action.id, "RUNNING")
    completed = transition_action(
        database_path,
        running.id,
        "COMPLETED",
        reported_result={"analysis": "hipótese incorreta"},
    )
    event = _evidence(database_path, goal.id)
    assessment = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=completed.id,
        criteria=({"kind": "analysis"},),
        status="ASSESSED",
        evidence_event_ids=(event.id,),
        observed={"verdict": "NOT_SATISFIED"},
        strength=2,
    )

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "PROCEED"
    assert decision.operation == "plan.propose"
    assert decision.requires_model is True
    assert decision.reason_code == "replanning_required"
    assert decision.action_id == completed.id
    assert decision.verification_id == assessment.id


def test_executive_recognizes_bindable_change_unknown_as_file_patch_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Realizar a mudança: corrigir variável",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "unknown",
                "capability_detail": "corrigir variável no arquivo",
                "verification": "arquivo modificado",
                "intent_role": "CHANGE",
                "intent_actor": "SIMON",
            },
        ),
    )

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert decision.operation == "plan.patch"
    assert decision.capability == "file.patch"
    assert [blocker.kind for blocker in decision.blockers] == ["CAPABILITY_UNAVAILABLE"]


def test_executive_proposes_plan_completion_only_after_all_steps_verified(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = _plan(database_path, goal, capability="process.run")
    _verified_action(
        database_path,
        goal=goal,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
    )

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "PROCEED"
    assert decision.operation == "plan.complete"
    assert decision.reason_code == "plan_ready_for_completion"


def test_executive_decision_is_read_only(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    _plan(database_path, goal, capability="process.run")

    with sqlite3.connect(database_path) as connection:
        before = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("actions", "verification_results", "events")
        )

    decide_next(database_path, goal_id=goal.id)

    with sqlite3.connect(database_path) as connection:
        after = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("actions", "verification_results", "events")
        )

    assert after == before


def test_executive_reports_done_for_completed_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    transition_goal(database_path, goal.id, "COMPLETED")

    decision = decide_next(database_path, goal_id=goal.id)

    assert decision.outcome == "DONE"
    assert decision.reason_code == "goal_completed"
    assert decision.operation is None


def test_executive_next_cli_exposes_structured_gate(tmp_path: Path, capsys: object) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    _plan(database_path, goal, capability="process.run")

    assert main(["--data-dir", str(tmp_path), "executive-next", goal.id]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert "Executive: NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Operação: plan.run" in output
    assert f"Goal: {goal.id}" in output
    assert "Step: step_01" in output
    assert "Capability: process.run" in output


def test_executive_surfaces_pending_attend_when_no_goal_is_open(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="há algo relevante para revisar",
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(subscribed=True),
    )
    opening = open_attention_item(database_path, attention_event_id=assessment.event.id)

    decision = decide_next(database_path)

    assert decision.outcome == "NEEDS_ATTENTION_REVIEW"
    assert decision.reason_code == "pending_attention_items"
    assert decision.operation is None
    assert len(decision.attention_candidates) == 1
    candidate = decision.attention_candidates[0]
    assert candidate.attention_item_event_id == opening.item.event.id
    assert candidate.assessment_event_id == assessment.event.id
    assert candidate.observation_event_id == observation.event.id
    assert candidate.summary == "há algo relevante para revisar"
    assert candidate.reasons == ("subscribed",)


def test_attend_does_not_preempt_active_foreground_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    observation = record_observation(
        database_path,
        observer="filesystem",
        signal_kind="file.changed",
        summary="outro sinal relevante",
        goal_id=goal.id,
    )
    assessment = assess_observation_attention(
        database_path,
        observation_event_id=observation.event.id,
        signals=AttentionSignals(goal_relevant=True),
    )
    open_attention_item(database_path, attention_event_id=assessment.event.id)

    decision = decide_next(database_path)

    assert decision.outcome == "PROCEED"
    assert decision.operation == "plan.propose"
    assert decision.goal_id == goal.id
    assert decision.attention_candidates == ()
