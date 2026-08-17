from pathlib import Path

import pytest

from simon.actions import create_action, transition_action
from simon.events import Event, append_event
from simon.goal_completion import complete_goal_from_assessment
from simon.goal_verification import (
    GoalCriterionAssessment,
    GoalEvidenceAssessment,
    assess_goal_outcome,
)
from simon.goals import Goal, get_goal, insert_goal, list_open_goals
from simon.model_provider import StructuredModelResult
from simon.plan_completion import complete_verified_plan
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result, list_verification_results


class FakeGoalAssessmentProvider:
    def __init__(self, assessment: GoalEvidenceAssessment) -> None:
        self.assessment = assessment

    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
        return StructuredModelResult(
            model="fake-model",
            output=self.assessment,
        )


def _completed_plan(database_path: Path) -> tuple[Goal, str]:
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
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script corrigido.",
                "verification": "A execução foi observada.",
            },
            {
                "id": "step_02",
                "description": "Analisar o resultado final.",
                "verification": "O resultado final foi analisado.",
            },
        ),
    )
    for step_id, payload in (
        ("step_01", {"exit_code": 0}),
        ("step_02", {"summary": "execução consistente e sem erro"}),
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
            kind="test.goal.completion.evidence",
            source="test",
            payload=payload,
            goal_id=goal.id,
        )
        append_event(database_path, evidence)
        create_verification_result(
            database_path,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=({"description": "evidência local verificada"},),
            status="VERIFIED",
            evidence_event_ids=(evidence.id,),
            observed={"ok": True},
            strength=3,
        )

    completion = complete_verified_plan(database_path, goal_id=goal.id)
    return goal, completion.plan.id


def _satisfied_assessment() -> GoalEvidenceAssessment:
    return GoalEvidenceAssessment(
        criteria=[
            GoalCriterionAssessment(
                criterion_index=1,
                verdict="SATISFIED",
                rationale="A execução observada terminou como esperado.",
                supporting_step_ids=["step_01"],
            ),
            GoalCriterionAssessment(
                criterion_index=2,
                verdict="SATISFIED",
                rationale="A análise final não encontrou mensagem de erro.",
                supporting_step_ids=["step_02"],
            ),
        ],
        missing_evidence=[],
    )


def _satisfied_goal_assessment(database_path: Path) -> tuple[Goal, str, str]:
    goal, plan_id = _completed_plan(database_path)
    receipt = assess_goal_outcome(
        database_path,
        FakeGoalAssessmentProvider(_satisfied_assessment()),
        model="fake-model",
        goal_id=goal.id,
    )
    assert receipt.overall_verdict == "SATISFIED"
    return goal, plan_id, receipt.verification.id


def test_goal_completion_promotes_satisfied_assessment_and_closes_goal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id, assessment_id = _satisfied_goal_assessment(database_path)

    receipt = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )

    assert receipt.created is True
    assert receipt.assessment.id == assessment_id
    assert receipt.verification.subject_type == "GOAL"
    assert receipt.verification.subject_id == goal.id
    assert receipt.verification.status == "VERIFIED"
    assert receipt.verification.strength == 3
    assert receipt.verification.observed["verification_type"] == "goal.assessment_confirmation"
    assert receipt.verification.observed["confirmed_assessment_id"] == assessment_id
    assert receipt.verification.observed["plan_id"] == plan_id
    assert receipt.verification.observed["confirmed_by"] == "user"
    assert receipt.confirmation_event_id in receipt.verification.evidence_event_ids
    assert receipt.goal.status == "COMPLETED"
    assert get_goal(database_path, goal.id) == receipt.goal
    assert list_open_goals(database_path) == ()


def test_goal_completion_is_idempotent_for_same_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, _, assessment_id = _satisfied_goal_assessment(database_path)

    first = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )
    second = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert second.confirmation_event_id == first.confirmation_event_id
    assert second.completion_event_id == first.completion_event_id
    results = list_verification_results(
        database_path,
        subject_type="GOAL",
        subject_id=first.goal.id,
    )
    assert [result.status for result in results] == ["ASSESSED", "VERIFIED"]


def test_goal_completion_rejects_non_satisfied_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _ = _completed_plan(database_path)
    assessment = GoalEvidenceAssessment(
        criteria=[
            GoalCriterionAssessment(
                criterion_index=1,
                verdict="SATISFIED",
                rationale="Primeiro critério atendido.",
                supporting_step_ids=["step_01"],
            ),
            GoalCriterionAssessment(
                criterion_index=2,
                verdict="INSUFFICIENT_EVIDENCE",
                rationale="Ainda falta evidência.",
                supporting_step_ids=["step_02"],
            ),
        ],
        missing_evidence=["Uma confirmação final."],
    )
    assessed = assess_goal_outcome(
        database_path,
        FakeGoalAssessmentProvider(assessment),
        model="fake-model",
        goal_id=goal.id,
    )

    with pytest.raises(ValueError, match="somente assessment SATISFIED"):
        complete_goal_from_assessment(
            database_path,
            assessment_verification_id=assessed.verification.id,
        )

    persisted = get_goal(database_path, goal.id)
    assert persisted is not None
    assert persisted.status == "ACTIVE"


def test_goal_completion_rejects_satisfied_assessment_with_missing_evidence(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _, assessment_id = _satisfied_goal_assessment(database_path)
    original = list_verification_results(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
    )[0]
    tampered = create_verification_result(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
        criteria=goal.success_criteria,
        status="ASSESSED",
        evidence_event_ids=original.evidence_event_ids,
        observed={
            **original.observed,
            "missing_evidence": ["Ainda falta uma prova."],
        },
        strength=2,
    )

    with pytest.raises(ValueError, match="ainda declara evidência ausente"):
        complete_goal_from_assessment(
            database_path,
            assessment_verification_id=tampered.id,
        )

    # O assessment anterior também se tornou obsoleto diante da observação mais recente.
    with pytest.raises(ValueError, match="assessment goal.semantic mais recente"):
        complete_goal_from_assessment(
            database_path,
            assessment_verification_id=assessment_id,
        )


def test_goal_completion_rejects_stale_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, _, assessment_id = _satisfied_goal_assessment(database_path)
    original = list_verification_results(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
    )[0]
    create_verification_result(
        database_path,
        subject_type="GOAL",
        subject_id=goal.id,
        criteria=goal.success_criteria,
        status="ASSESSED",
        evidence_event_ids=original.evidence_event_ids,
        observed={
            **original.observed,
            "verdict": "INSUFFICIENT_EVIDENCE",
            "criterion_assessments": [
                {
                    **item,
                    "verdict": "INSUFFICIENT_EVIDENCE",
                }
                for item in original.observed["criterion_assessments"]
            ],
            "missing_evidence": ["Nova evidência necessária."],
        },
        strength=2,
    )

    with pytest.raises(ValueError, match="assessment goal.semantic mais recente"):
        complete_goal_from_assessment(
            database_path,
            assessment_verification_id=assessment_id,
        )


def test_goal_completion_records_confirmation_and_completion_events(tmp_path: Path) -> None:
    import json
    import sqlite3

    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id, assessment_id = _satisfied_goal_assessment(database_path)

    receipt = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
        trace_id="trc_goal_completion",
    )

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT id, kind, source, payload_json, trace_id
            FROM events
            WHERE id IN (?, ?)
            ORDER BY occurred_at, id
            """,
            (receipt.confirmation_event_id, receipt.completion_event_id),
        ).fetchall()

    by_kind = {str(row[1]): row for row in rows}
    confirmation = by_kind["verification.goal_assessment.confirmed"]
    completion = by_kind["goal.completed"]
    confirmation_payload = json.loads(str(confirmation[3]))
    completion_payload = json.loads(str(completion[3]))

    assert confirmation[2] == "user"
    assert confirmation[4] == "trc_goal_completion"
    assert confirmation_payload["assessment_verification_id"] == assessment_id
    assert confirmation_payload["plan_id"] == plan_id
    assert completion[2] == "system"
    assert completion[4] == "trc_goal_completion"
    assert completion_payload["goal_id"] == goal.id
    assert completion_payload["goal_verification_id"] == receipt.verification.id
    assert completion_payload["status"] == "COMPLETED"


def test_goal_completion_closes_causal_experience_without_copying_entire_event_log(
    tmp_path: Path,
) -> None:
    import sqlite3

    from simon.events import Event, append_event
    from simon.experiences import get_experience

    database_path, _ = initialize_storage(tmp_path)
    goal, _, assessment_id = _satisfied_goal_assessment(database_path)
    unrelated = Event.create(
        kind="debug.noise",
        source="test",
        payload={"note": "não é causal"},
        goal_id=goal.id,
    )
    append_event(database_path, unrelated)

    receipt = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )
    experience = receipt.experience_closure.experience

    assert receipt.experience_closure.created is True
    assert experience.goal_id == goal.id
    assert experience.status == "CLOSED"
    assert experience.outcome == "SUCCESS"
    assert experience.started_at == goal.created_at
    assert experience.ended_at is not None
    assert receipt.completion_event_id in experience.event_ids
    assert receipt.experience_closure.closure_event_id in experience.event_ids
    assert unrelated.id not in experience.event_ids
    assert get_experience(database_path, experience.id) == experience

    with sqlite3.connect(database_path) as connection:
        action_ids = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM actions WHERE goal_id = ? ORDER BY created_at, id",
                (goal.id,),
            ).fetchall()
        )
    assert experience.action_ids == action_ids
    assert receipt.verification.id in experience.verification_ids


def test_goal_completion_experience_records_plan_lineage(
    tmp_path: Path,
) -> None:
    import json
    import sqlite3

    database_path, _ = initialize_storage(tmp_path)
    goal, plan_id, assessment_id = _satisfied_goal_assessment(database_path)

    receipt = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT payload_json, experience_id FROM events WHERE id = ?",
            (receipt.experience_closure.closure_event_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row[0]))
    assert row[1] == receipt.experience_closure.experience.id
    assert payload["goal_id"] == goal.id
    assert payload["goal_verification_id"] == receipt.verification.id
    assert payload["plans"] == [
        {"plan_id": plan_id, "revision": 1, "status": "COMPLETED"}
    ]
    assert payload["action_ids"] == list(receipt.experience_closure.experience.action_ids)
    assert payload["verification_ids"] == list(
        receipt.experience_closure.experience.verification_ids
    )


def test_goal_completion_reuses_same_closed_experience(
    tmp_path: Path,
) -> None:
    import sqlite3

    database_path, _ = initialize_storage(tmp_path)
    _, _, assessment_id = _satisfied_goal_assessment(database_path)

    first = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )
    second = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )

    assert second.created is False
    assert second.experience_closure.created is False
    assert second.experience_closure.experience.id == first.experience_closure.experience.id
    assert second.experience_closure.closure_event_id == first.experience_closure.closure_event_id
    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM experiences WHERE goal_id = ?",
            (first.goal.id,),
        ).fetchone()
    assert count is not None and count[0] == 1


def test_existing_goal_completion_can_backfill_missing_experience(
    tmp_path: Path,
) -> None:
    import sqlite3

    database_path, _ = initialize_storage(tmp_path)
    _, _, assessment_id = _satisfied_goal_assessment(database_path)
    first = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "DELETE FROM events WHERE id = ?",
            (first.experience_closure.closure_event_id,),
        )
        connection.execute(
            "DELETE FROM experiences WHERE id = ?",
            (first.experience_closure.experience.id,),
        )

    backfilled = complete_goal_from_assessment(
        database_path,
        assessment_verification_id=assessment_id,
    )

    assert backfilled.created is False
    assert backfilled.experience_closure.created is True
    assert backfilled.experience_closure.experience.status == "CLOSED"
    assert backfilled.experience_closure.experience.outcome == "SUCCESS"
