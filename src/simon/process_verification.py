from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from simon.actions import Action, get_action_in_connection
from simon.verification import (
    VerificationResult,
    create_verification_result_in_connection,
    list_verification_results_in_connection,
)

VERIFICATION_TYPE = "process.run.execution_observed"
VERIFICATION_STRENGTH = 3


@dataclass(frozen=True, slots=True)
class ProcessRunVerificationReceipt:
    action: Action
    verification: VerificationResult
    created: bool


def verify_process_run_execution(
    database_path: Path,
    *,
    action_id: str,
) -> ProcessRunVerificationReceipt:
    """Verifica a evidência técnica íntegra produzida por uma Action process.run."""
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        action = get_action_in_connection(connection, action_id)
        if action is None:
            raise ValueError(f"action não encontrada: {action_id}")
        _validate_action(action)
        _ensure_latest_step_attempt(connection, action)

        execution_event_id = _execution_event_id(action)
        observed = _execution_observation(
            connection,
            action=action,
            execution_event_id=execution_event_id,
        )

        existing = _find_existing_verification(
            connection,
            action_id=action.id,
            execution_event_id=execution_event_id,
        )
        if existing is not None:
            return ProcessRunVerificationReceipt(
                action=action,
                verification=existing,
                created=False,
            )

        plan_verification_intent = _plan_verification_intent(action)
        observed["verification_type"] = VERIFICATION_TYPE
        observed["execution_event_id"] = execution_event_id
        observed["plan_verification_intent"] = plan_verification_intent
        observed["semantic_effect_assessed"] = False

        verification = create_verification_result_in_connection(
            connection,
            subject_type="ACTION",
            subject_id=action.id,
            criteria=(
                {
                    "type": VERIFICATION_TYPE,
                    "description": (
                        "A execução process.run terminou e produziu um resultado técnico "
                        "observável e estruturalmente consistente."
                    ),
                },
            ),
            status="VERIFIED",
            evidence_event_ids=(execution_event_id,),
            observed=observed,
            strength=VERIFICATION_STRENGTH,
        )
        return ProcessRunVerificationReceipt(
            action=action,
            verification=verification,
            created=True,
        )


def _validate_action(action: Action) -> None:
    if action.kind != "process.run":
        raise ValueError(f"action não representa process.run: {action.id}")
    if action.status != "COMPLETED":
        raise ValueError(
            "verificação process.run exige Action COMPLETED: "
            f"{action.id} está {action.status}"
        )


def _ensure_latest_step_attempt(connection: sqlite3.Connection, action: Action) -> None:
    row = connection.execute(
        """
        SELECT id
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (action.plan_id, action.step_id),
    ).fetchone()
    if row is None or str(row[0]) != action.id:
        raise ValueError("verificação exige a tentativa mais recente do step")


def _execution_event_id(action: Action) -> str:
    if action.reported_result is None:
        raise ValueError(f"Action process.run não possui resultado reportado: {action.id}")
    value = action.reported_result.get("execution_event_id")
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Action process.run possui execution_event_id inválido: {action.id}")
    return value.strip()


def _plan_verification_intent(action: Action) -> str:
    value = action.input_data.get("verification")
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Action process.run possui critério do Plan inválido: {action.id}")
    return value.strip()


def _execution_observation(
    connection: sqlite3.Connection,
    *,
    action: Action,
    execution_event_id: str,
) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT kind, source, payload_json, goal_id
        FROM events
        WHERE id = ?
        """,
        (execution_event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Event de execução não encontrado: {execution_event_id}")
    if str(row[0]) != "process.execution.completed" or str(row[1]) != "tool":
        raise ValueError(
            f"Event não representa execução process.run concluída: {execution_event_id}"
        )
    if row[3] is None or str(row[3]) != action.goal_id:
        raise ValueError("Event de execução não pertence ao Goal da Action")

    payload = json.loads(str(row[2]))
    if not isinstance(payload, dict):
        raise TypeError(f"Event de execução possui payload inválido: {execution_event_id}")

    if payload.get("action_id") != action.id:
        raise ValueError("Event de execução não pertence à Action informada")
    if payload.get("plan_id") != action.plan_id:
        raise ValueError("Event de execução não pertence ao Plan da Action")
    if payload.get("step_id") != action.step_id:
        raise ValueError("Event de execução não pertence ao step da Action")

    exit_code = payload.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise TypeError("Event de execução possui exit_code inválido")

    stdout = payload.get("stdout")
    stderr = payload.get("stderr")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise TypeError("Event de execução possui stdout/stderr inválido")

    duration_seconds = payload.get("duration_seconds")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or duration_seconds < 0
    ):
        raise TypeError("Event de execução possui duração inválida")

    reported_result = action.reported_result
    if reported_result is None:
        raise ValueError(f"Action process.run não possui resultado reportado: {action.id}")
    if reported_result.get("exit_code") != exit_code:
        raise ValueError("Action e Event divergem sobre o exit_code")

    reported_duration = reported_result.get("duration_seconds")
    if isinstance(reported_duration, bool) or not isinstance(reported_duration, (int, float)):
        raise TypeError("Action process.run possui duração reportada inválida")
    if float(reported_duration) != float(duration_seconds):
        raise ValueError("Action e Event divergem sobre a duração da execução")

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": float(duration_seconds),
    }


def _find_existing_verification(
    connection: sqlite3.Connection,
    *,
    action_id: str,
    execution_event_id: str,
) -> VerificationResult | None:
    results = list_verification_results_in_connection(
        connection,
        subject_type="ACTION",
        subject_id=action_id,
    )
    for result in reversed(results):
        if result.status != "VERIFIED":
            continue
        if result.observed.get("verification_type") != VERIFICATION_TYPE:
            continue
        if result.observed.get("execution_event_id") != execution_event_id:
            continue
        return result
    return None
