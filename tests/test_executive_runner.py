from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from simon.actions import create_action, list_actions_for_plan, transition_action
from simon.cli import main
from simon.cognition_analysis import AnalysisFinding, CognitionAnalysis
from simon.events import Event, append_event
from simon.executive import decide_next
from simon.executive_runner import run_executive_once
from simon.goals import Goal, insert_goal
from simon.model_provider import StructuredModelResult
from simon.planning import PlanIntentDraft, PlanIntentStep
from simon.plans import create_plan, list_plans_for_goal
from simon.storage import initialize_storage
from simon.verification import create_verification_result


class PlanningProvider:
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
        output = PlanIntentDraft(
            summary="Coletar a evidência necessária antes de prosseguir.",
            steps=[
                PlanIntentStep(
                    subject="mensagem de erro observada pelo usuário",
                    role="COLLECT",
                    source="USER",
                    verification="o usuário forneceu a mensagem de erro",
                )
            ],
            open_questions=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


class AnalysisProvider:
    def __init__(self, evidence_event_id: str) -> None:
        self.evidence_event_id = evidence_event_id

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
            summary="A evidência foi analisada.",
            findings=[
                AnalysisFinding(
                    statement="O Event anterior contém o resultado observado.",
                    evidence_event_ids=[self.evidence_event_id],
                )
            ],
            uncertainties=[],
        )
        assert isinstance(output, response_model)
        return StructuredModelResult(model=model, output=output)


def _goal(database_path: Path, title: str = "Corrigir script") -> Goal:
    goal = Goal.create(
        title=title,
        origin="USER",
        desired_state={"description": "O script funciona novamente."},
        success_criteria=({"description": "O problema foi corrigido."},),
    )
    insert_goal(database_path, goal)
    return goal


def test_runner_does_not_cross_operation_authorization_gate(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "execução observada",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
    )

    receipt = run_executive_once(database_path, goal_id=goal.id)

    assert receipt.status == "STOPPED"
    assert receipt.decision.outcome == "NEEDS_OPERATION_AUTHORIZATION"
    assert receipt.decision.operation == "plan.run"
    assert list_actions_for_plan(database_path, plan.id) == ()


def test_runner_requires_model_without_mutating_cognitive_step(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Analisar a evidência",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "análise concluída",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
            },
        ),
    )

    receipt = run_executive_once(database_path, goal_id=goal.id)

    assert receipt.status == "MODEL_REQUIRED"
    assert receipt.decision.operation == "plan.analyze"
    assert list_actions_for_plan(database_path, plan.id) == ()


def test_runner_proposes_then_materializes_in_separate_cycles(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    provider = PlanningProvider()

    first = run_executive_once(
        database_path,
        goal_id=goal.id,
        provider=provider,
        model="fake-model",
    )

    assert first.status == "EXECUTED"
    assert first.executed_operation == "plan.propose"
    assert first.result_type == "event"
    assert list_plans_for_goal(database_path, goal.id) == ()
    assert first.next_decision is not None
    assert first.next_decision.operation == "plan.materialize"
    assert first.next_decision.proposal_event_id == first.result_id

    second = run_executive_once(database_path, goal_id=goal.id)

    assert second.status == "EXECUTED"
    assert second.executed_operation == "plan.materialize"
    assert second.result_type == "plan"
    plans = list_plans_for_goal(database_path, goal.id)
    assert len(plans) == 1
    assert plans[0].id == second.result_id
    assert list_actions_for_plan(database_path, plans[0].id) == ()
    assert second.next_decision is not None
    assert second.next_decision.operation == "plan.ask"


def test_runner_executes_only_one_safe_user_ask_transition(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Informe a mensagem de erro",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "o usuário forneceu a mensagem de erro",
                "intent_role": "COLLECT",
                "intent_actor": "USER",
            },
        ),
    )

    receipt = run_executive_once(database_path, goal_id=goal.id)

    assert receipt.status == "EXECUTED"
    assert receipt.executed_operation == "plan.ask"
    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 1
    assert actions[0].status == "WAITING"
    assert receipt.next_decision is not None
    assert receipt.next_decision.outcome == "NEEDS_USER_INPUT"
    assert receipt.next_decision.operation == "action.answer"


def test_runner_completes_plan_but_does_not_assess_goal_in_same_cycle(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Observar resultado",
                "kind": "EPISTEMIC",
                "depends_on": [],
                "preconditions": [],
                "capability": "user.ask",
                "verification": "resultado observado",
                "intent_role": "COLLECT",
                "intent_actor": "USER",
            },
        ),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_01",
        kind="user.ask",
    )
    transition_action(database_path, action.id, "RUNNING")
    transition_action(database_path, action.id, "COMPLETED", reported_result={"ok": True})
    evidence = Event.create(
        kind="test.evidence",
        source="tool",
        payload={"ok": True},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "resultado observado"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"ok": True},
        strength=3,
    )

    receipt = run_executive_once(database_path, goal_id=goal.id)

    assert receipt.status == "EXECUTED"
    assert receipt.executed_operation == "plan.complete"
    assert receipt.result_id == plan.id
    assert receipt.next_decision is not None
    assert receipt.next_decision.operation == "goal.assess"
    assert receipt.next_decision.requires_model is True
    # A segunda operação não foi atravessada no mesmo ciclo.
    assert decide_next(database_path, goal_id=goal.id).operation == "goal.assess"


def test_runner_executes_one_cognition_step_and_stops_before_assessment(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Observar a execução",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "resultado da execução observado",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
            {
                "id": "step_02",
                "description": "Analisar o resultado observado",
                "kind": "EPISTEMIC",
                "depends_on": ["step_01"],
                "preconditions": [],
                "capability": "cognition.analyze",
                "verification": "a evidência foi analisada",
                "intent_role": "ANALYZE",
                "intent_actor": "SIMON",
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
    transition_action(database_path, action.id, "COMPLETED", reported_result={"exit_code": 1})
    evidence = Event.create(
        kind="process.execution.completed",
        source="tool",
        payload={"action_id": action.id, "exit_code": 1, "stderr": "falha observada"},
        goal_id=goal.id,
    )
    append_event(database_path, evidence)
    create_verification_result(
        database_path,
        subject_type="ACTION",
        subject_id=action.id,
        criteria=({"description": "resultado da execução observado"},),
        status="VERIFIED",
        evidence_event_ids=(evidence.id,),
        observed={"exit_code": 1},
        strength=3,
    )

    receipt = run_executive_once(
        database_path,
        goal_id=goal.id,
        provider=AnalysisProvider(evidence.id),
        model="fake-model",
    )

    assert receipt.status == "EXECUTED"
    assert receipt.executed_operation == "plan.analyze"
    assert receipt.result_type == "action"
    actions = list_actions_for_plan(database_path, plan.id)
    assert len(actions) == 2
    assert actions[-1].id == receipt.result_id
    assert actions[-1].status == "COMPLETED"
    assert receipt.next_decision is not None
    assert receipt.next_decision.operation == "analysis.assess"
    assert receipt.next_decision.requires_model is True


def test_executive_step_cli_stops_at_operation_authorization(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = _goal(database_path)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=(
            {
                "id": "step_01",
                "description": "Executar o script",
                "kind": "WORLD",
                "depends_on": [],
                "preconditions": [],
                "capability": "process.run",
                "verification": "execução observada",
                "intent_role": "EXECUTE",
                "intent_actor": "SIMON",
            },
        ),
    )

    exit_code = main(["--data-dir", str(tmp_path), "executive-step", goal.id])

    assert exit_code == 0
    assert list_actions_for_plan(database_path, plan.id) == ()
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Executive runner: STOPPED" in output
    assert "NEEDS_OPERATION_AUTHORIZATION" in output
    assert "Operação: plan.run" in output
