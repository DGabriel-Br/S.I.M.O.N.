from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from simon.assessment_confirmation import confirm_action_assessment
from simon.cognition_analysis import retry_cognition_analysis
from simon.events import Event, append_event
from simon.executive import ExecutiveDecision, ExecutiveGoalCandidate, decide_next
from simon.executive_runner import ExecutiveContinueReceipt, run_executive_until_gate
from simon.file_patch import execute_next_file_patch, retry_file_patch
from simon.goal_completion import complete_goal_from_assessment
from simon.goal_focus import select_goal_focus
from simon.model_provider import ModelProvider
from simon.operation_materialization import (
    AnalysisRetryMaterialization,
    FilePatchCommandMaterialization,
    OperationMaterializationInputError,
    ProcessCommandMaterialization,
    parse_analysis_retry_turn,
    parse_file_patch_turn,
    parse_process_command_turn,
)
from simon.operation_proposal import (
    find_current_cognition_analysis_retry_proposal,
    find_current_file_patch_proposal,
    find_current_file_patch_retry_proposal,
    find_current_process_retry_proposal,
    find_current_process_run_proposal,
    propose_cognition_analysis_retry,
    propose_file_patch,
    propose_file_patch_retry,
    propose_process_retry,
    propose_process_run,
)
from simon.process_execution import execute_next_process_run, retry_process_run
from simon.user_ask import answer_user_ask

UserTurnIntent = Literal["CONTINUE", "SELECT", "ANSWER", "CONFIRM", "AUTHORIZE", "MATERIALIZE"]
UserTurnStatus = Literal["ROUTED", "UNSUPPORTED", "FAILED"]
UserTurnEffectType = Literal[
    "goal.focus",
    "user.response",
    "verification.confirmed",
    "goal.completed",
    "process.run",
    "file.patch",
    "process.retry",
    "file.retry",
    "analysis.retry",
    "operation.proposal",
]

_CONTINUE_UTTERANCES = {
    "continue",
    "continue esse goal",
    "continue este goal",
    "continue o goal",
    "continue com esse goal",
    "continue com este goal",
    "continue com o goal",
    "continue esse objetivo",
    "continue este objetivo",
    "continue o objetivo",
    "continue com esse objetivo",
    "continue com este objetivo",
    "continue com o objetivo",
}

_CONFIRM_UTTERANCES = {
    "sim",
    "confirmo",
    "confirmado",
    "sim confirmo",
    "pode confirmar",
}

_AUTHORIZE_UTTERANCES = {
    "sim",
    "autorizo",
    "pode executar",
    "pode rodar",
    "sim pode executar",
    "pode alterar",
    "pode aplicar",
    "pode modificar",
}


@dataclass(frozen=True, slots=True)
class UserTurnReceipt:
    status: UserTurnStatus
    turn_event: Event
    intent: UserTurnIntent | None
    routing_event: Event
    executive_receipt: ExecutiveContinueReceipt | None = None
    effect_type: UserTurnEffectType | None = None
    effect_id: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status == "ROUTED" and (self.intent is None or self.executive_receipt is None):
            raise ValueError("ROUTED exige intent e resultado do Executive")
        if self.status == "ROUTED" and self.error is not None:
            raise ValueError("ROUTED não pode declarar erro")
        if self.status != "ROUTED" and self.executive_receipt is not None:
            raise ValueError(f"{self.status} não pode declarar resultado do Executive")
        if self.status == "UNSUPPORTED" and self.intent is not None:
            raise ValueError("UNSUPPORTED não pode declarar intent")
        if self.status == "UNSUPPORTED" and self.error is not None:
            raise ValueError("UNSUPPORTED não pode declarar erro")
        if self.status == "FAILED" and not self.error:
            raise ValueError("FAILED exige mensagem de erro")
        if (self.effect_type is None) != (self.effect_id is None):
            raise ValueError("effect_type e effect_id devem ser declarados juntos")
        if self.status != "ROUTED" and self.effect_type is not None:
            raise ValueError(f"{self.status} não pode declarar efeito de gate")
        if self.intent == "CONTINUE" and self.effect_type is not None:
            raise ValueError("CONTINUE não pode declarar efeito de gate")
        if (
            self.status == "ROUTED"
            and self.intent in {"SELECT", "ANSWER", "CONFIRM", "AUTHORIZE", "MATERIALIZE"}
            and self.effect_type is None
        ):
            raise ValueError(f"{self.intent} exige efeito de gate persistido")


def handle_user_turn(
    database_path: Path,
    text: str,
    *,
    goal_id: str | None = None,
    provider: ModelProvider | None = None,
    model: str | None = None,
    max_transitions: int = 32,
    working_directory: Path | None = None,
) -> UserTurnReceipt:
    """Registra um turno humano e aplica somente o significado permitido pelo gate atual."""
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("turno do usuário não pode ser vazio")
    if max_transitions <= 0:
        raise ValueError("max_transitions deve ser maior que zero")

    turn_event = Event.create(
        kind="user.turn.received",
        source="user",
        payload={
            "text": normalized_text,
            "requested_goal_id": goal_id,
            "foreground_working_directory": (
                str(working_directory.resolve()) if working_directory is not None else None
            ),
        },
        goal_id=goal_id,
    )
    append_event(database_path, turn_event)

    intent = interpret_user_turn_intent(normalized_text)
    if intent == "CONTINUE":
        return _route_continue(
            database_path,
            turn_event=turn_event,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    try:
        decision = decide_next(database_path, goal_id=goal_id)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent=None,
            goal_id=goal_id,
            error=str(exc),
            reason_code="gate_lookup_failed",
        )

    if decision.outcome == "NEEDS_GOAL_SELECTION":
        return _route_goal_selection(
            database_path,
            turn_event=turn_event,
            decision=decision,
            text=normalized_text,
        )

    if decision.outcome == "NEEDS_USER_INPUT" and decision.operation == "action.answer":
        return _route_user_answer(
            database_path,
            turn_event=turn_event,
            decision=decision,
            response=normalized_text,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    if (
        decision.outcome == "NEEDS_USER_CONFIRMATION"
        and not _is_explicit_confirmation(normalized_text)
    ):
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=decision.goal_id or goal_id,
            reason_code="explicit_confirmation_required",
            current_decision=decision,
        )
    if decision.outcome == "NEEDS_USER_CONFIRMATION":
        return _route_confirmation(
            database_path,
            turn_event=turn_event,
            decision=decision,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    if decision.outcome == "NEEDS_OPERATION_AUTHORIZATION":
        materialized = _route_operation_materialization_turn(
            database_path,
            turn_event=turn_event,
            decision=decision,
            text=normalized_text,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
            working_directory=working_directory,
        )
        if materialized is not None:
            return materialized
        return _route_operation_authorization_turn(
            database_path,
            turn_event=turn_event,
            decision=decision,
            text=normalized_text,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )

    return _unsupported_turn(
        database_path,
        turn_event=turn_event,
        goal_id=decision.goal_id or goal_id,
        reason_code="unsupported_intent",
        current_decision=decision,
    )


def interpret_user_turn_intent(text: str) -> UserTurnIntent | None:
    normalized = _normalize_turn_text(text)
    if normalized in _CONTINUE_UTTERANCES:
        return "CONTINUE"
    return None


def _route_goal_selection(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    text: str,
) -> UserTurnReceipt:
    selected_goal_id = _resolve_goal_selection(text, decision.goal_candidates)
    if selected_goal_id is None:
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=None,
            reason_code="goal_selection_not_resolved",
            current_decision=decision,
        )

    try:
        selected_decision = decide_next(database_path, goal_id=selected_goal_id)
        focus = select_goal_focus(
            database_path,
            goal_id=selected_goal_id,
            trace_id=turn_event.id,
            selection_text=text,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="SELECT",
            goal_id=selected_goal_id,
            error=str(exc),
            reason_code="goal_selection_routing_failed",
            current_decision=decision,
        )

    executive_receipt = ExecutiveContinueReceipt(
        status="STOPPED",
        initial_decision=selected_decision,
        final_decision=selected_decision,
    )
    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="SELECT",
        executive_receipt=executive_receipt,
        authority_scope="FOREGROUND_GOAL_SELECTION_ONLY",
        goal_id=selected_goal_id,
        current_decision=decision,
        effect_type="goal.focus",
        effect_id=focus.event.id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="SELECT",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type="goal.focus",
        effect_id=focus.event.id,
    )


def _resolve_goal_selection(
    text: str,
    candidates: tuple[ExecutiveGoalCandidate, ...],
) -> str | None:
    if not candidates:
        return None

    normalized = _normalize_turn_text(text)
    ordinal_index = _goal_selection_ordinal_index(normalized)
    if ordinal_index is not None:
        if 0 <= ordinal_index < len(candidates):
            return candidates[ordinal_index].goal_id
        return None

    matching_goal_ids = {
        candidate.goal_id
        for candidate in candidates
        if normalized in _goal_title_selection_phrases(candidate.title)
    }
    if len(matching_goal_ids) == 1:
        return next(iter(matching_goal_ids))
    return None


def _goal_selection_ordinal_index(normalized: str) -> int | None:
    ordinal_words = {
        "primeiro": 0,
        "segundo": 1,
        "terceiro": 2,
        "quarto": 3,
        "quinto": 4,
        "sexto": 5,
        "setimo": 6,
        "oitavo": 7,
        "nono": 8,
        "decimo": 9,
    }
    wrappers = (
        "{}",
        "o {}",
        "goal {}",
        "objetivo {}",
        "escolho {}",
        "escolho o {}",
        "selecione {}",
        "selecione o {}",
        "quero {}",
        "quero o {}",
        "use {}",
        "use o {}",
    )
    for word, index in ordinal_words.items():
        if any(normalized == pattern.format(word) for pattern in wrappers):
            return index

    numeric_pattern = (
        r"(?:(?:o|goal|objetivo|escolho(?: o)?|selecione(?: o)?|quero(?: o)?|use(?: o)?) )?"
        r"(\d{1,3})(?:o)?"
    )
    numeric_match = re.fullmatch(numeric_pattern, normalized)
    if numeric_match is None:
        return None
    return int(numeric_match.group(1)) - 1


def _goal_title_selection_phrases(title: str) -> set[str]:
    normalized_title = _normalize_turn_text(title)
    return {
        normalized_title,
        f"goal {normalized_title}",
        f"objetivo {normalized_title}",
        f"o goal {normalized_title}",
        f"o objetivo {normalized_title}",
        f"escolho {normalized_title}",
        f"escolho o goal {normalized_title}",
        f"escolho o objetivo {normalized_title}",
        f"selecione {normalized_title}",
        f"selecione o goal {normalized_title}",
        f"selecione o objetivo {normalized_title}",
        f"quero {normalized_title}",
        f"quero o goal {normalized_title}",
        f"quero o objetivo {normalized_title}",
        f"use {normalized_title}",
        f"use o goal {normalized_title}",
        f"use o objetivo {normalized_title}",
    }


def _route_continue(
    database_path: Path,
    *,
    turn_event: Event,
    goal_id: str | None,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    try:
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="CONTINUE",
            goal_id=goal_id,
            error=str(exc),
            reason_code="continue_routing_failed",
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="CONTINUE",
        executive_receipt=executive_receipt,
        authority_scope="EXECUTIVE_SAFE_CONTINUATION",
        goal_id=executive_receipt.final_decision.goal_id or goal_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="CONTINUE",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
    )


def _route_user_answer(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    response: str,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    action_id = _required_decision_value(decision.action_id, "action_id", decision)
    goal_id = _required_decision_value(decision.goal_id, "goal_id", decision)
    try:
        answer = answer_user_ask(
            database_path,
            action_id=action_id,
            response=response,
            trace_id=turn_event.id,
        )
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="ANSWER",
            goal_id=goal_id,
            error=str(exc),
            reason_code="user_answer_routing_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="ANSWER",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_USER_INPUT_GATE_ONLY",
        goal_id=goal_id,
        current_decision=decision,
        effect_type="user.response",
        effect_id=answer.response_event_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="ANSWER",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type="user.response",
        effect_id=answer.response_event_id,
    )


def _route_confirmation(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    verification_id = _required_decision_value(
        decision.verification_id,
        "verification_id",
        decision,
    )
    goal_id = _required_decision_value(decision.goal_id, "goal_id", decision)

    try:
        if decision.operation == "verification.confirm":
            confirmation = confirm_action_assessment(
                database_path,
                assessment_verification_id=verification_id,
                trace_id=turn_event.id,
            )
            effect_type: UserTurnEffectType = "verification.confirmed"
            effect_id = confirmation.verification.id
        elif decision.operation == "goal.complete":
            completion = complete_goal_from_assessment(
                database_path,
                assessment_verification_id=verification_id,
                trace_id=turn_event.id,
            )
            effect_type = "goal.completed"
            effect_id = completion.goal.id
        else:
            raise RuntimeError(
                "gate NEEDS_USER_CONFIRMATION não possui operação confirmável conhecida: "
                f"{decision.operation}"
            )

        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="CONFIRM",
            goal_id=goal_id,
            error=str(exc),
            reason_code="confirmation_routing_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="CONFIRM",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_CONFIRMATION_GATE_ONLY",
        goal_id=goal_id,
        current_decision=decision,
        effect_type=effect_type,
        effect_id=effect_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="CONFIRM",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type=effect_type,
        effect_id=effect_id,
    )


def _route_operation_materialization_turn(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    text: str,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
    working_directory: Path | None,
) -> UserTurnReceipt | None:
    process_materialization: ProcessCommandMaterialization | None = None
    file_patch_materialization: FilePatchCommandMaterialization | None = None
    analysis_retry_materialization: AnalysisRetryMaterialization | None = None
    try:
        if decision.operation in {"plan.run", "process.retry"}:
            process_materialization = parse_process_command_turn(
                text,
                working_directory=working_directory,
            )
            if process_materialization is None:
                return None
        elif decision.operation in {"plan.patch", "file.retry"}:
            file_patch_materialization = parse_file_patch_turn(
                text,
                working_directory=working_directory,
            )
            if file_patch_materialization is None:
                return None
        elif decision.operation == "analysis.retry":
            analysis_retry_materialization = parse_analysis_retry_turn(text)
            if analysis_retry_materialization is None:
                return None
        else:
            return None
    except OperationMaterializationInputError as exc:
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=decision.goal_id,
            reason_code=exc.reason_code,
            current_decision=decision,
        )

    goal_id = _required_decision_value(decision.goal_id, "goal_id", decision)
    try:
        if decision.operation == "plan.run" and decision.capability == "process.run":
            assert process_materialization is not None
            proposal = propose_process_run(
                database_path,
                goal_id=goal_id,
                request=process_materialization.request,
                trace_id=turn_event.id,
            )
            proposal_event_id = proposal.event.id
        elif decision.operation == "process.retry":
            assert process_materialization is not None
            action_id = _required_decision_value(decision.action_id, "action_id", decision)
            retry_proposal = propose_process_retry(
                database_path,
                action_id=action_id,
                request=process_materialization.request,
                trace_id=turn_event.id,
            )
            proposal_event_id = retry_proposal.event.id
        elif decision.operation == "plan.patch" and decision.capability == "file.patch":
            assert file_patch_materialization is not None
            patch_proposal = propose_file_patch(
                database_path,
                goal_id=goal_id,
                request=file_patch_materialization.request,
                trace_id=turn_event.id,
            )
            proposal_event_id = patch_proposal.event.id
        elif decision.operation == "file.retry":
            assert file_patch_materialization is not None
            action_id = _required_decision_value(decision.action_id, "action_id", decision)
            patch_retry_proposal = propose_file_patch_retry(
                database_path,
                action_id=action_id,
                request=file_patch_materialization.request,
                trace_id=turn_event.id,
            )
            proposal_event_id = patch_retry_proposal.event.id
        elif decision.operation == "analysis.retry":
            assert analysis_retry_materialization is not None
            action_id = _required_decision_value(decision.action_id, "action_id", decision)
            analysis_retry_proposal = propose_cognition_analysis_retry(
                database_path,
                action_id=action_id,
                model=analysis_retry_materialization.model,
                trace_id=turn_event.id,
            )
            proposal_event_id = analysis_retry_proposal.event.id
        else:
            return None

        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="MATERIALIZE",
            goal_id=goal_id,
            error=str(exc),
            reason_code="operation_materialization_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="MATERIALIZE",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_OPERATION_GATE_MATERIALIZATION_ONLY",
        goal_id=goal_id,
        current_decision=decision,
        effect_type="operation.proposal",
        effect_id=proposal_event_id,
        proposal_event_id=proposal_event_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="MATERIALIZE",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type="operation.proposal",
        effect_id=proposal_event_id,
    )


def _route_operation_authorization_turn(
    database_path: Path,
    *,
    turn_event: Event,
    decision: ExecutiveDecision,
    text: str,
    provider: ModelProvider | None,
    model: str | None,
    max_transitions: int,
) -> UserTurnReceipt:
    goal_id = decision.goal_id
    if not _is_explicit_operation_authorization(text):
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=goal_id,
            reason_code="explicit_operation_authorization_required",
            current_decision=decision,
        )

    if decision.operation == "plan.run" and decision.capability == "process.run":
        process_proposal = find_current_process_run_proposal(database_path, decision)
        if process_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        proposal_goal_id = process_proposal.goal_id
        proposal_event_id = process_proposal.event.id
        try:
            process_execution = execute_next_process_run(
                database_path,
                goal_id=proposal_goal_id,
                request=process_proposal.request,
                trace_id=turn_event.id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type: UserTurnEffectType = "process.run"
        effect_id = process_execution.action.id
    elif decision.operation == "plan.patch" and decision.capability == "file.patch":
        patch_proposal = find_current_file_patch_proposal(database_path, decision)
        if patch_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        proposal_goal_id = patch_proposal.goal_id
        proposal_event_id = patch_proposal.event.id
        try:
            patch_execution = execute_next_file_patch(
                database_path,
                goal_id=proposal_goal_id,
                request=patch_proposal.request,
                trace_id=turn_event.id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type = "file.patch"
        effect_id = patch_execution.action.id
    elif decision.operation == "process.retry":
        process_retry_proposal = find_current_process_retry_proposal(database_path, decision)
        if process_retry_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        proposal_goal_id = process_retry_proposal.goal_id
        proposal_event_id = process_retry_proposal.event.id
        try:
            process_retry_execution = retry_process_run(
                database_path,
                action_id=process_retry_proposal.retry_of_action_id,
                request=process_retry_proposal.request,
                trace_id=turn_event.id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type = "process.retry"
        effect_id = process_retry_execution.action.id
    elif decision.operation == "file.retry":
        file_retry_proposal = find_current_file_patch_retry_proposal(database_path, decision)
        if file_retry_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        proposal_goal_id = file_retry_proposal.goal_id
        proposal_event_id = file_retry_proposal.event.id
        try:
            file_retry_execution = retry_file_patch(
                database_path,
                action_id=file_retry_proposal.retry_of_action_id,
                request=file_retry_proposal.request,
                trace_id=turn_event.id,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type = "file.retry"
        effect_id = file_retry_execution.action.id
    elif decision.operation == "analysis.retry":
        analysis_retry_proposal = find_current_cognition_analysis_retry_proposal(
            database_path,
            decision,
        )
        if analysis_retry_proposal is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="operation_proposal_required",
                current_decision=decision,
            )
        if provider is None:
            return _unsupported_turn(
                database_path,
                turn_event=turn_event,
                goal_id=goal_id,
                reason_code="analysis_retry_provider_required",
                current_decision=decision,
            )
        proposal_goal_id = analysis_retry_proposal.goal_id
        proposal_event_id = analysis_retry_proposal.event.id
        try:
            analysis_retry_execution = retry_cognition_analysis(
                database_path,
                provider,
                model=analysis_retry_proposal.model,
                action_id=analysis_retry_proposal.retry_of_action_id,
                trace_id=turn_event.id,
                expected_plan_revision=analysis_retry_proposal.plan_revision,
                expected_evidence_event_ids=analysis_retry_proposal.evidence_event_ids,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            return _failed_turn(
                database_path,
                turn_event=turn_event,
                intent="AUTHORIZE",
                goal_id=proposal_goal_id,
                error=str(exc),
                reason_code="operation_authorization_routing_failed",
                current_decision=decision,
            )
        effect_type = "analysis.retry"
        effect_id = analysis_retry_execution.action.id
    else:
        return _unsupported_turn(
            database_path,
            turn_event=turn_event,
            goal_id=goal_id,
            reason_code="operation_proposal_not_supported",
            current_decision=decision,
        )

    try:
        executive_receipt = run_executive_until_gate(
            database_path,
            goal_id=proposal_goal_id,
            provider=provider,
            model=model,
            max_transitions=max_transitions,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed_turn(
            database_path,
            turn_event=turn_event,
            intent="AUTHORIZE",
            goal_id=proposal_goal_id,
            error=str(exc),
            reason_code="operation_authorization_routing_failed",
            current_decision=decision,
        )

    routing_event = _append_routed_event(
        database_path,
        turn_event=turn_event,
        intent="AUTHORIZE",
        executive_receipt=executive_receipt,
        authority_scope="CURRENT_OPERATION_PROPOSAL_ONLY",
        goal_id=proposal_goal_id,
        current_decision=decision,
        effect_type=effect_type,
        effect_id=effect_id,
        proposal_event_id=proposal_event_id,
    )
    return UserTurnReceipt(
        status="ROUTED",
        turn_event=turn_event,
        intent="AUTHORIZE",
        routing_event=routing_event,
        executive_receipt=executive_receipt,
        effect_type=effect_type,
        effect_id=effect_id,
    )


def _append_routed_event(
    database_path: Path,
    *,
    turn_event: Event,
    intent: UserTurnIntent,
    executive_receipt: ExecutiveContinueReceipt,
    authority_scope: str,
    goal_id: str | None,
    current_decision: ExecutiveDecision | None = None,
    effect_type: UserTurnEffectType | None = None,
    effect_id: str | None = None,
    proposal_event_id: str | None = None,
) -> Event:
    payload: dict[str, object] = {
        "turn_event_id": turn_event.id,
        "intent": intent,
        "authority_scope": authority_scope,
        "executive_status": executive_receipt.status,
        "transitions_executed": executive_receipt.transitions_executed,
        "final_outcome": executive_receipt.final_decision.outcome,
        "final_operation": executive_receipt.final_decision.operation,
        "final_reason_code": executive_receipt.final_decision.reason_code,
        "transitions": [
            {
                "operation": transition.executed_operation,
                "result_type": transition.result_type,
                "result_id": transition.result_id,
            }
            for transition in executive_receipt.transitions
        ],
    }
    if current_decision is not None:
        payload["gate"] = _decision_gate_payload(current_decision)
    if effect_type is not None and effect_id is not None:
        payload["effect_type"] = effect_type
        payload["effect_id"] = effect_id
    if proposal_event_id is not None:
        payload["proposal_event_id"] = proposal_event_id

    routing_event = Event.create(
        kind="executive.user_turn.routed",
        source="system",
        payload=payload,
        trace_id=turn_event.id,
        goal_id=goal_id,
    )
    append_event(database_path, routing_event)
    return routing_event


def _unsupported_turn(
    database_path: Path,
    *,
    turn_event: Event,
    goal_id: str | None,
    reason_code: str,
    current_decision: ExecutiveDecision | None = None,
) -> UserTurnReceipt:
    payload: dict[str, object] = {
        "turn_event_id": turn_event.id,
        "reason_code": reason_code,
        "supported_intents": [
            "CONTINUE",
            "SELECT_CURRENT_GOAL",
            "MATERIALIZE_CURRENT_PROCESS_PROPOSAL",
            "MATERIALIZE_CURRENT_PROCESS_RETRY_PROPOSAL",
            "MATERIALIZE_CURRENT_FILE_PATCH_PROPOSAL",
            "MATERIALIZE_CURRENT_FILE_RETRY_PROPOSAL",
            "ANSWER_AT_USER_INPUT_GATE",
            "CONFIRM_AT_GATE",
            "AUTHORIZE_CURRENT_PROCESS_PROPOSAL",
            "AUTHORIZE_CURRENT_FILE_PATCH_PROPOSAL",
            "AUTHORIZE_CURRENT_PROCESS_RETRY_PROPOSAL",
            "AUTHORIZE_CURRENT_FILE_RETRY_PROPOSAL",
            "AUTHORIZE_CURRENT_ANALYSIS_RETRY_PROPOSAL",
        ],
    }
    if current_decision is not None:
        payload["gate"] = _decision_gate_payload(current_decision)

    routing_event = Event.create(
        kind="user.turn.unhandled",
        source="system",
        payload=payload,
        trace_id=turn_event.id,
        goal_id=goal_id,
    )
    append_event(database_path, routing_event)
    return UserTurnReceipt(
        status="UNSUPPORTED",
        turn_event=turn_event,
        intent=None,
        routing_event=routing_event,
    )


def _failed_turn(
    database_path: Path,
    *,
    turn_event: Event,
    intent: UserTurnIntent | None,
    goal_id: str | None,
    error: str,
    reason_code: str,
    current_decision: ExecutiveDecision | None = None,
) -> UserTurnReceipt:
    payload: dict[str, object] = {
        "turn_event_id": turn_event.id,
        "intent": intent,
        "reason_code": reason_code,
        "error": error,
    }
    if current_decision is not None:
        payload["gate"] = _decision_gate_payload(current_decision)

    routing_event = Event.create(
        kind="executive.user_turn.failed",
        source="system",
        payload=payload,
        trace_id=turn_event.id,
        goal_id=goal_id,
    )
    append_event(database_path, routing_event)
    return UserTurnReceipt(
        status="FAILED",
        turn_event=turn_event,
        intent=intent,
        routing_event=routing_event,
        error=error,
    )


def _decision_gate_payload(decision: ExecutiveDecision) -> dict[str, object]:
    return {
        "outcome": decision.outcome,
        "reason_code": decision.reason_code,
        "operation": decision.operation,
        "goal_id": decision.goal_id,
        "plan_id": decision.plan_id,
        "step_id": decision.step_id,
        "action_id": decision.action_id,
        "verification_id": decision.verification_id,
        "capability": decision.capability,
        "goal_candidates": [
            {
                "goal_id": candidate.goal_id,
                "status": candidate.status,
                "title": candidate.title,
            }
            for candidate in decision.goal_candidates
        ],
    }


def _required_decision_value(
    value: str | None,
    field: str,
    decision: ExecutiveDecision,
) -> str:
    if value is None or not value.strip():
        raise RuntimeError(
            f"gate {decision.reason_code} não possui {field} necessário para {decision.operation}"
        )
    return value.strip()


def _is_explicit_confirmation(text: str) -> bool:
    return _normalize_turn_text(text) in _CONFIRM_UTTERANCES


def _is_explicit_operation_authorization(text: str) -> bool:
    return _normalize_turn_text(text) in _AUTHORIZE_UTTERANCES


def _normalize_turn_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    without_punctuation = re.sub(r"[^\w\s]", " ", without_accents)
    return re.sub(r"\s+", " ", without_punctuation).strip()
