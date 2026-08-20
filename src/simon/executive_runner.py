from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.cognition_analysis import execute_next_cognition_analysis
from simon.cognition_analysis_verification import assess_cognition_analysis
from simon.executive import ExecutiveDecision, ExecutiveOperation, decide_next
from simon.file_patch_verification import verify_file_patch_state
from simon.goal_verification import assess_goal_outcome
from simon.model_provider import ModelProvider, ModelProviderError
from simon.plan_completion import complete_verified_plan
from simon.plan_intake import materialize_plan_proposal
from simon.plan_proposal import PlanProposalGateError, propose_plan_for_goal
from simon.process_verification import verify_process_run_execution
from simon.user_ask import dispatch_next_user_ask, retry_user_ask
from simon.user_ask_verification import assess_user_ask_response

ExecutiveRunStatus = Literal[
    "EXECUTED",
    "STOPPED",
    "MODEL_REQUIRED",
    "FAILED",
]


@dataclass(frozen=True, slots=True)
class ExecutiveRunReceipt:
    status: ExecutiveRunStatus
    decision: ExecutiveDecision
    executed_operation: ExecutiveOperation | None = None
    result_type: str | None = None
    result_id: str | None = None
    next_decision: ExecutiveDecision | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status == "EXECUTED":
            if (
                self.executed_operation is None
                or self.result_type is None
                or self.result_id is None
            ):
                raise ValueError("EXECUTED exige operação e referência do resultado")
            if self.next_decision is None:
                raise ValueError("EXECUTED exige reconstrução da próxima decisão")
        elif self.executed_operation is not None:
            raise ValueError(f"{self.status} não pode declarar operação executada")
        if self.status == "FAILED" and not self.error:
            raise ValueError("FAILED exige mensagem de erro")


def run_executive_once(
    database_path: Path,
    *,
    goal_id: str | None = None,
    provider: ModelProvider | None = None,
    model: str | None = None,
) -> ExecutiveRunReceipt:
    """Executa no máximo uma decisão PROCEED e reavalia o estado sem continuar o ciclo."""
    decision = decide_next(database_path, goal_id=goal_id)
    if decision.outcome != "PROCEED":
        return ExecutiveRunReceipt(status="STOPPED", decision=decision)

    if decision.requires_model and (provider is None or model is None or not model.strip()):
        return ExecutiveRunReceipt(status="MODEL_REQUIRED", decision=decision)

    try:
        result_type, result_id = _execute_safe_operation(
            database_path,
            decision,
            provider=provider,
            model=model,
        )
    except (
        ModelProviderError,
        PlanProposalGateError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        return ExecutiveRunReceipt(
            status="FAILED",
            decision=decision,
            error=str(exc),
        )

    next_decision = decide_next(database_path, goal_id=decision.goal_id)
    return ExecutiveRunReceipt(
        status="EXECUTED",
        decision=decision,
        executed_operation=decision.operation,
        result_type=result_type,
        result_id=result_id,
        next_decision=next_decision,
    )


def _execute_safe_operation(
    database_path: Path,
    decision: ExecutiveDecision,
    *,
    provider: ModelProvider | None,
    model: str | None,
) -> tuple[str, str]:
    operation = decision.operation
    goal_id = _required(decision.goal_id, "goal_id", operation)

    if operation == "plan.propose":
        selected_provider, selected_model = _required_model(provider, model, operation)
        proposal_receipt = propose_plan_for_goal(
            database_path,
            selected_provider,
            model=selected_model,
            goal_id=goal_id,
        )
        return "event", proposal_receipt.proposal_event.id

    if operation == "plan.materialize":
        proposal_event_id = _required(decision.proposal_event_id, "proposal_event_id", operation)
        materialization_receipt = materialize_plan_proposal(database_path, proposal_event_id)
        return "plan", materialization_receipt.plan.id

    if operation == "plan.ask":
        dispatch = dispatch_next_user_ask(database_path, goal_id=goal_id)
        return "action", dispatch.action.id

    if operation == "plan.analyze":
        selected_provider, selected_model = _required_model(provider, model, operation)
        analysis_receipt = execute_next_cognition_analysis(
            database_path,
            selected_provider,
            model=selected_model,
            goal_id=goal_id,
        )
        return "action", analysis_receipt.action.id

    if operation == "process.verify":
        action_id = _required(decision.action_id, "action_id", operation)
        process_verification_receipt = verify_process_run_execution(
            database_path,
            action_id=action_id,
        )
        return "verification", process_verification_receipt.verification.id

    if operation == "file.verify":
        action_id = _required(decision.action_id, "action_id", operation)
        file_verification_receipt = verify_file_patch_state(
            database_path,
            action_id=action_id,
        )
        return "verification", file_verification_receipt.verification.id

    if operation == "action.assess":
        selected_provider, selected_model = _required_model(provider, model, operation)
        action_id = _required(decision.action_id, "action_id", operation)
        user_assessment_receipt = assess_user_ask_response(
            database_path,
            selected_provider,
            model=selected_model,
            action_id=action_id,
        )
        return "verification", user_assessment_receipt.verification.id

    if operation == "analysis.assess":
        selected_provider, selected_model = _required_model(provider, model, operation)
        action_id = _required(decision.action_id, "action_id", operation)
        analysis_assessment_receipt = assess_cognition_analysis(
            database_path,
            selected_provider,
            model=selected_model,
            action_id=action_id,
        )
        return "verification", analysis_assessment_receipt.verification.id

    if operation == "action.retry":
        action_id = _required(decision.action_id, "action_id", operation)
        retry_dispatch = retry_user_ask(database_path, action_id=action_id)
        return "action", retry_dispatch.action.id

    if operation == "plan.complete":
        completion_receipt = complete_verified_plan(database_path, goal_id=goal_id)
        return "plan", completion_receipt.plan.id

    if operation == "goal.assess":
        selected_provider, selected_model = _required_model(provider, model, operation)
        goal_assessment_receipt = assess_goal_outcome(
            database_path,
            selected_provider,
            model=selected_model,
            goal_id=goal_id,
        )
        return "verification", goal_assessment_receipt.verification.id

    raise RuntimeError(f"operação PROCEED não é executável pelo runner seguro: {operation}")


def _required_model(
    provider: ModelProvider | None,
    model: str | None,
    operation: ExecutiveOperation | None,
) -> tuple[ModelProvider, str]:
    if provider is None or model is None or not model.strip():
        raise ValueError(f"operação {operation} exige provider e model")
    return provider, model.strip()


def _required(
    value: str | None,
    field: str,
    operation: ExecutiveOperation | None,
) -> str:
    if value is None or not value.strip():
        raise RuntimeError(f"decisão {operation} não possui {field}")
    return value.strip()
