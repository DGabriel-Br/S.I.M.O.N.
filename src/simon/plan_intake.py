from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from simon.events import Event
from simon.planning import PlanProposal
from simon.plans import Plan, create_plan_in_connection, get_plan


@dataclass(frozen=True, slots=True)
class PlanMaterialization:
    plan: Plan
    created: bool


def materialize_plan_proposal(
    database_path: Path,
    proposal_event_id: str,
    *,
    trace_id: str | None = None,
) -> PlanMaterialization:
    normalized_event_id = proposal_event_id.strip()
    if not normalized_event_id:
        raise ValueError("ID do Event de proposta não pode ser vazio")

    materialization_trace_id = trace_id or f"trc_{uuid4().hex}"
    existing_plan_id: str | None = None
    created_plan: Plan | None = None

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing_plan_id = _find_existing_materialization(connection, normalized_event_id)
        if existing_plan_id is None:
            proposal, goal_id, proposal_trace_id, proposal_model = _load_proposal(
                connection,
                normalized_event_id,
            )
            steps = tuple(step.model_dump(mode="json") for step in proposal.steps)
            created_plan = create_plan_in_connection(
                connection,
                goal_id=goal_id,
                steps=steps,
            )
            materialization_event = Event.create(
                kind="plan.proposal.materialized",
                source="system",
                payload={
                    "proposal_event_id": normalized_event_id,
                    "proposal_trace_id": proposal_trace_id,
                    "proposal_model": proposal_model,
                    "summary": proposal.summary,
                    "open_questions": proposal.open_questions,
                    "plan_id": created_plan.id,
                    "plan_revision": created_plan.revision,
                },
                trace_id=materialization_trace_id,
                goal_id=goal_id,
            )
            _insert_event(connection, materialization_event)

    if existing_plan_id is not None:
        existing_plan = get_plan(database_path, existing_plan_id)
        if existing_plan is None:
            raise RuntimeError(
                "materialização existente referencia um Plan que não está mais disponível: "
                f"{existing_plan_id}"
            )
        return PlanMaterialization(plan=existing_plan, created=False)

    if created_plan is None:
        raise RuntimeError("materialização de Plan terminou sem criar ou recuperar um Plan")
    return PlanMaterialization(plan=created_plan, created=True)


def _find_existing_materialization(
    connection: sqlite3.Connection,
    proposal_event_id: str,
) -> str | None:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM events
        WHERE kind = 'plan.proposal.materialized'
        ORDER BY occurred_at, id
        """
    ).fetchall()

    for (payload_json,) in rows:
        payload = json.loads(str(payload_json))
        if not isinstance(payload, dict):
            continue
        if payload.get("proposal_event_id") != proposal_event_id:
            continue
        plan_id = payload.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            raise TypeError(
                "materialização de Plan possui plan_id inválido para a proposta: "
                f"{proposal_event_id}"
            )
        return plan_id
    return None


def _load_proposal(
    connection: sqlite3.Connection,
    proposal_event_id: str,
) -> tuple[PlanProposal, str, str | None, str | None]:
    row = connection.execute(
        """
        SELECT kind, payload_json, trace_id, goal_id
        FROM events
        WHERE id = ?
        """,
        (proposal_event_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"Event de proposta não encontrado: {proposal_event_id}")
    if str(row[0]) != "cognition.plan_proposal.completed":
        raise ValueError(
            "Event não representa uma proposta de Plan concluída: "
            f"{proposal_event_id}"
        )
    if row[3] is None:
        raise ValueError(f"proposta de Plan não possui Goal associado: {proposal_event_id}")

    payload = json.loads(str(row[1]))
    if not isinstance(payload, dict):
        raise TypeError(f"payload de proposta inválido: {proposal_event_id}")

    raw_proposal = payload.get("proposal")
    try:
        proposal = PlanProposal.model_validate(raw_proposal)
    except ValidationError as exc:
        message = f"proposta armazenada não respeita o contrato: {proposal_event_id}"
        raise ValueError(message) from exc

    proposal_trace_id = str(row[2]) if row[2] is not None else None
    raw_model = payload.get("model")
    proposal_model = str(raw_model) if isinstance(raw_model, str) else None
    return proposal, str(row[3]), proposal_trace_id, proposal_model


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
