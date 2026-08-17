from pathlib import Path

import pytest

from simon.actions import create_action, transition_action
from simon.assessment_confirmation import confirm_action_assessment
from simon.cognition_analysis_verification import (
    ASSESSMENT_TYPE,
    CognitionAnalysisCriterionAssessment,
    assess_cognition_analysis,
)
from simon.events import Event, append_event, get_event
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result, list_verification_results


class FakeAssessmentProvider:
    def __init__(self, verdict: str = "SATISFIED") -> None:
        self.verdict = verdict
        self.calls = 0
        self.prompt = ""
        self.system = ""

    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured(self, **kwargs: object) -> StructuredModelResult[object]:
        self.calls += 1
        self.prompt = str(kwargs["prompt"])
        self.system = str(kwargs["system"])
        missing = [] if self.verdict == "SATISFIED" else ["causa conclusiva"]
        output = CognitionAnalysisCriterionAssessment(
            verdict=self.verdict,  # type: ignore[arg-type]
            rationale=(
                "O finding identifica a causa e cita a evidência observada."
                if self.verdict == "SATISFIED"
                else "A análise não sustenta uma conclusão suficiente."
            ),
            missing_information=missing,
        )
        return StructuredModelResult(
            model="fake-model",
            output=output,
            prompt_eval_count=30,
            eval_count=10,
            total_duration_ns=700_000_000,
        )


def _completed_analysis(database_path: Path) -> tuple[Goal, str, str, str]:
    goal = Goal.create(
        title="Diagnosticar execução",
        origin="USER",
        desired_state={"description": "A causa da falha foi identificada."},
        success_criteria=({"description": "Existe diagnóstico fundamentado."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar: stderr da execução.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A causa observável da falha foi identificada.",
            },
        ),
    )
    evidence = Event.create(
        kind="process.execution.completed",
        source="tool",
        payload={
            "exit_code": 1,
            "stdout": "",
            "stderr": "NameError: name 'resultado' is not defined",
            "duration_seconds": 0.2,
        },
        goal_id=goal.id,
    )
    append_event(database_path, evidence)

    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="cognition.analyze",
        input_data={
            "model": "analysis-model",
            "task": "Analisar: stderr da execução.",
            "verification": "A causa observável da falha foi identificada.",
            "evidence_event_ids": [evidence.id],
        },
    )
    transition_action(database_path, action.id, "RUNNING")
    analysis_event = Event.create(
        kind="cognition.analysis.completed",
        source="cognition",
        payload={
            "action_id": action.id,
            "plan_id": plan.id,
            "step_id": "step_01",
            "model": "analysis-model",
            "analysis": {
                "summary": "A execução falhou por uma variável ausente.",
                "findings": [
                    {
                        "statement": "O stderr registra NameError para a variável resultado.",
                        "evidence_event_ids": [evidence.id],
                    }
                ],
                "uncertainties": [],
            },
            "evidence_event_ids": [evidence.id],
            "prompt_eval_count": 40,
            "eval_count": 15,
            "total_duration_ns": 900_000_000,
        },
        goal_id=goal.id,
    )
    append_event(database_path, analysis_event)
    completed = transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={
            "analysis_event_id": analysis_event.id,
            "model": "analysis-model",
        },
    )
    return goal, completed.id, analysis_event.id, evidence.id


def test_analysis_assessment_persists_assessed_with_full_evidence_lineage(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id, analysis_event_id, evidence_event_id = _completed_analysis(database_path)
    provider = FakeAssessmentProvider("SATISFIED")

    receipt = assess_cognition_analysis(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    assert receipt.created is True
    assert receipt.verification.status == "ASSESSED"
    assert receipt.verification.strength == 2
    assert receipt.verification.observed["assessment_type"] == ASSESSMENT_TYPE
    assert receipt.verification.observed["verdict"] == "SATISFIED"
    assert receipt.verification.observed["analysis_event_id"] == analysis_event_id
    assert receipt.verification.evidence_event_ids == (analysis_event_id, evidence_event_id)
    assert "NameError" in provider.prompt
    assert "critério é a única fonte autoritativa" in provider.system
    assert "não pode se promover a VERIFIED" in provider.system

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "BLOCKED"
    assert readiness.steps[0].blockers[0].kind == "ASSESSED_SATISFIED_REQUIRES_CONFIRMATION"
    assert readiness.steps[0].blockers[0].detail == receipt.verification.id


def test_analysis_assessment_is_idempotent_for_same_event_and_model(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id, _, _ = _completed_analysis(database_path)
    provider = FakeAssessmentProvider("SATISFIED")

    first = assess_cognition_analysis(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )
    second = assess_cognition_analysis(
        database_path,
        provider,
        model="fake-model",
        action_id=action_id,
    )

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert provider.calls == 1


def test_unclear_analysis_assessment_stays_blocked_without_confirmation_path(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id, _, _ = _completed_analysis(database_path)
    receipt = assess_cognition_analysis(
        database_path,
        FakeAssessmentProvider("UNCLEAR"),
        model="fake-model",
        action_id=action_id,
    )

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert receipt.verification.status == "ASSESSED"
    assert readiness.steps[0].blockers[0].kind == "ASSESSMENT_INCONCLUSIVE"

    with pytest.raises(ValueError, match="somente assessment SATISFIED"):
        confirm_action_assessment(
            database_path,
            assessment_verification_id=receipt.verification.id,
        )


def test_positive_analysis_assessment_can_be_confirmed_and_verifies_step(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id, _, _ = _completed_analysis(database_path)
    assessment = assess_cognition_analysis(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )

    confirmation = confirm_action_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
        trace_id="trc_analysis_confirm",
    )

    assert confirmation.created is True
    assert confirmation.verification.status == "VERIFIED"
    assert confirmation.verification.subject_id == action_id
    assert confirmation.verification.observed["verification_type"] == (
        "cognition.analyze.assessment_confirmation"
    )
    assert confirmation.verification.observed["confirmed_assessment_id"] == (
        assessment.verification.id
    )
    event = get_event(database_path, confirmation.confirmation_event_id)
    assert event is not None
    assert event.kind == "verification.assessment.confirmed"
    assert event.source == "user"
    assert event.trace_id == "trc_analysis_confirm"
    assert event.payload["assessment_type"] == ASSESSMENT_TYPE

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.steps[0].state == "VERIFIED"
    assert readiness.steps[0].related_action_id == action_id


def test_analysis_confirmation_is_idempotent(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id, _, _ = _completed_analysis(database_path)
    assessment = assess_cognition_analysis(
        database_path,
        FakeAssessmentProvider("SATISFIED"),
        model="fake-model",
        action_id=action_id,
    )

    first = confirm_action_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
    )
    second = confirm_action_assessment(
        database_path,
        assessment_verification_id=assessment.verification.id,
    )

    assert first.created is True
    assert second.created is False
    assert second.verification.id == first.verification.id
    assert second.confirmation_event_id == first.confirmation_event_id


def test_analysis_assessment_rejects_stale_step_attempt(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal, action_id, _, evidence_event_id = _completed_analysis(database_path)
    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    create_action(
        database_path,
        goal_id=goal.id,
        plan_id=readiness.plan.id,
        step_id="step_01",
        kind="cognition.analyze",
        input_data={
            "model": "analysis-model",
            "task": "Nova análise",
            "verification": "A causa observável da falha foi identificada.",
            "evidence_event_ids": [evidence_event_id],
        },
    )

    with pytest.raises(ValueError, match="tentativa mais recente"):
        assess_cognition_analysis(
            database_path,
            FakeAssessmentProvider(),
            model="fake-model",
            action_id=action_id,
        )


def test_generic_confirmation_rejects_unregistered_assessment_type(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id, analysis_event_id, _ = _completed_analysis(database_path)
    assessment = create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
        criteria=({"description": "critério"},),
        status="ASSESSED",
        evidence_event_ids=(analysis_event_id,),
        observed={
            "assessment_type": "unknown.semantic",
            "verdict": "SATISFIED",
        },
        strength=2,
    )

    with pytest.raises(ValueError, match="assessment confirmável"):
        confirm_action_assessment(
            database_path,
            assessment_verification_id=assessment.id,
        )


def test_analysis_assessment_revalidates_finding_grounding(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    _, action_id, analysis_event_id, _ = _completed_analysis(database_path)

    import json
    import sqlite3

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE id = ?",
            (analysis_event_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[0]))
        payload["analysis"]["findings"][0]["evidence_event_ids"] = ["evt_inventado"]
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, separators=(",", ":")), analysis_event_id),
        )

    with pytest.raises(ValueError, match="sem grounding"):
        assess_cognition_analysis(
            database_path,
            FakeAssessmentProvider(),
            model="fake-model",
            action_id=action_id,
        )

    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    )
    assert results == ()


def test_analysis_assess_and_generic_confirmation_cli(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from simon.cli import main

    database_path, _ = initialize_storage(tmp_path)
    _, action_id, _, _ = _completed_analysis(database_path)
    provider = FakeAssessmentProvider("SATISFIED")
    monkeypatch.setattr("simon.cli.OllamaProvider", lambda **kwargs: provider)

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "analysis-assess",
            "--model",
            "fake-model",
            action_id,
        ]
    ) == 0
    assessment_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Veredito: SATISFIED" in assessment_output
    assert "Status persistido: ASSESSED" in assessment_output

    assessments = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    )
    assessment = next(result for result in assessments if result.status == "ASSESSED")

    assert main(
        [
            "--data-dir",
            str(tmp_path),
            "verification-confirm",
            assessment.id,
        ]
    ) == 0
    confirmation_output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Tipo: cognition.analyze.semantic" in confirmation_output
    assert "Status persistido: VERIFIED" in confirmation_output
