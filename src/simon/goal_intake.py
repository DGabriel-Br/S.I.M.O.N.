from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from simon.cognition import GoalProposal
from simon.events import Event, get_event
from simon.goals import Goal, get_goal


@dataclass(frozen=True, slots=True)
class GoalAcceptance:
    goal: Goal
    created: bool


@dataclass(frozen=True, slots=True)
class GoalRejection:
    event: Event
    created: bool


def accept_goal_proposal(
    database_path: Path,
    proposal_event_id: str,
    *,
    trace_id: str | None = None,
) -> GoalAcceptance:
    normalized_event_id = proposal_event_id.strip()
    if not normalized_event_id:
        raise ValueError("ID do Event de proposta não pode ser vazio")

    acceptance_trace_id = trace_id or f"trc_{uuid4().hex}"
    existing_goal_id: str | None = None
    created_goal: Goal | None = None

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing_goal_id = _find_existing_acceptance(connection, normalized_event_id)
        if existing_goal_id is None:
            if _find_existing_rejection(connection, normalized_event_id) is not None:
                raise ValueError(
                    f"proposta de Goal já foi rejeitada: {normalized_event_id}"
                )
            proposal, proposal_trace_id, proposal_model = _load_proposal(
                connection,
                normalized_event_id,
            )
            created_goal = Goal.create(
                title=proposal.title,
                origin="USER",
                desired_state={"description": proposal.desired_state},
                success_criteria=tuple(
                    {"description": criterion} for criterion in proposal.success_criteria
                ),
            )
            acceptance_event = Event.create(
                kind="goal.proposal.accepted",
                source="user",
                payload={
                    "proposal_event_id": normalized_event_id,
                    "proposal_trace_id": proposal_trace_id,
                    "proposal_model": proposal_model,
                    "open_questions": proposal.open_questions,
                },
                trace_id=acceptance_trace_id,
                goal_id=created_goal.id,
            )

            _insert_goal(connection, created_goal)
            _insert_event(connection, acceptance_event)

    if existing_goal_id is not None:
        existing_goal = get_goal(database_path, existing_goal_id)
        if existing_goal is None:
            raise RuntimeError(
                "aceitação existente referencia um Goal que não está mais disponível: "
                f"{existing_goal_id}"
            )
        return GoalAcceptance(goal=existing_goal, created=False)

    if created_goal is None:
        raise RuntimeError("aceitação de Goal terminou sem criar ou recuperar um Goal")
    return GoalAcceptance(goal=created_goal, created=True)


def reject_goal_proposal(
    database_path: Path,
    proposal_event_id: str,
    *,
    trace_id: str | None = None,
) -> GoalRejection:
    normalized_event_id = proposal_event_id.strip()
    if not normalized_event_id:
        raise ValueError("ID do Event de proposta não pode ser vazio")

    rejection_trace_id = trace_id or f"trc_{uuid4().hex}"
    existing_rejection_id: str | None = None
    rejection_event: Event | None = None

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        if _find_existing_acceptance(connection, normalized_event_id) is not None:
            raise ValueError(
                f"proposta de Goal já foi aceita: {normalized_event_id}"
            )

        existing_rejection_id = _find_existing_rejection(connection, normalized_event_id)
        if existing_rejection_id is None:
            _, proposal_trace_id, proposal_model = _load_proposal(
                connection,
                normalized_event_id,
            )
            rejection_event = Event.create(
                kind="goal.proposal.rejected",
                source="user",
                payload={
                    "proposal_event_id": normalized_event_id,
                    "proposal_trace_id": proposal_trace_id,
                    "proposal_model": proposal_model,
                },
                trace_id=rejection_trace_id,
            )
            _insert_event(connection, rejection_event)

    if existing_rejection_id is not None:
        existing_event = get_event(database_path, existing_rejection_id)
        if existing_event is None:
            raise RuntimeError(
                "rejeição existente referencia um Event que não está mais disponível: "
                f"{existing_rejection_id}"
            )
        return GoalRejection(event=existing_event, created=False)

    if rejection_event is None:
        raise RuntimeError("rejeição de Goal terminou sem criar ou recuperar um Event")
    return GoalRejection(event=rejection_event, created=True)


def find_latest_pending_conversational_goal_proposal(
    database_path: Path,
) -> Event | None:
    """Retorna somente a proposta conversacional mais recente, se ainda não respondida."""
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT proposal.id
            FROM events AS proposal
            INNER JOIN events AS turn
                ON turn.id = proposal.trace_id
               AND turn.kind = 'user.turn.received'
            WHERE proposal.kind = 'cognition.goal_proposal.completed'
            ORDER BY proposal.occurred_at DESC, proposal.id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None

        proposal_event_id = str(row[0])
        if _find_existing_acceptance(connection, proposal_event_id) is not None:
            return None
        if _find_existing_rejection(connection, proposal_event_id) is not None:
            return None

    event = get_event(database_path, proposal_event_id)
    if event is None:
        raise RuntimeError(
            f"proposta conversacional não está mais disponível: {proposal_event_id}"
        )
    return event


def _find_existing_acceptance(
    connection: sqlite3.Connection,
    proposal_event_id: str,
) -> str | None:
    rows = connection.execute(
        """
        SELECT goal_id, payload_json
        FROM events
        WHERE kind = 'goal.proposal.accepted'
          AND goal_id IS NOT NULL
        ORDER BY occurred_at, id
        """
    ).fetchall()

    for goal_id, payload_json in rows:
        payload = json.loads(str(payload_json))
        if isinstance(payload, dict) and payload.get("proposal_event_id") == proposal_event_id:
            return str(goal_id)
    return None


def _find_existing_rejection(
    connection: sqlite3.Connection,
    proposal_event_id: str,
) -> str | None:
    rows = connection.execute(
        """
        SELECT id, payload_json
        FROM events
        WHERE kind = 'goal.proposal.rejected'
        ORDER BY occurred_at, id
        """
    ).fetchall()

    for event_id, payload_json in rows:
        payload = json.loads(str(payload_json))
        if isinstance(payload, dict) and payload.get("proposal_event_id") == proposal_event_id:
            return str(event_id)
    return None


def _load_proposal(
    connection: sqlite3.Connection,
    proposal_event_id: str,
) -> tuple[GoalProposal, str | None, str | None]:
    row = connection.execute(
        """
        SELECT kind, payload_json, trace_id
        FROM events
        WHERE id = ?
        """,
        (proposal_event_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Event de proposta não encontrado: {proposal_event_id}")
    proposal_kind = str(row[0])
    if proposal_kind not in {
        "cognition.goal_proposal.completed",
        "attention.goal_proposal.completed",
    }:
        raise ValueError(
            "Event não representa uma proposta de Goal concluída: "
            f"{proposal_event_id}"
        )

    payload = json.loads(str(row[1]))
    if not isinstance(payload, dict):
        raise TypeError(f"payload de proposta inválido: {proposal_event_id}")

    raw_proposal = payload.get("proposal")
    try:
        proposal = GoalProposal.model_validate(raw_proposal)
    except ValidationError as exc:
        message = f"proposta armazenada não respeita o contrato: {proposal_event_id}"
        raise ValueError(message) from exc

    proposal_trace_id = str(row[2]) if row[2] is not None else None
    raw_model = payload.get("model")
    proposal_model = str(raw_model) if isinstance(raw_model, str) else None
    return proposal, proposal_trace_id, proposal_model


def _insert_goal(connection: sqlite3.Connection, goal: Goal) -> None:
    connection.execute(
        """
        INSERT INTO goals (
            id,
            title,
            origin,
            parent_goal_id,
            desired_state_json,
            success_criteria_json,
            status,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            goal.id,
            goal.title,
            goal.origin,
            goal.parent_goal_id,
            json.dumps(goal.desired_state, ensure_ascii=False, separators=(",", ":")),
            json.dumps(goal.success_criteria, ensure_ascii=False, separators=(",", ":")),
            goal.status,
            goal.created_at.isoformat(),
            goal.updated_at.isoformat(),
        ),
    )


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


def get_goal_acceptance_open_questions(
    database_path: Path,
    goal_id: str,
) -> tuple[str, ...]:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT payload_json
            FROM events
            WHERE kind = 'goal.proposal.accepted'
              AND goal_id = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1
            """,
            (goal_id,),
        ).fetchone()

    if row is None:
        return ()

    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise TypeError(f"payload de aceitação inválido para goal: {goal_id}")

    raw_questions = payload.get("open_questions", [])
    if not isinstance(raw_questions, list):
        raise TypeError(f"open_questions inválido para goal: {goal_id}")

    questions: list[str] = []
    for question in raw_questions:
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"open_questions inválido para goal: {goal_id}")
        questions.append(question.strip())
    return tuple(questions)
