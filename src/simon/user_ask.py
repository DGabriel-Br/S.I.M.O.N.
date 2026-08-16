from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from simon.actions import (
    Action,
    create_action_in_connection,
    get_action,
    get_action_in_connection,
    transition_action_in_connection,
)
from simon.events import Event
from simon.step_readiness import evaluate_active_plan
from simon.verification import list_verification_results


@dataclass(frozen=True, slots=True)
class UserAskDispatch:
    action: Action
    prompt: str
    created: bool


@dataclass(frozen=True, slots=True)
class UserAnswerReceipt:
    action: Action
    response_event_id: str


@dataclass(frozen=True, slots=True)
class UserAskRetryDispatch:
    action: Action
    prompt: str
    retry_of_action_id: str
    review_verification_id: str
    created: bool


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



def retry_user_ask(
    database_path: Path,
    *,
    action_id: str,
    prompt: str | None = None,
    trace_id: str | None = None,
) -> UserAskRetryDispatch:
    original = _require_retryable_user_ask(database_path, action_id)
    existing = _get_retry_waiting_for_action(database_path, original)
    review = _latest_retryable_assessment(database_path, original.id)
    if existing is not None:
        return UserAskRetryDispatch(
            action=existing,
            prompt=_prompt_from_action(existing),
            retry_of_action_id=original.id,
            review_verification_id=review[0],
            created=False,
        )

    retry_prompt = _normalize_retry_prompt(prompt, original)
    verification = _step_verification_for_action(original)
    interaction_trace_id = trace_id or f"trc_{uuid4().hex}"

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = get_action_in_connection(connection, original.id)
        if current is None:
            raise ValueError(f"action não encontrada: {original.id}")
        if current.status != "COMPLETED":
            raise ValueError(
                "retry exige action user.ask COMPLETED: "
                f"{original.id} está {current.status}"
            )

        _ensure_latest_step_attempt(connection, current)
        waiting = _get_waiting_user_ask_in_connection(connection, current.plan_id)
        if waiting is not None:
            retry_of = waiting.input_data.get("retry_of_action_id")
            if waiting.step_id == current.step_id and retry_of == current.id:
                return UserAskRetryDispatch(
                    action=waiting,
                    prompt=_prompt_from_action(waiting),
                    retry_of_action_id=current.id,
                    review_verification_id=review[0],
                    created=False,
                )
            raise ValueError(
                "plan já possui outra user.ask aguardando resposta: "
                f"{waiting.id} ({waiting.step_id})"
            )

        review_verification_id, verdict = _latest_retryable_assessment_in_connection(
            connection,
            current.id,
        )
        authorization_event = Event.create(
            kind="action.retry.authorized",
            source="user",
            payload={
                "retry_of_action_id": current.id,
                "review_verification_id": review_verification_id,
                "review_verdict": verdict,
                "plan_id": current.plan_id,
                "step_id": current.step_id,
                "prompt_overridden": prompt is not None,
            },
            trace_id=interaction_trace_id,
            goal_id=current.goal_id,
        )
        action = create_action_in_connection(
            connection,
            goal_id=current.goal_id,
            plan_id=current.plan_id,
            step_id=current.step_id,
            kind="user.ask",
            input_data={
                "prompt": retry_prompt,
                "verification": verification,
                "retry_of_action_id": current.id,
                "review_verification_id": review_verification_id,
                "retry_authorization_event_id": authorization_event.id,
            },
        )
        waiting = transition_action_in_connection(connection, action.id, "WAITING")
        authorization_event = Event(
            id=authorization_event.id,
            kind=authorization_event.kind,
            occurred_at=authorization_event.occurred_at,
            source=authorization_event.source,
            payload={
                **authorization_event.payload,
                "retry_action_id": waiting.id,
            },
            trace_id=authorization_event.trace_id,
            related_entity_ids=authorization_event.related_entity_ids,
            goal_id=authorization_event.goal_id,
            experience_id=authorization_event.experience_id,
        )
        _insert_event(connection, authorization_event)
        question_event = Event.create(
            kind="user.question.asked",
            source="system",
            payload={
                "action_id": waiting.id,
                "plan_id": waiting.plan_id,
                "step_id": waiting.step_id,
                "prompt": retry_prompt,
                "retry_of_action_id": current.id,
                "retry_authorization_event_id": authorization_event.id,
            },
            trace_id=interaction_trace_id,
            goal_id=waiting.goal_id,
        )
        _insert_event(connection, question_event)

    return UserAskRetryDispatch(
        action=waiting,
        prompt=retry_prompt,
        retry_of_action_id=original.id,
        review_verification_id=review_verification_id,
        created=True,
    )



def _require_retryable_user_ask(database_path: Path, action_id: str) -> Action:
    action = get_action(database_path, action_id)
    if action is None:
        raise ValueError(f"action não encontrada: {action_id}")
    if action.kind != "user.ask":
        raise ValueError(f"action não representa user.ask: {action_id}")
    if action.status != "COMPLETED":
        raise ValueError(
            "retry exige action user.ask COMPLETED: "
            f"{action_id} está {action.status}"
        )
    _latest_retryable_assessment(database_path, action.id)
    return action


def _latest_retryable_assessment(
    database_path: Path,
    action_id: str,
) -> tuple[str, str]:
    results = list_verification_results(
        database_path,
        subject_type="ACTION",
        subject_id=action_id,
    )
    for result in reversed(results):
        if result.status != "ASSESSED":
            continue
        if result.observed.get("assessment_type") != "user.ask.semantic":
            continue
        verdict = result.observed.get("verdict")
        if verdict in {"NOT_SATISFIED", "UNCLEAR"}:
            return result.id, str(verdict)
        if verdict == "SATISFIED":
            raise ValueError(
                "retry não é permitido após assessment SATISFIED; "
                "a evidência exige confirmação"
            )
    raise ValueError(
        "retry exige assessment ASSESSED com veredito NOT_SATISFIED ou UNCLEAR"
    )


def _latest_retryable_assessment_in_connection(
    connection: sqlite3.Connection,
    action_id: str,
) -> tuple[str, str]:
    rows = connection.execute(
        """
        SELECT id, status, observed_json
        FROM verification_results
        WHERE subject_type = 'ACTION' AND subject_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (action_id,),
    ).fetchall()
    for row in rows:
        if str(row[1]) != "ASSESSED":
            continue
        observed = json.loads(str(row[2]))
        if not isinstance(observed, dict):
            raise TypeError(f"observed de Verification inválido: {row[0]}")
        if observed.get("assessment_type") != "user.ask.semantic":
            continue
        verdict = observed.get("verdict")
        if verdict in {"NOT_SATISFIED", "UNCLEAR"}:
            return str(row[0]), str(verdict)
        if verdict == "SATISFIED":
            raise ValueError(
                "retry não é permitido após assessment SATISFIED; "
                "a evidência exige confirmação"
            )
    raise ValueError(
        "retry exige assessment ASSESSED com veredito NOT_SATISFIED ou UNCLEAR"
    )


def _get_retry_waiting_for_action(database_path: Path, original: Action) -> Action | None:
    with sqlite3.connect(database_path) as connection:
        waiting = _get_waiting_user_ask_in_connection(connection, original.plan_id)
    if waiting is None or waiting.step_id != original.step_id:
        return None
    retry_of = waiting.input_data.get("retry_of_action_id")
    return waiting if retry_of == original.id else None


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
    if row is None:
        raise RuntimeError(f"step não possui tentativa persistida: {action.step_id}")
    if str(row[0]) != action.id:
        raise ValueError(
            "retry exige a tentativa mais recente do step; "
            f"a action {action.id} já foi sucedida por {row[0]}"
        )


def _normalize_retry_prompt(prompt: str | None, original: Action) -> str:
    if prompt is None:
        return _prompt_from_action(original)
    normalized = prompt.strip()
    if not normalized:
        raise ValueError("prompt de retry não pode ser vazio")
    return normalized


def _step_verification_for_action(action: Action) -> str:
    value = action.input_data.get("verification")
    if not isinstance(value, str):
        raise TypeError(f"action user.ask possui verification inválida: {action.id}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"action user.ask possui verification vazia: {action.id}")
    return normalized


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
