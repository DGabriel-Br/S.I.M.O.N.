from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from simon.actions import create_action, list_actions_for_plan, transition_action
from simon.cli import main
from simon.cognition_analysis import (
    AnalysisFinding,
    CognitionAnalysis,
    execute_next_cognition_analysis,
    retry_cognition_analysis,
)
from simon.events import Event, append_event, get_event
from simon.executive import decide_next
from simon.goals import Goal, insert_goal
from simon.model_provider import ModelProviderError, StructuredModelResult
from simon.operation_proposal import (
    find_current_cognition_analysis_retry_proposal,
    propose_cognition_analysis_retry,
)
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.user_turn import handle_user_turn
from simon.verification import create_verification_result


class FailingProvider:
    def list_models(self) -> tuple[str, ...]:
        return ("failing-model",)

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


class RecordingAnalysisProvider:
    def __init__(self, evidence_event_id: str) -> None:
        self.evidence_event_id = evidence_event_id
        self.models: list[str] = []

    def list_models(self) -> tuple[str, ...]:
        return ("model-a", "model-b", "proposal-model")

    def generate_structured[OutputT: BaseModel](
        self,
        *,
        model: str,
        prompt: str,
        response_model: type[OutputT],
        system: str | None = None,
        temperature: float = 0.0,
    ) -> StructuredModelResult[OutputT]:
        self.models.append(model)
        output = CognitionAnalysis(
            summary="A execução anterior fornece evidência suficiente para o diagnóstico.",
            findings=[
                AnalysisFinding(
                    statement="A evidência registrada mostra a falha observada.",
                    evidence_event_ids=[self.evidence_event_id],
                )
            ],
            uncertainties=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def _failed_analysis_state(database_path: Path) -> tuple[Goal, str, str, str, str]:
    goal = Goal.create(
        title="Diagnosticar execução",
        origin="USER",
        desired_state={"description": "A causa observável foi diagnosticada."},
        success_criteria=({"description": "Existe análise fundamentada."},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Observar execução anterior.",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "A execução foi observada.",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
            {
                "id": "step_02",
                "description": "Analisar a evidência observada.",
                "kind": "EPISTEMIC",
                "depends_on": ["step_01"],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "A causa observável foi identificada.",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
            },
        ),
    )

    prior = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="process.run",
        input_data={"verification": "A execução foi observada."},
    )
    transition_action(database_path, prior.id, "RUNNING")
    transition_action(
        database_path,
        prior.id,
        "COMPLETED",
        reported_result={"exit_code": 1},
    )
    evidence = Event.create(
        kind="process.execution.completed",
        source="tool",
        payload={
            "action_id": prior.id,
            "plan_id": plan.id,
            "step_id": "step_01",
            "exit_code": 1,
            "stdout": "",
            "stderr": "NameError: resultado",
        },
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=prior.id,
        criteria=({"description": "execução observada"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"exit_code": 1},
        strength=3,
    )

    failed = execute_next_cognition_analysis(
        database_path,
        FailingProvider(),
        model="initial-model",
        goal_id=goal.id,
    )
    assert failed.action.status == "FAILED"
    return goal, plan.id, prior.id, evidence.id, failed.action.id


def test_analysis_retry_proposal_freezes_model_and_current_evidence_without_retrying(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, _, evidence_id, failed_action_id = _failed_analysis_state(database_path)

    proposal = propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="proposal-model",
    )

    assert proposal.goal_id == goal.id
    assert proposal.plan_id == plan_id
    assert proposal.step_id == "step_02"
    assert proposal.retry_of_action_id == failed_action_id
    assert proposal.previous_status == "FAILED"
    assert proposal.model == "proposal-model"
    assert proposal.evidence_event_ids == (evidence_id,)
    assert len(list_actions_for_plan(database_path, plan_id)) == 2

    event = get_event(database_path, proposal.event.id)
    assert event is not None
    assert event.kind == "executive.operation.proposed"
    assert event.source == "system"
    assert event.payload["proposal_type"] == "analysis.retry"
    assert event.payload["operation"] == "analysis.retry"
    assert event.payload["model"] == "proposal-model"
    assert event.payload["evidence_event_ids"] == [evidence_id]

    decision = decide_next(database_path, goal_id=goal.id)
    current = find_current_cognition_analysis_retry_proposal(database_path, decision)
    assert current is not None
    assert current.event.id == proposal.event.id


def test_affirmative_turn_executes_only_current_analysis_retry_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, _, evidence_id, failed_action_id = _failed_analysis_state(database_path)
    proposal = propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="proposal-model",
    )
    provider = RecordingAnalysisProvider(evidence_id)

    receipt = handle_user_turn(
        database_path,
        "sim",
        goal_id=goal.id,
        provider=provider,
    )

    assert receipt.status == "ROUTED"
    assert receipt.intent == "AUTHORIZE"
    assert receipt.effect_type == "analysis.retry"
    assert receipt.routing_event.payload["proposal_event_id"] == proposal.event.id
    assert provider.models == ["proposal-model"]

    actions = list_actions_for_plan(database_path, plan_id)
    assert len(actions) == 3
    retry = actions[-1]
    assert retry.kind == "cognition.analyze"
    assert retry.status == "COMPLETED"
    assert retry.input_data["retry_of_action_id"] == failed_action_id
    assert retry.input_data["model"] == "proposal-model"
    assert retry.input_data["evidence_event_ids"] == [evidence_id]

    authorization_id = retry.input_data["retry_authorization_event_id"]
    assert isinstance(authorization_id, str)
    authorization = get_event(database_path, authorization_id)
    assert authorization is not None
    assert authorization.kind == "action.retry.authorized"
    assert authorization.source == "user"
    assert authorization.trace_id == receipt.turn_event.id
    assert authorization.payload["model"] == "proposal-model"
    assert authorization.payload["evidence_event_ids"] == [evidence_id]

    assert receipt.executive_receipt is not None
    assert receipt.executive_receipt.status == "MODEL_REQUIRED"
    assert receipt.executive_receipt.final_decision.operation == "analysis.assess"


def test_analysis_retry_requires_current_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, _, evidence_id, _ = _failed_analysis_state(database_path)

    receipt = handle_user_turn(
        database_path,
        "sim",
        goal_id=goal.id,
        provider=RecordingAnalysisProvider(evidence_id),
    )

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "operation_proposal_required"
    assert len(list_actions_for_plan(database_path, plan_id)) == 2


def test_analysis_retry_proposal_requires_provider_before_consuming_turn(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, _, _, failed_action_id = _failed_analysis_state(database_path)
    proposal = propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="proposal-model",
    )

    receipt = handle_user_turn(database_path, "sim", goal_id=goal.id)

    assert receipt.status == "UNSUPPORTED"
    assert receipt.routing_event.payload["reason_code"] == "analysis_retry_provider_required"
    assert len(list_actions_for_plan(database_path, plan_id)) == 2
    decision = decide_next(database_path, goal_id=goal.id)
    current = find_current_cognition_analysis_retry_proposal(database_path, decision)
    assert current is not None
    assert current.event.id == proposal.event.id


def test_latest_analysis_retry_proposal_supersedes_older_model(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, plan_id, _, evidence_id, failed_action_id = _failed_analysis_state(database_path)
    first = propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="model-a",
    )
    second = propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="model-b",
    )
    provider = RecordingAnalysisProvider(evidence_id)

    assert second.event.payload["supersedes_proposal_event_id"] == first.event.id

    receipt = handle_user_turn(
        database_path,
        "autorizo",
        goal_id=goal.id,
        provider=provider,
    )

    assert receipt.status == "ROUTED"
    assert receipt.routing_event.payload["proposal_event_id"] == second.event.id
    assert provider.models == ["model-b"]
    actions = list_actions_for_plan(database_path, plan_id)
    assert actions[-1].input_data["model"] == "model-b"


def test_analysis_retry_proposal_becomes_stale_when_verified_evidence_changes(
    tmp_path: Path,
) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    goal, _, prior_action_id, evidence_id, failed_action_id = _failed_analysis_state(database_path)
    proposal = propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="proposal-model",
    )
    old_decision = decide_next(database_path, goal_id=goal.id)
    assert find_current_cognition_analysis_retry_proposal(database_path, old_decision) is not None

    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=prior_action_id,
        criteria=({"description": "estado posterior divergente"},),
        status="FAILED",
        evidence_event_ids=(evidence_id,),
        observed={"reason": "evidência anterior invalidada"},
        strength=4,
    )

    assert proposal.evidence_event_ids == (evidence_id,)
    assert find_current_cognition_analysis_retry_proposal(database_path, old_decision) is None


def test_retry_executor_rejects_evidence_different_from_approved_proposal(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path / "data")
    _, plan_id, _, evidence_id, failed_action_id = _failed_analysis_state(database_path)
    provider = RecordingAnalysisProvider(evidence_id)

    with pytest.raises(ValueError, match="evidência verificada mudou"):
        retry_cognition_analysis(
            database_path,
            provider,
            model="proposal-model",
            action_id=failed_action_id,
            expected_evidence_event_ids=("evt_other",),
        )

    assert provider.models == []
    assert len(list_actions_for_plan(database_path, plan_id)) == 2


def test_analysis_retry_propose_cli_presents_model_and_evidence_without_retrying(
    tmp_path: Path,
    capsys: object,
) -> None:
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    _, plan_id, _, evidence_id, failed_action_id = _failed_analysis_state(database_path)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "analysis-retry-propose",
            "--model",
            "proposal-model",
            failed_action_id,
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Tipo: analysis.retry" in output
    assert f"Action anterior: {failed_action_id} (FAILED)" in output
    assert "Modelo: proposal-model" in output
    assert evidence_id in output
    assert "Nova tentativa realizada: não" in output
    assert "Autorização de retry registrada: não" in output
    assert len(list_actions_for_plan(database_path, plan_id)) == 2


def test_user_turn_cli_uses_model_frozen_in_analysis_retry_proposal(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    database_path, _ = initialize_storage(data_dir)
    goal, plan_id, _, evidence_id, failed_action_id = _failed_analysis_state(database_path)
    propose_cognition_analysis_retry(
        database_path,
        action_id=failed_action_id,
        model="proposal-model",
    )
    provider = RecordingAnalysisProvider(evidence_id)
    monkeypatch.setattr("simon.cli.OllamaProvider", lambda **_: provider)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "user-turn",
            "--goal-id",
            goal.id,
            "sim",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Efeito do gate: analysis.retry" in output
    assert "Parada: informe --model" in output
    assert provider.models == ["proposal-model"]
    actions = list_actions_for_plan(database_path, plan_id)
    assert actions[-1].input_data["model"] == "proposal-model"
