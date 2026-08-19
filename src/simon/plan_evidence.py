from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from simon.actions import Action, get_latest_action_for_step_in_connection
from simon.verification import VerificationResult, get_latest_verification_result_in_connection


@dataclass(frozen=True, slots=True)
class CurrentVerifiedStep:
    step_id: str
    action: Action
    verification: VerificationResult


def completion_action_ids(
    payload: dict[str, object],
    *,
    steps: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    persisted_step_ids = _required_text_list(
        payload,
        "verified_step_ids",
    )
    action_ids = _required_text_list(
        payload,
        "verified_action_ids",
    )
    expected_step_ids = tuple(_step_id(step) for step in steps)
    if persisted_step_ids != expected_step_ids:
        raise RuntimeError("plan.completed não preserva os steps do Plan na ordem original")
    if len(action_ids) != len(expected_step_ids):
        raise RuntimeError("plan.completed não preserva uma Action verificada por step")
    return action_ids


def require_current_verified_steps_in_connection(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    steps: tuple[dict[str, object], ...],
    expected_action_ids: tuple[str, ...] | None = None,
) -> tuple[CurrentVerifiedStep, ...]:
    if expected_action_ids is not None and len(expected_action_ids) != len(steps):
        raise ValueError("quantidade de Actions esperadas diverge dos steps do Plan")

    verified: list[CurrentVerifiedStep] = []
    for index, step in enumerate(steps):
        step_id = _step_id(step)
        action = get_latest_action_for_step_in_connection(
            connection,
            plan_id=plan_id,
            step_id=step_id,
        )
        if action is None:
            raise RuntimeError(f"step não possui tentativa persistida: {step_id}")
        if expected_action_ids is not None and action.id != expected_action_ids[index]:
            raise RuntimeError(
                f"tentativa atual de {step_id} diverge da Action registrada em plan.completed"
            )
        if action.status != "COMPLETED":
            raise RuntimeError(
                f"tentativa atual de {step_id} não está COMPLETED: {action.status}"
            )

        verification = get_latest_verification_result_in_connection(
            connection,
            subject_type="ACTION",
            subject_id=action.id,
        )
        if verification is None:
            raise RuntimeError(f"tentativa atual de {step_id} não possui Verification")
        if verification.status != "VERIFIED":
            raise RuntimeError(
                f"Verification atual de {step_id} não está VERIFIED: {verification.status}"
            )
        verified.append(
            CurrentVerifiedStep(
                step_id=step_id,
                action=action,
                verification=verification,
            )
        )
    return tuple(verified)


def _required_text_list(payload: dict[str, object], key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"plan.completed possui {key} inválido")
    values: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"plan.completed possui {key} inválido")
        values.append(value.strip())
    return tuple(values)


def _step_id(step: dict[str, object]) -> str:
    value = step.get("id")
    if not isinstance(value, str):
        raise TypeError("step persistido possui id com tipo inválido")
    normalized = value.strip()
    if not normalized:
        raise ValueError("step persistido possui id vazio")
    return normalized
