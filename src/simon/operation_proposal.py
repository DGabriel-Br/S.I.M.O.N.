from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from simon.events import Event, append_event, get_event
from simon.executive import ExecutiveDecision, decide_next
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
    previous_event_id = _latest_process_run_proposal_event_id(database_path, goal_id)
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

    event_id = _latest_process_run_proposal_event_id(database_path, goal_id)
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
        bind_process_run_step(readiness.plan, step_id=step_id, request=request)
    except (TypeError, ValueError):
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


def _latest_process_run_proposal_event_id(database_path: Path, goal_id: str) -> str | None:
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


def _required_decision_value(value: str | None, field: str) -> str:
    if value is None or not value.strip():
        raise RuntimeError(f"gate de process.run não possui {field}")
    return value.strip()
