import json
import sqlite3
from pathlib import Path

import pytest

from simon.actions import get_action, list_actions_for_plan
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.user_ask import answer_user_ask, dispatch_next_user_ask


def _user_ask_plan(database_path: Path) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Obter contexto do usuário",
        origin="USER",
        desired_state={"description": "informação necessária disponível"},
        success_criteria=({"description": "resposta do usuário foi obtida"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário a mensagem de erro.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece a mensagem de erro.",
            },
            {
                "id": "step_02",
                "description": "Solicitar ao usuário o caminho do arquivo.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece o caminho do arquivo.",
            },
        ),
    )
    return goal, plan.id


def test_dispatch_user_ask_creates_waiting_action_and_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _user_ask_plan(database_path)

    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id, trace_id="trc_test")

    assert dispatch.created is True
    assert dispatch.action.plan_id == plan_id
    assert dispatch.action.step_id == "step_01"
    assert dispatch.action.kind == "user.ask"
    assert dispatch.action.status == "WAITING"
    assert dispatch.action.started_at is not None
    assert dispatch.action.finished_at is None
    assert dispatch.prompt == "Solicitar ao usuário a mensagem de erro."

    with sqlite3.connect(database_path) as connection:
        event = connection.execute(
            """
            SELECT kind, source, payload_json, trace_id, goal_id
            FROM events
            WHERE kind = 'user.question.asked'
            """
        ).fetchone()

    assert event is not None
    assert event[0:2] == ("user.question.asked", "system")
    payload = json.loads(str(event[2]))
    assert payload["action_id"] == dispatch.action.id
    assert payload["step_id"] == "step_01"
    assert payload["prompt"] == dispatch.prompt
    assert event[3] == "trc_test"
    assert event[4] == goal.id


def test_dispatch_user_ask_is_idempotent_while_waiting(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _user_ask_plan(database_path)

    first = dispatch_next_user_ask(database_path, goal_id=goal.id)
    second = dispatch_next_user_ask(database_path, goal_id=goal.id)

    assert first.created is True
    assert second.created is False
    assert second.action.id == first.action.id
    assert second.prompt == first.prompt
    assert list_actions_for_plan(database_path, plan_id) == (first.action,)

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'user.question.asked'"
        ).fetchone()
    assert count == (1,)


def test_user_answer_completes_action_and_preserves_response_as_event(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _user_ask_plan(database_path)
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)

    receipt = answer_user_ask(
        database_path,
        action_id=dispatch.action.id,
        response="ValueError: arquivo ausente",
        trace_id="trc_answer",
    )

    assert receipt.action.status == "COMPLETED"
    assert receipt.action.finished_at is not None
    assert receipt.action.reported_result == {"response_event_id": receipt.response_event_id}

    stored = get_action(database_path, dispatch.action.id)
    assert stored == receipt.action

    with sqlite3.connect(database_path) as connection:
        event = connection.execute(
            """
            SELECT kind, source, payload_json, trace_id, goal_id
            FROM events
            WHERE id = ?
            """,
            (receipt.response_event_id,),
        ).fetchone()
        verification_count = connection.execute(
            "SELECT COUNT(*) FROM verification_results WHERE subject_id = ?",
            (dispatch.action.id,),
        ).fetchone()

    assert event is not None
    assert event[0:2] == ("user.response.received", "user")
    payload = json.loads(str(event[2]))
    assert payload["action_id"] == dispatch.action.id
    assert payload["response"] == "ValueError: arquivo ausente"
    assert event[3] == "trc_answer"
    assert event[4] == goal.id
    assert verification_count == (0,)


def test_user_answer_rejects_wrong_action_state_or_kind(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _user_ask_plan(database_path)
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer_user_ask(database_path, action_id=dispatch.action.id, response="primeira resposta")

    with pytest.raises(ValueError, match="está COMPLETED"):
        answer_user_ask(database_path, action_id=dispatch.action.id, response="segunda resposta")

    with pytest.raises(ValueError, match="não pode ser vazia"):
        answer_user_ask(database_path, action_id=dispatch.action.id, response="   ")


def test_waiting_user_ask_is_in_progress_for_readiness(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _user_ask_plan(database_path)
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    step = next(item for item in readiness.steps if item.step_id == "step_01")

    assert step.state == "IN_PROGRESS"
    assert step.related_action_id == dispatch.action.id
    assert readiness.next_step is not None
    assert readiness.next_step.step_id == "step_02"


def _add_user_ask_assessment(
    database_path: Path,
    *,
    action_id: str,
    response_event_id: str,
    verdict: str,
) -> str:
    from simon.verification import create_verification_result

    result = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"description": "O usuário fornece a informação solicitada."},),
        status="ASSESSED",
        evidence_event_ids=(response_event_id,),
        observed={
            "assessment_type": "user.ask.semantic",
            "verdict": verdict,
            "response_event_id": response_event_id,
            "model": "fake-model",
        },
        strength=2,
    )
    return result.id


def test_user_ask_retry_requires_review_and_creates_new_waiting_attempt(
    tmp_path: Path,
) -> None:
    from simon.actions import list_actions_for_plan
    from simon.user_ask import retry_user_ask

    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id = _user_ask_plan(database_path)
    first = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer = answer_user_ask(
        database_path,
        action_id=first.action.id,
        response="Ainda não tenho a informação.",
    )
    verification_id = _add_user_ask_assessment(
        database_path,
        action_id=first.action.id,
        response_event_id=answer.response_event_id,
        verdict="NOT_SATISFIED",
    )

    retry = retry_user_ask(
        database_path,
        action_id=first.action.id,
        trace_id="trc_retry",
    )

    assert retry.created is True
    assert retry.retry_of_action_id == first.action.id
    assert retry.review_verification_id == verification_id
    assert retry.action.id != first.action.id
    assert retry.action.step_id == first.action.step_id
    assert retry.action.status == "WAITING"
    assert retry.action.input_data["retry_of_action_id"] == first.action.id
    assert retry.action.input_data["review_verification_id"] == verification_id
    assert retry.prompt == first.prompt

    actions = list_actions_for_plan(database_path, plan_id)
    assert [action.status for action in actions] == ["COMPLETED", "WAITING"]

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT kind, source, payload_json, trace_id
            FROM events
            WHERE kind IN ('action.retry.authorized', 'user.question.asked')
              AND trace_id = 'trc_retry'
            ORDER BY occurred_at, id
            """
        ).fetchall()

    assert [row[0] for row in rows] == ["action.retry.authorized", "user.question.asked"]
    assert rows[0][1] == "user"
    authorization = json.loads(str(rows[0][2]))
    assert authorization["retry_of_action_id"] == first.action.id
    assert authorization["retry_action_id"] == retry.action.id
    assert authorization["review_verification_id"] == verification_id
    question = json.loads(str(rows[1][2]))
    assert question["action_id"] == retry.action.id
    assert question["retry_of_action_id"] == first.action.id


def test_user_ask_retry_is_idempotent_while_retry_waits(tmp_path: Path) -> None:
    from simon.user_ask import retry_user_ask

    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _user_ask_plan(database_path)
    first = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer = answer_user_ask(
        database_path,
        action_id=first.action.id,
        response="Ainda não tenho a informação.",
    )
    _add_user_ask_assessment(
        database_path,
        action_id=first.action.id,
        response_event_id=answer.response_event_id,
        verdict="NOT_SATISFIED",
    )

    created = retry_user_ask(database_path, action_id=first.action.id)
    repeated = retry_user_ask(database_path, action_id=first.action.id)

    assert created.created is True
    assert repeated.created is False
    assert repeated.action.id == created.action.id


def test_user_ask_retry_rejects_missing_or_positive_assessment(tmp_path: Path) -> None:
    from simon.user_ask import retry_user_ask

    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _user_ask_plan(database_path)
    first = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer = answer_user_ask(
        database_path,
        action_id=first.action.id,
        response="print('ok')",
    )

    with pytest.raises(ValueError, match="retry exige assessment"):
        retry_user_ask(database_path, action_id=first.action.id)

    _add_user_ask_assessment(
        database_path,
        action_id=first.action.id,
        response_event_id=answer.response_event_id,
        verdict="SATISFIED",
    )
    with pytest.raises(ValueError, match="SATISFIED"):
        retry_user_ask(database_path, action_id=first.action.id)


def test_user_ask_retry_can_refine_prompt_and_blocks_stale_retry(tmp_path: Path) -> None:
    from simon.user_ask import retry_user_ask

    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _user_ask_plan(database_path)
    first = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer = answer_user_ask(
        database_path,
        action_id=first.action.id,
        response="Não tenho isso agora.",
    )
    _add_user_ask_assessment(
        database_path,
        action_id=first.action.id,
        response_event_id=answer.response_event_id,
        verdict="UNCLEAR",
    )
    retry = retry_user_ask(
        database_path,
        action_id=first.action.id,
        prompt="Cole aqui o conteúdo completo do script, se estiver disponível.",
    )
    assert retry.prompt == "Cole aqui o conteúdo completo do script, se estiver disponível."

    second_answer = answer_user_ask(
        database_path,
        action_id=retry.action.id,
        response="Ainda não tenho o arquivo.",
    )
    _add_user_ask_assessment(
        database_path,
        action_id=retry.action.id,
        response_event_id=second_answer.response_event_id,
        verdict="NOT_SATISFIED",
    )

    with pytest.raises(ValueError, match="já foi sucedida"):
        retry_user_ask(database_path, action_id=first.action.id)
