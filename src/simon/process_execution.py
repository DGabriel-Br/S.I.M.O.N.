from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from simon.actions import (
    Action,
    create_action_in_connection,
    get_action,
    transition_action_in_connection,
)
from simon.events import Event
from simon.process_binding import ProcessRunBinding, ProcessRunRequest, bind_process_run_step
from simon.step_readiness import StepReadiness, evaluate_active_plan


@dataclass(frozen=True, slots=True)
class ProcessRunReceipt:
    action: Action
    binding: ProcessRunBinding
    authorization_event_id: str
    execution_event_id: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    retry_of_action_id: str | None = None


def execute_next_process_run(
    database_path: Path,
    *,
    goal_id: str,
    request: ProcessRunRequest,
    trace_id: str | None = None,
) -> ProcessRunReceipt:
    """Executa o próximo step process.run READY usando apenas parâmetros já estruturados."""
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    step = readiness.next_step
    if step is None:
        raise ValueError("plan não possui step READY para executar")
    if step.capability != "process.run":
        raise ValueError(
            "próximo step READY não usa a capability process.run: "
            f"{step.step_id} ({step.capability or 'não especificada'})"
        )

    binding = bind_process_run_step(
        readiness.plan,
        step_id=step.step_id,
        request=request,
    )
    _validate_working_directory(request)
    return _execute_process_run_attempt(
        database_path,
        binding=binding,
        request=request,
        trace_id=trace_id,
        retry_of_action=None,
    )


def retry_process_run(
    database_path: Path,
    *,
    action_id: str,
    request: ProcessRunRequest,
    trace_id: str | None = None,
) -> ProcessRunReceipt:
    """Autoriza uma nova tentativa explícita após falha ou interrupção operacional."""
    original = get_action(database_path, action_id)
    if original is None:
        raise ValueError(f"action não encontrada: {action_id}")
    if original.kind != "process.run":
        raise ValueError(f"action não representa process.run: {action_id}")
    if original.status not in {"FAILED", "INTERRUPTED"}:
        raise ValueError(
            "retry process.run exige Action FAILED ou INTERRUPTED: "
            f"{action_id} está {original.status}"
        )

    readiness = evaluate_active_plan(database_path, goal_id=original.goal_id)
    if readiness.plan.id != original.plan_id:
        raise ValueError(
            "retry process.run exige que a tentativa pertença ao Plan ACTIVE atual: "
            f"{original.plan_id}"
        )

    step = next(
        (candidate for candidate in readiness.steps if candidate.step_id == original.step_id),
        None,
    )
    if step is None:
        raise RuntimeError(f"step da tentativa não existe no Plan ativo: {original.step_id}")
    _validate_retry_readiness(step, original)

    binding = bind_process_run_step(
        readiness.plan,
        step_id=original.step_id,
        request=request,
    )
    _validate_working_directory(request)
    return _execute_process_run_attempt(
        database_path,
        binding=binding,
        request=request,
        trace_id=trace_id,
        retry_of_action=original,
    )


def _execute_process_run_attempt(
    database_path: Path,
    *,
    binding: ProcessRunBinding,
    request: ProcessRunRequest,
    trace_id: str | None,
    retry_of_action: Action | None,
) -> ProcessRunReceipt:
    execution_trace_id = trace_id or f"trc_{uuid4().hex}"
    authorization_kind = (
        "process.run.authorized" if retry_of_action is None else "action.retry.authorized"
    )
    authorization_payload: dict[str, object] = {
        "plan_id": binding.plan_id,
        "plan_revision": binding.plan_revision,
        "step_id": binding.step_id,
        "request": request.model_dump(mode="json"),
    }
    if retry_of_action is not None:
        authorization_payload.update(
            {
                "retry_of_action_id": retry_of_action.id,
                "previous_status": retry_of_action.status,
                "capability": "process.run",
            }
        )

    authorization_event = Event.create(
        kind=authorization_kind,
        source="user",
        payload=authorization_payload,
        trace_id=execution_trace_id,
        goal_id=binding.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if retry_of_action is None:
            _ensure_step_has_no_attempt(connection, binding)
        else:
            _ensure_retry_is_latest_attempt(connection, binding, retry_of_action)

        input_data: dict[str, object] = {
            "request": request.model_dump(mode="json"),
            "verification": binding.verification,
            "authorization_event_id": authorization_event.id,
        }
        if retry_of_action is not None:
            input_data["retry_of_action_id"] = retry_of_action.id

        action = create_action_in_connection(
            connection,
            goal_id=binding.goal_id,
            plan_id=binding.plan_id,
            step_id=binding.step_id,
            kind="process.run",
            input_data=input_data,
        )
        running = transition_action_in_connection(connection, action.id, "RUNNING")
        _insert_event(connection, authorization_event)
        _insert_event(
            connection,
            Event.create(
                kind="process.execution.started",
                source="tool",
                payload={
                    "action_id": running.id,
                    "plan_id": running.plan_id,
                    "step_id": running.step_id,
                    "argv": list(request.argv()),
                    "working_directory": request.working_directory,
                    "timeout_seconds": request.timeout_seconds,
                    "retry_of_action_id": (
                        retry_of_action.id if retry_of_action is not None else None
                    ),
                },
                trace_id=execution_trace_id,
                goal_id=running.goal_id,
            ),
        )

    started_at = monotonic()
    try:
        completed_process = subprocess.run(
            request.argv(),
            cwd=request.working_directory,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=request.timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_seconds = monotonic() - started_at
        stdout = _timeout_stream(exc.stdout)
        stderr = _timeout_stream(exc.stderr)
        return _record_failure(
            database_path,
            binding=binding,
            action_id=running.id,
            authorization_event_id=authorization_event.id,
            trace_id=execution_trace_id,
            kind="process_timeout",
            message=f"processo excedeu timeout de {request.timeout_seconds:g}s",
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            retry_of_action_id=(retry_of_action.id if retry_of_action is not None else None),
        )
    except OSError as exc:
        duration_seconds = monotonic() - started_at
        return _record_failure(
            database_path,
            binding=binding,
            action_id=running.id,
            authorization_event_id=authorization_event.id,
            trace_id=execution_trace_id,
            kind="process_start",
            message=str(exc),
            stdout="",
            stderr="",
            duration_seconds=duration_seconds,
            retry_of_action_id=(retry_of_action.id if retry_of_action is not None else None),
        )

    duration_seconds = monotonic() - started_at
    stdout = completed_process.stdout or ""
    stderr = completed_process.stderr or ""
    execution_event = Event.create(
        kind="process.execution.completed",
        source="tool",
        payload={
            "action_id": running.id,
            "plan_id": running.plan_id,
            "step_id": running.step_id,
            "exit_code": completed_process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration_seconds,
            "retry_of_action_id": (
                retry_of_action.id if retry_of_action is not None else None
            ),
        },
        trace_id=execution_trace_id,
        goal_id=running.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        completed = transition_action_in_connection(
            connection,
            running.id,
            "COMPLETED",
            reported_result={
                "execution_event_id": execution_event.id,
                "exit_code": completed_process.returncode,
                "duration_seconds": duration_seconds,
            },
        )
        _insert_event(connection, execution_event)

    return ProcessRunReceipt(
        action=completed,
        binding=binding,
        authorization_event_id=authorization_event.id,
        execution_event_id=execution_event.id,
        stdout=stdout,
        stderr=stderr,
        exit_code=completed_process.returncode,
        duration_seconds=duration_seconds,
        retry_of_action_id=(retry_of_action.id if retry_of_action is not None else None),
    )


def _record_failure(
    database_path: Path,
    *,
    binding: ProcessRunBinding,
    action_id: str,
    authorization_event_id: str,
    trace_id: str,
    kind: str,
    message: str,
    stdout: str,
    stderr: str,
    duration_seconds: float,
    retry_of_action_id: str | None,
) -> ProcessRunReceipt:
    failure_event = Event.create(
        kind="process.execution.failed",
        source="tool",
        payload={
            "action_id": action_id,
            "plan_id": binding.plan_id,
            "step_id": binding.step_id,
            "failure_kind": kind,
            "message": message,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration_seconds,
            "retry_of_action_id": retry_of_action_id,
        },
        trace_id=trace_id,
        goal_id=binding.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        failed = transition_action_in_connection(
            connection,
            action_id,
            "FAILED",
            failure={
                "kind": kind,
                "message": message,
                "failure_event_id": failure_event.id,
                "duration_seconds": duration_seconds,
            },
        )
        _insert_event(connection, failure_event)

    return ProcessRunReceipt(
        action=failed,
        binding=binding,
        authorization_event_id=authorization_event_id,
        execution_event_id=failure_event.id,
        stdout=stdout,
        stderr=stderr,
        exit_code=None,
        duration_seconds=duration_seconds,
        retry_of_action_id=retry_of_action_id,
    )


def _validate_retry_readiness(step: StepReadiness, original: Action) -> None:
    if step.state != "BLOCKED":
        raise ValueError(
            "retry process.run exige step bloqueado aguardando review da tentativa anterior"
        )

    expected_detail = f"{original.id}: {original.status}"
    blockers = tuple((blocker.kind, blocker.detail) for blocker in step.blockers)
    if blockers != (("PREVIOUS_ATTEMPT_REQUIRES_REVIEW", expected_detail),):
        rendered = ", ".join(f"{kind}: {detail}" for kind, detail in blockers) or "nenhum"
        raise ValueError(
            "retry process.run não pode ignorar outros blockers do step: " + rendered
        )


def _validate_working_directory(request: ProcessRunRequest) -> None:
    working_directory = Path(request.working_directory)
    if not working_directory.exists():
        raise ValueError(f"diretório de trabalho não encontrado: {working_directory}")
    if not working_directory.is_dir():
        raise ValueError(f"diretório de trabalho inválido: {working_directory}")


def _ensure_step_has_no_attempt(
    connection: sqlite3.Connection,
    binding: ProcessRunBinding,
) -> None:
    row = connection.execute(
        """
        SELECT id, status
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (binding.plan_id, binding.step_id),
    ).fetchone()
    if row is not None:
        raise ValueError(
            "step process.run já possui tentativa registrada: "
            f"{row[0]} ({row[1]})"
        )


def _ensure_retry_is_latest_attempt(
    connection: sqlite3.Connection,
    binding: ProcessRunBinding,
    original: Action,
) -> None:
    row = connection.execute(
        """
        SELECT id, status
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (binding.plan_id, binding.step_id),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"step não possui tentativa persistida: {binding.step_id}")
    if str(row[0]) != original.id:
        raise ValueError(
            "retry process.run exige a tentativa mais recente do step; "
            f"a Action {original.id} já foi sucedida por {row[0]}"
        )
    if str(row[1]) != original.status:
        raise RuntimeError(
            "status da tentativa mudou durante autorização do retry: "
            f"{original.status} -> {row[1]}"
        )


def _timeout_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _insert_event(connection: sqlite3.Connection, event: Event) -> None:
    connection.execute(
        """
        INSERT INTO events (
            id,
            kind,
            occurred_at,
            source,
            payload_json,
            trace_id,
            related_entity_ids_json,
            goal_id,
            experience_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            event.kind,
            event.occurred_at.isoformat(),
            event.source,
            json.dumps(event.payload, ensure_ascii=False, separators=(",", ":")),
            event.trace_id,
            json.dumps(event.related_entity_ids, separators=(",", ":")),
            event.goal_id,
            event.experience_id,
        ),
    )
