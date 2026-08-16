from pathlib import Path

import pytest

from simon.actions import create_action
from simon.events import get_event
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.user_ask import answer_user_ask, dispatch_next_user_ask
from simon.user_ask_verification import (
    AssessmentVerdict,
    UserAskCriterionAssessment,
    assess_user_ask_response,
    confirm_user_ask_assessment,
)
from simon.verification import list_verification_results


class FakeAssessmentProvider:
    def __init__(self, verdict: AssessmentVerdict) -> None:
        self.verdict = verdict
        self.calls = 0

    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
        self.calls += 1
        response_model = kwargs["response_model"]
        assert response_model is UserAskCriterionAssessment
        rationale = {
            "SATISFIED": "A resposta fornece diretamente a informação solicitada.",
            "NOT_SATISFIED": "A resposta declara que a informação ainda não foi fornecida.",
            "UNCLEAR": "A resposta não permite concluir se o critério foi atendido.",
        }[self.verdict]
        output = UserAskCriterionAssessment(
            verdict=self.verdict,
            rationale=rationale,
            missing_information=(
                ["conteúdo do script"] if self.verdict != "SATISFIED" else []
            ),
        )
        return StructuredModelResult(
            model="fake-model",
            output=output,
            prompt_eval_count=30,
            eval_count=12,
            total_duration_ns=1_000_000_000,
        )


def _answered_user_ask(database_path: Path, response: str) -> tuple[Goal, str]:
    goal = Goal.create(
        title="Obter script",
        origin="USER",
        desired_state={"description": "conteúdo do script disponível"},
        success_criteria=({"description": "script recebido"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar ao usuário o conteúdo do script.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece o código ou arquivo do script.",
            },
            {
                "id": "step_02",
                "description": "Solicitar ao usuário a mensagem de erro.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece a mensagem de erro.",
            },
        ),
    )
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)
    answer_user_ask(database_path, action_id=dispatch.action.id, response=response)
    return goal, dispatch.action.id


def test_user_ask_assessment_persists_model_judgment_as_assessed(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _answered_user_ask(database_path, "Ainda não forneci o conteúdo do script.")
    provider = FakeAssessmentProvider("NOT_SATISFIED")

    receipt = assess_user_ask_response(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    assert receipt.created is True
    assert receipt.assessment.verdict == "NOT_SATISFIED"
    assert receipt.verification.status == "ASSESSED"
    assert receipt.verification.strength == 2
    assert receipt.verification.criteria == (
        {"description": "O usuário fornece o código ou arquivo do script."},
    )
    assert len(receipt.verification.evidence_event_ids) == 1
    assert receipt.verification.observed["assessment_type"] == "user.ask.semantic"
    assert receipt.verification.observed["model"] == "fake-model"
    assert "response" not in receipt.verification.observed


def test_user_ask_assessment_is_idempotent_for_same_response_and_model(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _answered_user_ask(database_path, "Ainda não forneci o conteúdo do script.")
    provider = FakeAssessmentProvider("NOT_SATISFIED")

    first = assess_user_ask_response(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )
    second = assess_user_ask_response(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert provider.calls == 1
    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    )
    assert results == (first.verification,)


def test_negative_assessment_replaces_verification_pending_blocker(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _answered_user_ask(database_path, "Ainda não forneci o conteúdo do script.")
    provider = FakeAssessmentProvider("NOT_SATISFIED")
    receipt = assess_user_ask_response(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    step = next(item for item in readiness.steps if item.step_id == "step_01")

    assert step.state == "BLOCKED"
    assert len(step.blockers) == 1
    assert step.blockers[0].kind == "CRITERION_NOT_SATISFIED"
    assert step.blockers[0].detail == receipt.verification.id
    assert readiness.next_step is not None
    assert readiness.next_step.step_id == "step_02"


def test_positive_model_assessment_still_requires_confirmation(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _answered_user_ask(
        database_path,
        "print('ok')",
    )
    provider = FakeAssessmentProvider("SATISFIED")
    receipt = assess_user_ask_response(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    step = next(item for item in readiness.steps if item.step_id == "step_01")

    assert receipt.verification.status == "ASSESSED"
    assert step.state == "BLOCKED"
    assert step.blockers[0].kind == "ASSESSED_SATISFIED_REQUIRES_CONFIRMATION"
    assert step.blockers[0].detail == receipt.verification.id


def test_user_ask_assessment_rejects_waiting_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Obter script",
        origin="USER",
        desired_state={"description": "conteúdo do script disponível"},
        success_criteria=({"description": "script recebido"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Solicitar o script.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "O usuário fornece o script.",
            },
        ),
    )
    dispatch = dispatch_next_user_ask(database_path, goal_id=goal.id)

    with pytest.raises(ValueError, match="está WAITING"):
        assess_user_ask_response(
            database_path,
            FakeAssessmentProvider("SATISFIED"),
            model="fake-model",
            action_id=dispatch.action.id,
        )


def test_assessment_prompt_treats_criterion_as_authoritative(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _answered_user_ask(database_path, "print('ok')")

    class CapturingProvider(FakeAssessmentProvider):
        def __init__(self) -> None:
            super().__init__("SATISFIED")
            self.system: str | None = None

        def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
            system = kwargs.get("system")
            assert isinstance(system, str)
            self.system = system
            return super().generate_structured(**kwargs)

    provider = CapturingProvider()
    assess_user_ask_response(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    assert provider.system is not None
    assert "critério é a única fonte autoritativa" in provider.system
    assert "nunca pode tornar o critério mais estrito" in provider.system
    assert "não presuma que um script curto é incompleto" in provider.system


def test_satisfied_assessment_can_be_explicitly_confirmed_as_verified(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _answered_user_ask(database_path, "print('ok')")
    assessment = assess_user_ask_response(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )

    confirmation = confirm_user_ask_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
    )

    assert confirmation.created is True
    assert confirmation.verification.status == "VERIFIED"
    assert confirmation.verification.strength == 3
    assert confirmation.verification.subject_id == action_id
    assert confirmation.verification.criteria == assessment.verification.criteria
    assert assessment.verification.evidence_event_ids[0] in confirmation.verification.evidence_event_ids
    assert confirmation.confirmation_event_id in confirmation.verification.evidence_event_ids
    assert confirmation.verification.observed["confirmed_assessment_id"] == assessment.verification.id
    assert confirmation.verification.observed["confirmed_by"] == "user"

    event = get_event(database_path, confirmation.confirmation_event_id)
    assert event is not None
    assert event.kind == "verification.assessment.confirmed"
    assert event.source == "user"
    assert event.goal_id == goal.id


def test_confirmation_is_idempotent_for_same_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _answered_user_ask(database_path, "print('ok')")
    assessment = assess_user_ask_response(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )

    first = confirm_user_ask_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
    )
    second = confirm_user_ask_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
    )

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert second.confirmation_event_id == first.confirmation_event_id


def test_confirmation_rejects_non_satisfied_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _answered_user_ask(database_path, "Ainda não forneci o script.")
    assessment = assess_user_ask_response(
        database_path,
        FakeAssessmentProvider("NOT_SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )

    with pytest.raises(ValueError, match="somente assessment SATISFIED"):
        confirm_user_ask_assessment(
            database_path,
            assessment_verification_id=assessment.verification.id,
        )


def test_confirmation_promotes_step_readiness_to_verified(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _answered_user_ask(database_path, "print('ok')")
    assessment = assess_user_ask_response(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )
    confirm_user_ask_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
    )

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    step = next(item for item in readiness.steps if item.step_id == "step_01")

    assert step.state == "VERIFIED"
    assert step.blockers == ()
    assert step.related_action_id == action_id
    assert readiness.next_step is not None
    assert readiness.next_step.step_id == "step_02"


def test_confirmation_rejects_assessment_from_stale_step_attempt(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id = _answered_user_ask(database_path, "print('ok')")
    assessment = assess_user_ask_response(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )
    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    create_action(
        database_path,
        goal_id=goal.id,
        plan_id=readiness.plan.id,
        step_id="step_01",
        kind="user.ask",
        input_data={
            "prompt": "Nova tentativa",
            "verification": "O usuário fornece o código ou arquivo do script.",
        },
    )

    with pytest.raises(ValueError, match="tentativa mais recente"):
        confirm_user_ask_assessment(
            database_path,
            assessment_verification_id=assessment.verification.id,
        )


def test_confirmation_rolls_back_event_if_verified_insert_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id = _answered_user_ask(database_path, "print('ok')")
    assessment = assess_user_ask_response(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )

    def fail_insert(*args: object, **kwargs: object) -> object:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(
        "simon.user_ask_verification.create_verification_result_in_connection",
        fail_insert,
    )

    with pytest.raises(RuntimeError, match="falha simulada"):
        confirm_user_ask_assessment(
            database_path,
            assessment_verification_id=assessment.verification.id,
        )

    import sqlite3

    with sqlite3.connect(database_path) as connection:
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'verification.assessment.confirmed'"
        ).fetchone()
        verified_count = connection.execute(
            "SELECT COUNT(*) FROM verification_results WHERE status = 'VERIFIED'"
        ).fetchone()

    assert event_count == (0,)
    assert verified_count == (0,)
