from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from simon.actions import (
    Action,
    create_action_in_connection,
    get_action_in_connection,
    transition_action_in_connection,
)
from simon.events import Event
from simon.step_readiness import evaluate_active_plan


@dataclass(frozen=True, slots=True)
class UserAskDispatch:
    action: Action
    prompt: str
    created: bool


@dataclass(frozen=True, slots=True)
class UserAnswerReceipt:
    action: Action
    response_event_id: str


def dispatch_next_user_ask(
    database_path: Path,
    *,
    goal_id: str,
    trace_id: str | None = None,
) -> UserAskDispatch:
    readiness = evaluate_active_plan(database_path, goal_id=goal_id)
    existing = _get_waiting_user_ask(database_path, readiness.plan.id)
    if existing is not None:
        return UserAskDispatch(
            action=existing,
            prompt=_prompt_from_action(existing),
            created=False,
        )

    step = readiness.next_step
    if step is None:
        raise ValueError("plan não possui step READY para iniciar")
    if step.capability != "user.ask":
        raise ValueError(
            "próximo step READY não usa a capability user.ask: "
            f"{step.step_id} ({step.capability or 'não especificada'})"
        )

    prompt = step.description
    verification = _step_verification(readiness.plan.steps, step.step_id)
    interaction_trace_id = trace_id or f"trc_{uuid4().hex}"

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing = _get_waiting_user_ask_in_connection(connection, readiness.plan.id)
        if existing is not None:
            return UserAskDispatch(
                action=existing,
                prompt=_prompt_from_action(existing),
                created=False,
            )

        action = create_action_in_connection(
            connection,
            goal_id=readiness.plan.goal_id,
            plan_id=readiness.plan.id,
            step_id=step.step_id,
            kind="user.ask",
            input_data={
                "prompt": prompt,
                "verification": verification,
            },
        )
        waiting = transition_action_in_connection(
            connection,
            action.id,
            "WAITING",
        )
        event = Event.create(
            kind="user.question.asked",
            source="system",
            payload={
                "action_id": waiting.id,
                "plan_id": waiting.plan_id,
                "step_id": waiting.step_id,
                "prompt": prompt,
            },
            trace_id=interaction_trace_id,
            goal_id=waiting.goal_id,
        )
        _insert_event(connection, event)

    return UserAskDispatch(action=waiting, prompt=prompt, created=True)


def answer_user_ask(
    database_path: Path,
    *,
    action_id: str,
    response: str,
    trace_id: str | None = None,
) -> UserAnswerReceipt:
    normalized_response = response.strip()
    if not normalized_response:
        raise ValueError("resposta do usuário não pode ser vazia")

    interaction_trace_id = trace_id or f"trc_{uuid4().hex}"

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        action = get_action_in_connection(connection, action_id)
        if action is None:
            raise ValueError(f"action não encontrada: {action_id}")
        if action.kind != "user.ask":
            raise ValueError(f"action não representa user.ask: {action_id}")
        if action.status != "WAITING":
            raise ValueError(
                "resposta exige action user.ask em WAITING: "
                f"{action_id} está {action.status}"
            )

        response_event = Event.create(
            kind="user.response.received",
            source="user",
            payload={
                "action_id": action.id,
                "plan_id": action.plan_id,
                "step_id": action.step_id,
                "response": normalized_response,
            },
            trace_id=interaction_trace_id,
            goal_id=action.goal_id,
        )
        _insert_event(connection, response_event)
        completed = transition_action_in_connection(
            connection,
            action.id,
            "COMPLETED",
            reported_result={"response_event_id": response_event.id},
        )

    return UserAnswerReceipt(
        action=completed,
        response_event_id=response_event.id,
    )


def _get_waiting_user_ask(database_path: Path, plan_id: str) -> Action | None:
    with sqlite3.connect(database_path) as connection:
        return _get_waiting_user_ask_in_connection(connection, plan_id)


def _get_waiting_user_ask_in_connection(
    connection: sqlite3.Connection,
    plan_id: str,
) -> Action | None:
    rows = connection.execute(
        """
        SELECT id
        FROM actions
        WHERE plan_id = ? AND kind = 'user.ask' AND status = 'WAITING'
        ORDER BY created_at, id
        """,
        (plan_id,),
    ).fetchall()
    if len(rows) > 1:
        raise RuntimeError(f"plan possui múltiplas user.ask em WAITING: {plan_id}")
    if not rows:
        return None
    return get_action_in_connection(connection, str(rows[0][0]))


def _prompt_from_action(action: Action) -> str:
    prompt = action.input_data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise TypeError(f"action user.ask possui prompt inválido: {action.id}")
    return prompt.strip()


def _step_verification(
    steps: tuple[dict[str, object], ...],
    step_id: str,
) -> str | None:
    for step in steps:
        if step.get("id") != step_id:
            continue
        verification = step.get("verification")
        if verification is None:
            return None
        if not isinstance(verification, str):
            raise TypeError(f"verification persistida possui tipo inválido: {step_id}")
        normalized = verification.strip()
        return normalized or None
    raise ValueError(f"step não encontrado no Plan persistido: {step_id}")


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
