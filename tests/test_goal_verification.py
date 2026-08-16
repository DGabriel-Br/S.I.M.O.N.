from pathlib import Path

import pytest

from simon.actions import create_action, transition_action
from simon.events import Event, append_event
from simon.goal_verification import (
    GoalCriterionAssessment,
    GoalEvidenceAssessment,
    assess_goal_outcome,
)
from simon.goals import Goal, get_goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.plan_completion import complete_verified_plan
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result, list_verification_results


class FakeGoalAssessmentProvider:
    def __init__(self, assessment: GoalEvidenceAssessment) -> None:
        self.assessment = assessment
        self.calls = 0
        self.system: str | None = None

    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
        self.calls += 1
        system = kwargs.get("system")
        assert isinstance(system, str)
        self.system = system
        return StructuredModelResult(
            model="fake-model",
            output=self.assessment,
            prompt_eval_count=30,
            eval_count=12,
            total_duration_ns=750_000_000,
        )


def _goal(database_path: Path) -> Goal:
    goal = Goal.create(
        title="Corrigir execução",
        origin="USER",
        desired_state={"description": "O script executa corretamente."},
        success_criteria=(
            {"description": "A execução conclui com sucesso."},
            {"description": "Não ocorre mensagem de erro."},
        ),
    )
    insert_goal(database_path, goal)
    return goal


def _completed_goal(database_path: Path) -> tuple[Goal, str, tuple[str, str]]:
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Observar a execução.",
                "capability": "test.observe",
                "verification": "A execução foi observada.",
            },
            {
                "id": "step_02",
                "description": "Observar a falha.",
                "capability": "test.observe",
                "verification": "A mensagem de erro foi observada.",
            },
        ),
    )
    evidence_ids: list[str] = []
    for step_id, payload in (
        ("step_01", {"output": "execução iniciada"}),
        ("step_02", {"error": "NameError: resultado is not defined"}),
    ):
        action = create_action(
            database_path,
            goal_id=goal.id,
            plan_id=plan.id,
            step_id=step_id,
            kind="test.observe",
        )
        transition_action(database_path, action.id, "RUNNING")
        transition_action(database_path, action.id, "COMPLETED", reported_result={"ok": True})
        evidence = Event.create(
            kind="test.goal.evidence",
            source="test",
            payload=payload,
            goal_id=goal.id,
        )
        append_event(database_path, evidence)
        evidence_ids.append(evidence.id)
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=({"description": "evidência local observada"},),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"ok": True},
            strength=3,
        )

    completion = complete_verified_plan(database_path, goal_id=goal.id)
    return goal, completion.completion_event_id, (evidence_ids[0], evidence_ids[1])


def _negative_assessment() -> GoalEvidenceAssessment:
    return GoalEvidenceAssessment(
        criteria=[
            GoalCriterionAssessment(
                criterion_index=1,
                verdict="INSUFFICIENT_EVIDENCE",
                rationale="A evidência não demonstra uma conclusão bem-sucedida.",
                supporting_step_ids=["step_01"],
            ),
            GoalCriterionAssessment(
                criterion_index=2,
                verdict="NOT_SATISFIED",
                rationale="A evidência contém uma mensagem de erro.",
                supporting_step_ids=["step_02"],
            ),
        ],
        missing_evidence=["Uma execução posterior sem erro."],
    )


def test_goal_assessment_persists_model_judgment_without_completing_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, completion_event_id, evidence_ids = _completed_goal(database_path)
    provider = FakeGoalAssessmentProvider(_negative_assessment())

    receipt = assess_goal_outcome(
        database_path,
        provider,
        model="fake-model",
        goal_id=goal.id,
    )

    assert receipt.created is True
    assert receipt.overall_verdict == "NOT_SATISFIED"
    assert receipt.verification.subject_type == "GOAL"
    assert receipt.verification.subject_id == goal.id
    assert receipt.verification.status == "ASSESSED"
    assert receipt.verification.strength == 2
    assert completion_event_id in receipt.verification.evidence_event_ids
    assert set(evidence_ids) <= set(receipt.verification.evidence_event_ids)
    assert receipt.verification.observed["assessment_type"] == "goal.semantic"
    assert receipt.verification.observed["verdict"] == "NOT_SATISFIED"

    persisted_goal = get_goal(database_path, goal.id)
    assert persisted_goal is not None
    assert persisted_goal.status == "ACTIVE"


def test_goal_assessment_is_idempotent_for_same_completed_plan_and_model(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _, _ = _completed_goal(database_path)
    provider = FakeGoalAssessmentProvider(_negative_assessment())

    first = assess_goal_outcome(database_path, provider, model="fake-model", goal_id=goal.id)
    second = assess_goal_outcome(database_path, provider, model="fake-model", goal_id=goal.id)

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert provider.calls == 1
    results = list_verification_results(database_path, subject_type="GOAL", subject_id=goal.id)
    assert results == (first.verification,)


def test_goal_assessment_requires_completed_plan(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_01", "description": "Ainda ativo"},),
    )

    with pytest.raises(ValueError, match="não possui plan COMPLETED"):
        assess_goal_outcome(
            database_path,
            FakeGoalAssessmentProvider(_negative_assessment()),
            model="fake-model",
            goal_id=goal.id,
        )


def test_goal_assessment_rejects_unknown_supporting_step(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _, _ = _completed_goal(database_path)
    provider = FakeGoalAssessmentProvider(
        GoalEvidenceAssessment(
            criteria=[
                GoalCriterionAssessment(
                    criterion_index=1,
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale="Ainda falta evidência.",
                    supporting_step_ids=["step_99"],
                ),
                GoalCriterionAssessment(
                    criterion_index=2,
                    verdict="INSUFFICIENT_EVIDENCE",
                    rationale="Ainda falta evidência.",
                    supporting_step_ids=[],
                ),
            ]
        )
    )

    with pytest.raises(ValueError, match="step inexistente: step_99"):
        assess_goal_outcome(database_path, provider, model="fake-model", goal_id=goal.id)

    assert list_verification_results(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
    ) == ()


def test_goal_assessment_prompt_does_not_equate_plan_completion_with_goal_success(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _, _ = _completed_goal(database_path)
    provider = FakeGoalAssessmentProvider(_negative_assessment())

    assess_goal_outcome(database_path, provider, model="fake-model", goal_id=goal.id)

    assert provider.system is not None
    assert "Plan estar COMPLETED prova somente" in provider.system
    assert "não prova automaticamente que o Goal global foi alcançado" in provider.system


def test_latest_goal_assessment_context_exposes_persisted_feedback_and_evidence(
    tmp_path: Path,
) -> None:
    from simon.goal_verification import get_latest_goal_assessment_context

    database_path, _ = initialize_storage(tmp_path)
    goal, completion_event_id, evidence_ids = _completed_goal(database_path)
    provider = FakeGoalAssessmentProvider(_negative_assessment())
    receipt = assess_goal_outcome(
        database_path,
        provider,
        model="fake-model",
        goal_id=goal.id,
    )

    context = get_latest_goal_assessment_context(database_path, goal.id)

    assert context is not None
    assert context.verification_id == receipt.verification.id
    assert context.verdict == "NOT_SATISFIED"
    assert context.plan_id == receipt.plan_id
    assert context.plan_revision == receipt.plan_revision
    assert context.missing_evidence == ("Uma execução posterior sem erro.",)
    assert context.criterion_assessments[1]["verdict"] == "NOT_SATISFIED"
    event_ids = {event.id for event in context.evidence_events}
    assert completion_event_id in event_ids
    assert set(evidence_ids) <= event_ids


def test_latest_goal_assessment_context_returns_none_without_goal_assessment(
    tmp_path: Path,
) -> None:
    from simon.goal_verification import get_latest_goal_assessment_context

    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)

    assert get_latest_goal_assessment_context(database_path, goal.id) is None
