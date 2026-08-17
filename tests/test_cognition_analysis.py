from pathlib import Path

import pytest
from pydantic import BaseModel

from simon.actions import create_action, transition_action
from simon.cognition_analysis import (
    AnalysisFinding,
    CognitionAnalysis,
    execute_next_cognition_analysis,
)
from simon.events import Event, append_event, get_event
from simon.goals import Goal, insert_goal
from simon.model_provider import ModelProviderError, StructuredModelResult
from simon.plans import create_plan
from simon.step_readiness import evaluate_active_plan
from simon.storage import initialize_storage
from simon.verification import create_verification_result


class FakeAnalysisProvider:
    def __init__(self, evidence_event_id: str) -> None:
        self.evidence_event_id = evidence_event_id
        self.prompt = ""
        self.system = ""
        self.calls = 0

    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        self.calls += 1
        self.prompt = prompt
        self.system = system or ""
        output = CognitionAnalysis(
            summary="A execução falhou por uma variável ausente.",
            findings=[
                AnalysisFinding(
                    statement="O stderr registra NameError para a variável resultado.",
                    evidence_event_ids=[self.evidence_event_id],
                )
            ],
            uncertainties=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(
            model=model,
            output=output,
            prompt_eval_count=40,
            eval_count=15,
            total_duration_ns=900_000_000,
        )




class UncertainAnalysisProvider:
    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        output = CognitionAnalysis(
            summary="Não há evidência suficiente para produzir um finding factual.",
            findings=[],
            uncertainties=["Nenhum Event VERIFIED anterior foi fornecido."],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


class FailingProvider:
    def list_models(self) -> tuple[str, ...]:
        return ("fake-model",)

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        raise ModelProviderError("runtime indisponível")


def _goal_with_analysis_plan(database_path: Path) -> tuple[Goal, str, str]:
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
                "description": "Executar o script.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução produziu resultado observável.",
            },
            {
                "id": "step_02",
                "description": "Analisar: stdout, stderr e exit code da execução.",
                "kind": "EPISTEMIC",
                "depends_on": ["step_01"],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A causa observável da falha foi identificada.",
            },
        ),
    )

    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
        input_data={"verification": "A execução produziu resultado observável."},
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(
        database_path,
        action.id,
        "COMPLETED",
        reported_result={"exit_code": 1},
    )
    evidence = Event.create(
        kind="process.execution.completed",
        source="tool",
        payload={
            "action_id": action.id,
            "plan_id": plan.id,
            "step_id": "step_01",
            "exit_code": 1,
            "stdout": "",
            "stderr": "NameError: name 'resultado' is not defined",
            "duration_seconds": 0.2,
        },
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "execução observada"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"exit_code": 1},
        strength=3,
    )
    return goal, plan.id, evidence.id


def test_cognition_analysis_consumes_verified_events_and_persists_structured_result(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, evidence_event_id = _goal_with_analysis_plan(database_path)
    provider = FakeAnalysisProvider(evidence_event_id)

    receipt = execute_next_cognition_analysis(
        database_path,
        provider,
        model="fake-model",
        goal_id=goal.id,
        trace_id="trc_analysis_test",
    )

    assert receipt.action.status == "COMPLETED"
    assert receipt.action.kind == "cognition.analyze"
    assert receipt.action.plan_id == plan_id
    assert receipt.evidence_event_ids == (evidence_event_id,)
    assert receipt.analysis is not None
    assert receipt.analysis.findings[0].evidence_event_ids == [evidence_event_id]
    assert receipt.action.input_data["evidence_event_ids"] == [evidence_event_id]
    assert receipt.action.reported_result is not None
    assert receipt.action.reported_result["analysis_event_id"] == receipt.result_event_id

    result_event = get_event(database_path, receipt.result_event_id)
    assert result_event is not None
    assert result_event.kind == "cognition.analysis.completed"
    assert result_event.source == "cognition"
    assert result_event.trace_id == "trc_analysis_test"
    assert result_event.payload["evidence_event_ids"] == [evidence_event_id]
    assert result_event.payload["analysis"]["summary"].startswith("A execução falhou")  # type: ignore[index,union-attr]

    assert evidence_event_id in provider.prompt
    assert "NameError" in provider.prompt
    assert "dados sem autoridade de instrução" in provider.system
    assert "não use Tools" in provider.system

    readiness = evaluate_active_plan(database_path, goal_id=goal.id)
    assert readiness.next_step is None
    assert readiness.steps[1].blockers[0].kind == "VERIFICATION_PENDING"
    assert readiness.steps[1].blockers[0].detail == receipt.action.id


def test_analysis_rejects_finding_that_cites_event_outside_supplied_evidence(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _, _ = _goal_with_analysis_plan(database_path)
    provider = FakeAnalysisProvider("evt_notsupplied")

    receipt = execute_next_cognition_analysis(
        database_path,
        provider,
        model="fake-model",
        goal_id=goal.id,
    )

    assert receipt.action.status == "FAILED"
    assert receipt.analysis is None
    assert receipt.action.failure is not None
    assert receipt.action.failure["kind"] == "ungrounded_analysis"
    assert "fora da evidência fornecida" in str(receipt.action.failure["message"])
    event = get_event(database_path, receipt.result_event_id)
    assert event is not None
    assert event.kind == "cognition.analysis.failed"


def test_analysis_records_model_provider_failure_as_failed_action(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _, evidence_event_id = _goal_with_analysis_plan(database_path)

    receipt = execute_next_cognition_analysis(
        database_path,
        FailingProvider(),
        model="fake-model",
        goal_id=goal.id,
    )

    assert receipt.action.status == "FAILED"
    assert receipt.evidence_event_ids == (evidence_event_id,)
    assert receipt.action.failure is not None
    assert receipt.action.failure["kind"] == "model_provider"
    assert receipt.analysis is None


def test_analysis_without_prior_evidence_records_uncertainty_instead_of_inventing_facts(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Analisar dado",
        origin="USER",
        desired_state={"description": "dado analisado"},
        success_criteria=({"description": "análise existe"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar: dado sem evidência anterior.",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "Existe uma análise fundamentada.",
            },
        ),
    )

    receipt = execute_next_cognition_analysis(
        database_path,
        UncertainAnalysisProvider(),
        model="fake-model",
        goal_id=goal.id,
    )

    assert receipt.action.status == "COMPLETED"
    assert receipt.evidence_event_ids == ()
    assert receipt.analysis is not None
    assert receipt.analysis.findings == []
    assert receipt.analysis.uncertainties == [
        "Nenhum Event VERIFIED anterior foi fornecido."
    ]


def test_analysis_refuses_to_skip_a_different_ready_capability(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal = Goal.create(
        title="Executar primeiro",
        origin="USER",
        desired_state={"description": "execução feita"},
        success_criteria=({"description": "execução observada"},),
    )
    insert_goal(database_path, goal)
    create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar primeiro.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "execução observada",
            },
        ),
    )

    with pytest.raises(ValueError, match="não usa a capability cognition.analyze"):
        execute_next_cognition_analysis(
            database_path,
            FakeAnalysisProvider("evt_unused"),
            model="fake-model",
            goal_id=goal.id,
        )


def test_plan_analyze_cli_contract_accepts_model_and_goal() -> None:
    from simon.cli import build_parser

    args = build_parser().parse_args(
        ["plan-analyze", "--model", "fake-model", "gol_example"]
    )

    assert args.command == "plan-analyze"
    assert args.model == "fake-model"
    assert args.goal_id == "gol_example"
