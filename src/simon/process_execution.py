from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from simon.actions import Action, create_action_in_connection, transition_action_in_connection
from simon.events import Event
from simon.process_binding import ProcessRunBinding, ProcessRunRequest, bind_process_run_step
from simon.step_readiness import evaluate_active_plan


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
    execution_trace_id = trace_id or f"trc_{uuid4().hex}"

    authorization_event = Event.create(
        kind="process.run.authorized",
        source="user",
        payload={
            "plan_id": binding.plan_id,
            "plan_revision": binding.plan_revision,
            "step_id": binding.step_id,
            "request": request.model_dump(mode="json"),
        },
        trace_id=execution_trace_id,
        goal_id=binding.goal_id,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_step_has_no_attempt(connection, binding)
        action = create_action_in_connection(
            connection,
            goal_id=binding.goal_id,
            plan_id=binding.plan_id,
            step_id=binding.step_id,
            kind="process.run",
            input_data={
                "request": request.model_dump(mode="json"),
                "verification": binding.verification,
                "authorization_event_id": authorization_event.id,
            },
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
