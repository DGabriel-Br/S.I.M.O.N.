from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from simon.actions import Action, get_action
from simon.cognition_analysis import get_cognition_retry_context
from simon.events import Event, append_event, get_event
from simon.executive import ExecutiveDecision, decide_next
from simon.file_patch import FilePatchRequest, bind_file_patch_step
from simon.process_binding import ProcessRunRequest, bind_process_run_step
from simon.step_readiness import evaluate_active_plan


@dataclass(frozen=True, slots=True)
class ProcessRunProposal:
    event: Event
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    reason: str
    verification: str
    request: ProcessRunRequest


@dataclass(frozen=True, slots=True)
class FilePatchProposal:
    event: Event
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    reason: str
    verification: str
    capability_detail: str
    request: FilePatchRequest


@dataclass(frozen=True, slots=True)
class ProcessRetryProposal:
    event: Event
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    reason: str
    verification: str
    retry_of_action_id: str
    previous_status: str
    request: ProcessRunRequest


@dataclass(frozen=True, slots=True)
class FilePatchRetryProposal:
    event: Event
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    reason: str
    verification: str
    capability_detail: str
    retry_of_action_id: str
    previous_status: str
    request: FilePatchRequest


@dataclass(frozen=True, slots=True)
class CognitionAnalysisRetryProposal:
    event: Event
    goal_id: str
    plan_id: str
    plan_revision: int
    step_id: str
    reason: str
    verification: str
    retry_of_action_id: str
    previous_status: str
    model: str
    evidence_event_ids: tuple[str, ...]


def propose_process_run(
    database_path: Path,
    *,
    goal_id: str,
    request: ProcessRunRequest,
    trace_id: str | None = None,
) -> ProcessRunProposal:
    """Persiste a execução concreta pedida pelo gate sem autorizar ou executar o processo."""
    decision = decide_next(database_path, goal_id=goal_id)
    _require_process_run_authorization_gate(decision)

    plan_id = _required_decision_value(decision.plan_id, "plan_id")
    step_id = _required_decision_value(decision.step_id, "step_id")
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    if readiness.plan.id != plan_id:
        raise RuntimeError(
            "a decisão de autorização não corresponde mais ao Plan ACTIVE atual: "
            f"{plan_id} != {readiness.plan.id}"
        )

    binding = bind_process_run_step(
        readiness.plan,
        step_id=step_id,
        request=request,
    )
    previous_event_id = _latest_operation_proposal_event_id(database_path, goal_id)
    event = Event.create(
        kind="executive.operation.proposed",
        source="system",
        payload={
            "proposal_type": "process.run",
            "operation": "plan.run",
            "reason_code": decision.reason_code,
            "reason": decision.reason,
            "goal_id": binding.goal_id,
            "plan_id": binding.plan_id,
            "plan_revision": binding.plan_revision,
            "step_id": binding.step_id,
            "capability": binding.capability,
            "verification": binding.verification,
            "request": request.model_dump(mode="json"),
            "argv": list(request.argv()),
            "supersedes_proposal_event_id": previous_event_id,
        },
        trace_id=trace_id,
        goal_id=binding.goal_id,
    )
    append_event(database_path, event)
    return ProcessRunProposal(
        event=event,
        goal_id=binding.goal_id,
        plan_id=binding.plan_id,
        plan_revision=binding.plan_revision,
        step_id=binding.step_id,
        reason=decision.reason,
        verification=binding.verification,
        request=request,
    )


def propose_file_patch(
    database_path: Path,
    *,
    goal_id: str,
    request: FilePatchRequest,
    trace_id: str | None = None,
) -> FilePatchProposal:
    """Persiste uma alteração concreta pedida pelo gate sem autorizar ou modificar arquivo."""
    decision = decide_next(database_path, goal_id=goal_id)
    _require_file_patch_authorization_gate(decision)

    plan_id = _required_decision_value(decision.plan_id, "plan_id")
    step_id = _required_decision_value(decision.step_id, "step_id")
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    if readiness.plan.id != plan_id:
        raise RuntimeError(
            "a decisão de autorização não corresponde mais ao Plan ACTIVE atual: "
            f"{plan_id} != {readiness.plan.id}"
        )

    binding = bind_file_patch_step(
        readiness.plan,
        step_id=step_id,
        request=request,
    )
    previous_event_id = _latest_operation_proposal_event_id(database_path, goal_id)
    event = Event.create(
        kind="executive.operation.proposed",
        source="system",
        payload={
            "proposal_type": "file.patch",
            "operation": "plan.patch",
            "reason_code": decision.reason_code,
            "reason": decision.reason,
            "goal_id": binding.goal_id,
            "plan_id": binding.plan_id,
            "plan_revision": binding.plan_revision,
            "step_id": binding.step_id,
            "capability": "file.patch",
            "capability_detail": binding.capability_detail,
            "verification": binding.verification,
            "request": request.model_dump(mode="json"),
            "supersedes_proposal_event_id": previous_event_id,
        },
        trace_id=trace_id,
        goal_id=binding.goal_id,
    )
    append_event(database_path, event)
    return FilePatchProposal(
        event=event,
        goal_id=binding.goal_id,
        plan_id=binding.plan_id,
        plan_revision=binding.plan_revision,
        step_id=binding.step_id,
        reason=decision.reason,
        verification=binding.verification,
        capability_detail=binding.capability_detail,
        request=request,
    )


def propose_process_retry(
    database_path: Path,
    *,
    action_id: str,
    request: ProcessRunRequest,
    trace_id: str | None = None,
) -> ProcessRetryProposal:
    """Persiste uma nova tentativa concreta de process.run sem autorizar o retry."""
    original = _require_retry_action(database_path, action_id, kind="process.run")
    decision = decide_next(database_path, goal_id=original.goal_id)
    _require_retry_authorization_gate(decision, operation="process.retry", original=original)

    readiness = evaluate_active_plan(database_path, goal_id=original.goal_id)
    if readiness.plan.id != original.plan_id:
        raise ValueError("retry process.run exige a tentativa no Plan ACTIVE atual")
    binding = bind_process_run_step(
        readiness.plan,
        step_id=original.step_id,
        request=request,
    )
    previous_event_id = _latest_operation_proposal_event_id(database_path, original.goal_id)
    event = Event.create(
        kind="executive.operation.proposed",
        source="system",
        payload={
            "proposal_type": "process.retry",
            "operation": "process.retry",
            "reason_code": decision.reason_code,
            "reason": decision.reason,
            "goal_id": binding.goal_id,
            "plan_id": binding.plan_id,
            "plan_revision": binding.plan_revision,
            "step_id": binding.step_id,
            "capability": "process.run",
            "verification": binding.verification,
            "retry_of_action_id": original.id,
            "previous_status": original.status,
            "request": request.model_dump(mode="json"),
            "argv": list(request.argv()),
            "supersedes_proposal_event_id": previous_event_id,
        },
        trace_id=trace_id,
        goal_id=binding.goal_id,
    )
    append_event(database_path, event)
    return ProcessRetryProposal(
        event=event,
        goal_id=binding.goal_id,
        plan_id=binding.plan_id,
        plan_revision=binding.plan_revision,
        step_id=binding.step_id,
        reason=decision.reason,
        verification=binding.verification,
        retry_of_action_id=original.id,
        previous_status=original.status,
        request=request,
    )


def propose_file_patch_retry(
    database_path: Path,
    *,
    action_id: str,
    request: FilePatchRequest,
    trace_id: str | None = None,
) -> FilePatchRetryProposal:
    """Persiste uma nova tentativa concreta de file.patch sem autorizar o retry."""
    original = _require_retry_action(database_path, action_id, kind="file.patch")
    decision = decide_next(database_path, goal_id=original.goal_id)
    _require_retry_authorization_gate(decision, operation="file.retry", original=original)

    readiness = evaluate_active_plan(database_path, goal_id=original.goal_id)
    if readiness.plan.id != original.plan_id:
        raise ValueError("retry file.patch exige a tentativa no Plan ACTIVE atual")
    binding = bind_file_patch_step(
        readiness.plan,
        step_id=original.step_id,
        request=request,
    )
    previous_event_id = _latest_operation_proposal_event_id(database_path, original.goal_id)
    event = Event.create(
        kind="executive.operation.proposed",
        source="system",
        payload={
            "proposal_type": "file.retry",
            "operation": "file.retry",
            "reason_code": decision.reason_code,
            "reason": decision.reason,
            "goal_id": binding.goal_id,
            "plan_id": binding.plan_id,
            "plan_revision": binding.plan_revision,
            "step_id": binding.step_id,
            "capability": "file.patch",
            "capability_detail": binding.capability_detail,
            "verification": binding.verification,
            "retry_of_action_id": original.id,
            "previous_status": original.status,
            "request": request.model_dump(mode="json"),
            "supersedes_proposal_event_id": previous_event_id,
        },
        trace_id=trace_id,
        goal_id=binding.goal_id,
    )
    append_event(database_path, event)
    return FilePatchRetryProposal(
        event=event,
        goal_id=binding.goal_id,
        plan_id=binding.plan_id,
        plan_revision=binding.plan_revision,
        step_id=binding.step_id,
        reason=decision.reason,
        verification=binding.verification,
        capability_detail=binding.capability_detail,
        retry_of_action_id=original.id,
        previous_status=original.status,
        request=request,
    )


def propose_cognition_analysis_retry(
    database_path: Path,
    *,
    action_id: str,
    model: str,
    trace_id: str | None = None,
) -> CognitionAnalysisRetryProposal:
    """Persiste um retry cognition.analyze concreto sem autorizar nem chamar o modelo."""
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("modelo do retry cognition.analyze não pode ser vazio")

    context = get_cognition_retry_context(database_path, action_id=action_id)
    original = context.original_action
    decision = decide_next(database_path, goal_id=original.goal_id)
    _require_retry_authorization_gate(decision, operation="analysis.retry", original=original)

    previous_event_id = _latest_operation_proposal_event_id(database_path, original.goal_id)
    event = Event.create(
        kind="executive.operation.proposed",
        source="system",
        payload={
            "proposal_type": "analysis.retry",
            "operation": "analysis.retry",
            "reason_code": decision.reason_code,
            "reason": decision.reason,
            "goal_id": context.plan.goal_id,
            "plan_id": context.plan.id,
            "plan_revision": context.plan.revision,
            "step_id": context.step.step_id,
            "capability": "cognition.analyze",
            "verification": context.verification,
            "retry_of_action_id": original.id,
            "previous_status": original.status,
            "model": normalized_model,
            "evidence_event_ids": list(context.evidence_event_ids),
            "supersedes_proposal_event_id": previous_event_id,
        },
        trace_id=trace_id,
        goal_id=context.plan.goal_id,
    )
    append_event(database_path, event)
    return CognitionAnalysisRetryProposal(
        event=event,
        goal_id=context.plan.goal_id,
        plan_id=context.plan.id,
        plan_revision=context.plan.revision,
        step_id=context.step.step_id,
        reason=decision.reason,
        verification=context.verification,
        retry_of_action_id=original.id,
        previous_status=original.status,
        model=normalized_model,
        evidence_event_ids=context.evidence_event_ids,
    )


def find_current_cognition_analysis_retry_proposal(
    database_path: Path,
    decision: ExecutiveDecision,
) -> CognitionAnalysisRetryProposal | None:
    if (
        decision.outcome != "NEEDS_OPERATION_AUTHORIZATION"
        or decision.operation != "analysis.retry"
    ):
        return None
    original = _decision_retry_action(database_path, decision, kind="cognition.analyze")
    if original is None:
        return None
    event = _latest_operation_proposal_event(database_path, original.goal_id)
    if event is None:
        return None
    payload = event.payload
    if not _retry_payload_matches(payload, decision, original, proposal_type="analysis.retry"):
        return None
    if payload.get("capability") != "cognition.analyze":
        return None

    raw_revision = payload.get("plan_revision")
    raw_reason = payload.get("reason")
    raw_verification = payload.get("verification")
    raw_model = payload.get("model")
    raw_evidence = payload.get("evidence_event_ids")
    if (
        not isinstance(raw_revision, int)
        or not isinstance(raw_reason, str)
        or not raw_reason.strip()
        or not isinstance(raw_verification, str)
        or not raw_verification.strip()
        or not isinstance(raw_model, str)
        or not raw_model.strip()
        or not isinstance(raw_evidence, list)
    ):
        return None

    normalized_evidence: list[str] = []
    for event_id in raw_evidence:
        if not isinstance(event_id, str) or not event_id.strip():
            return None
        normalized_evidence.append(event_id.strip())

    try:
        context = get_cognition_retry_context(database_path, action_id=original.id)
    except (RuntimeError, TypeError, ValueError):
        return None
    evidence_event_ids = tuple(normalized_evidence)
    if (
        context.plan.id != original.plan_id
        or context.plan.revision != raw_revision
        or context.verification != raw_verification.strip()
        or context.evidence_event_ids != evidence_event_ids
    ):
        return None

    return CognitionAnalysisRetryProposal(
        event=event,
        goal_id=original.goal_id,
        plan_id=original.plan_id,
        plan_revision=raw_revision,
        step_id=original.step_id,
        reason=raw_reason.strip(),
        verification=raw_verification.strip(),
        retry_of_action_id=original.id,
        previous_status=original.status,
        model=raw_model.strip(),
        evidence_event_ids=evidence_event_ids,
    )


def find_current_process_retry_proposal(
    database_path: Path,
    decision: ExecutiveDecision,
) -> ProcessRetryProposal | None:
    if decision.outcome != "NEEDS_OPERATION_AUTHORIZATION" or decision.operation != "process.retry":
        return None
    original = _decision_retry_action(database_path, decision, kind="process.run")
    if original is None:
        return None
    event = _latest_operation_proposal_event(database_path, original.goal_id)
    if event is None:
        return None
    payload = event.payload
    if not _retry_payload_matches(payload, decision, original, proposal_type="process.retry"):
        return None
    raw_revision = payload.get("plan_revision")
    raw_reason = payload.get("reason")
    raw_verification = payload.get("verification")
    if (
        not isinstance(raw_revision, int)
        or not isinstance(raw_reason, str)
        or not isinstance(raw_verification, str)
    ):
        return None
    readiness = evaluate_active_plan(database_path, goal_id=original.goal_id)
    if readiness.plan.id != original.plan_id or readiness.plan.revision != raw_revision:
        return None
    try:
        request = ProcessRunRequest.model_validate(payload.get("request"))
        binding = bind_process_run_step(readiness.plan, step_id=original.step_id, request=request)
    except (TypeError, ValueError):
        return None
    if binding.verification != raw_verification.strip():
        return None
    return ProcessRetryProposal(
        event=event,
        goal_id=original.goal_id,
        plan_id=original.plan_id,
        plan_revision=raw_revision,
        step_id=original.step_id,
        reason=raw_reason.strip(),
        verification=raw_verification.strip(),
        retry_of_action_id=original.id,
        previous_status=original.status,
        request=request,
    )


def find_current_file_patch_retry_proposal(
    database_path: Path,
    decision: ExecutiveDecision,
) -> FilePatchRetryProposal | None:
    if decision.outcome != "NEEDS_OPERATION_AUTHORIZATION" or decision.operation != "file.retry":
        return None
    original = _decision_retry_action(database_path, decision, kind="file.patch")
    if original is None:
        return None
    event = _latest_operation_proposal_event(database_path, original.goal_id)
    if event is None:
        return None
    payload = event.payload
    if not _retry_payload_matches(payload, decision, original, proposal_type="file.retry"):
        return None
    raw_revision = payload.get("plan_revision")
    raw_reason = payload.get("reason")
    raw_verification = payload.get("verification")
    raw_detail = payload.get("capability_detail")
    if (
        not isinstance(raw_revision, int)
        or not isinstance(raw_reason, str)
        or not isinstance(raw_verification, str)
        or not isinstance(raw_detail, str)
    ):
        return None
    readiness = evaluate_active_plan(database_path, goal_id=original.goal_id)
    if readiness.plan.id != original.plan_id or readiness.plan.revision != raw_revision:
        return None
    try:
        request = FilePatchRequest.model_validate(payload.get("request"))
        binding = bind_file_patch_step(readiness.plan, step_id=original.step_id, request=request)
    except (TypeError, ValueError):
        return None
    if (
        binding.verification != raw_verification.strip()
        or binding.capability_detail != raw_detail.strip()
    ):
        return None
    return FilePatchRetryProposal(
        event=event,
        goal_id=original.goal_id,
        plan_id=original.plan_id,
        plan_revision=raw_revision,
        step_id=original.step_id,
        reason=raw_reason.strip(),
        verification=raw_verification.strip(),
        capability_detail=raw_detail.strip(),
        retry_of_action_id=original.id,
        previous_status=original.status,
        request=request,
    )


def find_current_file_patch_proposal(
    database_path: Path,
    decision: ExecutiveDecision,
) -> FilePatchProposal | None:
    """Retorna somente a proposta file.patch mais recente que ainda corresponde ao gate atual."""
    if (
        decision.outcome != "NEEDS_OPERATION_AUTHORIZATION"
        or decision.operation != "plan.patch"
        or decision.capability != "file.patch"
    ):
        return None

    goal_id = decision.goal_id
    plan_id = decision.plan_id
    step_id = decision.step_id
    if goal_id is None or plan_id is None or step_id is None:
        return None

    event_id = _latest_operation_proposal_event_id(database_path, goal_id)
    if event_id is None:
        return None
    event = get_event(database_path, event_id)
    if event is None or event.kind != "executive.operation.proposed":
        return None

    payload = event.payload
    if (
        payload.get("proposal_type") != "file.patch"
        or payload.get("operation") != "plan.patch"
        or payload.get("reason_code") != decision.reason_code
        or payload.get("goal_id") != goal_id
        or payload.get("plan_id") != plan_id
        or payload.get("step_id") != step_id
        or payload.get("capability") != "file.patch"
    ):
        return None

    raw_revision = payload.get("plan_revision")
    raw_reason = payload.get("reason")
    raw_verification = payload.get("verification")
    raw_capability_detail = payload.get("capability_detail")
    if (
        not isinstance(raw_revision, int)
        or not isinstance(raw_reason, str)
        or not raw_reason.strip()
        or not isinstance(raw_verification, str)
        or not raw_verification.strip()
        or not isinstance(raw_capability_detail, str)
        or not raw_capability_detail.strip()
    ):
        return None

    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    if readiness.plan.id != plan_id or readiness.plan.revision != raw_revision:
        return None

    raw_request = payload.get("request")
    try:
        request = FilePatchRequest.model_validate(raw_request)
        binding = bind_file_patch_step(readiness.plan, step_id=step_id, request=request)
    except (TypeError, ValueError):
        return None
    if (
        binding.verification != raw_verification.strip()
        or binding.capability_detail != raw_capability_detail.strip()
    ):
        return None

    return FilePatchProposal(
        event=event,
        goal_id=goal_id,
        plan_id=plan_id,
        plan_revision=raw_revision,
        step_id=step_id,
        reason=raw_reason.strip(),
        verification=raw_verification.strip(),
        capability_detail=raw_capability_detail.strip(),
        request=request,
    )


def find_current_process_run_proposal(
    database_path: Path,
    decision: ExecutiveDecision,
) -> ProcessRunProposal | None:
    """Retorna somente a proposta process.run mais recente que ainda corresponde ao gate atual."""
    if (
        decision.outcome != "NEEDS_OPERATION_AUTHORIZATION"
        or decision.operation != "plan.run"
        or decision.capability != "process.run"
    ):
        return None

    goal_id = decision.goal_id
    plan_id = decision.plan_id
    step_id = decision.step_id
    if goal_id is None or plan_id is None or step_id is None:
        return None

    event_id = _latest_operation_proposal_event_id(database_path, goal_id)
    if event_id is None:
        return None
    event = get_event(database_path, event_id)
    if event is None or event.kind != "executive.operation.proposed":
        return None

    payload = event.payload
    if (
        payload.get("proposal_type") != "process.run"
        or payload.get("operation") != "plan.run"
        or payload.get("reason_code") != decision.reason_code
        or payload.get("goal_id") != goal_id
        or payload.get("plan_id") != plan_id
        or payload.get("step_id") != step_id
        or payload.get("capability") != "process.run"
    ):
        return None

    raw_revision = payload.get("plan_revision")
    raw_reason = payload.get("reason")
    raw_verification = payload.get("verification")
    if (
        not isinstance(raw_revision, int)
        or not isinstance(raw_reason, str)
        or not raw_reason.strip()
        or not isinstance(raw_verification, str)
        or not raw_verification.strip()
    ):
        return None
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    if readiness.plan.id != plan_id or readiness.plan.revision != raw_revision:
        return None

    raw_request = payload.get("request")
    try:
        request = ProcessRunRequest.model_validate(raw_request)
        binding = bind_process_run_step(readiness.plan, step_id=step_id, request=request)
    except (TypeError, ValueError):
        return None
    if binding.verification != raw_verification.strip():
        return None

    return ProcessRunProposal(
        event=event,
        goal_id=goal_id,
        plan_id=plan_id,
        plan_revision=raw_revision,
        step_id=step_id,
        reason=raw_reason.strip(),
        verification=raw_verification.strip(),
        request=request,
    )


def _require_retry_action(database_path: Path, action_id: str, *, kind: str) -> Action:
    action = get_action(database_path, action_id)
    if action is None:
        raise ValueError(f"action não encontrada: {action_id}")
    if action.kind != kind:
        raise ValueError(f"action não representa {kind}: {action_id}")
    if action.status not in {"FAILED", "INTERRUPTED"}:
        raise ValueError(f"retry {kind} exige Action FAILED ou INTERRUPTED: {action.status}")
    return action


def _require_retry_authorization_gate(
    decision: ExecutiveDecision,
    *,
    operation: str,
    original: Action,
) -> None:
    if decision.outcome != "NEEDS_OPERATION_AUTHORIZATION" or decision.operation != operation:
        raise ValueError(f"o gate atual não solicita {operation}")
    if decision.action_id != original.id:
        raise ValueError("o gate de retry não corresponde à Action informada")
    if decision.reason_code != "retry_authorization_required":
        raise ValueError("o gate atual não representa retry autorizado")


def _decision_retry_action(
    database_path: Path,
    decision: ExecutiveDecision,
    *,
    kind: str,
) -> Action | None:
    action_id = decision.action_id
    if action_id is None:
        return None
    action = get_action(database_path, action_id)
    if action is None or action.kind != kind or action.status not in {"FAILED", "INTERRUPTED"}:
        return None
    return action


def _retry_payload_matches(
    payload: dict[str, object],
    decision: ExecutiveDecision,
    original: Action,
    *,
    proposal_type: str,
) -> bool:
    return (
        payload.get("proposal_type") == proposal_type
        and payload.get("operation") == decision.operation
        and payload.get("reason_code") == decision.reason_code
        and payload.get("goal_id") == original.goal_id
        and payload.get("plan_id") == original.plan_id
        and payload.get("step_id") == original.step_id
        and payload.get("retry_of_action_id") == original.id
        and payload.get("previous_status") == original.status
    )


def _latest_operation_proposal_event(database_path: Path, goal_id: str) -> Event | None:
    event_id = _latest_operation_proposal_event_id(database_path, goal_id)
    return get_event(database_path, event_id) if event_id is not None else None


def _latest_operation_proposal_event_id(database_path: Path, goal_id: str) -> str | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM events
            WHERE kind = 'executive.operation.proposed'
              AND goal_id = ?
            ORDER BY occurred_at DESC, rowid DESC
            LIMIT 1
            """,
            (goal_id,),
        ).fetchone()
    return str(row[0]) if row is not None else None


def _require_process_run_authorization_gate(decision: ExecutiveDecision) -> None:
    if decision.outcome != "NEEDS_OPERATION_AUTHORIZATION":
        raise ValueError(
            "process.run só pode ser proposto quando o Executive aguarda autorização operacional"
        )
    if decision.operation != "plan.run" or decision.capability != "process.run":
        raise ValueError(
            "o gate atual não solicita uma autorização concreta de process.run: "
            f"{decision.operation or 'nenhuma'}"
        )


def _require_file_patch_authorization_gate(decision: ExecutiveDecision) -> None:
    if decision.outcome != "NEEDS_OPERATION_AUTHORIZATION":
        raise ValueError(
            "file.patch só pode ser proposto quando o Executive aguarda autorização operacional"
        )
    if decision.operation != "plan.patch" or decision.capability != "file.patch":
        raise ValueError(
            "o gate atual não solicita uma autorização concreta de file.patch: "
            f"{decision.operation or 'nenhuma'}"
        )


def _required_decision_value(value: str | None, field: str) -> str:
    if value is None or not value.strip():
        raise RuntimeError(f"gate de autorização não possui {field}")
    return value.strip()
