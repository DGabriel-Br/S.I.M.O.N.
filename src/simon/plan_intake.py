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
            (
                proposal,
                goal_id,
                proposal_trace_id,
                proposal_model,
                proposal_payload,
            ) = _load_proposal(
                connection,
                normalized_event_id,
            )
            _validate_replanning_source(
                connection,
                goal_id=goal_id,
                payload=proposal_payload,
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
                    "source_active_plan_id": proposal_payload.get("source_active_plan_id"),
                    "source_failure_verification_id": proposal_payload.get(
                        "source_failure_verification_id"
                    ),
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
) -> tuple[PlanProposal, str, str | None, str | None, dict[str, object]]:
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
    return proposal, str(row[3]), proposal_trace_id, proposal_model, payload


def _validate_replanning_source(
    connection: sqlite3.Connection,
    *,
    goal_id: str,
    payload: dict[str, object],
) -> None:
    field_names = (
        "source_active_plan_id",
        "source_active_plan_revision",
        "source_failure_step_id",
        "source_failure_action_id",
        "source_failure_verification_id",
        "source_failure_blocker_kind",
    )
    values = {name: payload.get(name) for name in field_names}
    if all(value is None for value in values.values()):
        return
    if any(value is None for value in values.values()):
        raise ValueError("proposta de replanejamento possui proveniência incompleta")

    plan_id = _required_source_text(values["source_active_plan_id"], "source_active_plan_id")
    step_id = _required_source_text(values["source_failure_step_id"], "source_failure_step_id")
    action_id = _required_source_text(values["source_failure_action_id"], "source_failure_action_id")
    verification_id = _required_source_text(
        values["source_failure_verification_id"],
        "source_failure_verification_id",
    )
    blocker_kind = _required_source_text(
        values["source_failure_blocker_kind"],
        "source_failure_blocker_kind",
    )
    revision = values["source_active_plan_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise TypeError("source_active_plan_revision inválida")

    plan_row = connection.execute(
        "SELECT goal_id, revision, status FROM plans WHERE id = ?",
        (plan_id,),
    ).fetchone()
    if plan_row is None:
        raise ValueError(f"Plan fonte do replanejamento não encontrado: {plan_id}")
    if str(plan_row[0]) != goal_id:
        raise ValueError("Plan fonte do replanejamento pertence a outro Goal")
    if plan_row[1] != revision:
        raise ValueError("revisão do Plan fonte mudou ou diverge da proposta")
    if str(plan_row[2]) != "ACTIVE":
        raise ValueError("Plan fonte do replanejamento não está mais ACTIVE")

    action_row = connection.execute(
        "SELECT plan_id, step_id, status FROM actions WHERE id = ?",
        (action_id,),
    ).fetchone()
    if action_row is None:
        raise ValueError(f"Action fonte do replanejamento não encontrada: {action_id}")
    if str(action_row[0]) != plan_id or str(action_row[1]) != step_id:
        raise ValueError("Action fonte não pertence ao Plan/step registrados")
    if str(action_row[2]) != "COMPLETED":
        raise ValueError("Action fonte do replanejamento não está COMPLETED")

    latest_action = connection.execute(
        """
        SELECT id
        FROM actions
        WHERE plan_id = ? AND step_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (plan_id, step_id),
    ).fetchone()
    if latest_action is None or str(latest_action[0]) != action_id:
        raise ValueError("proposta de replanejamento ficou obsoleta por nova tentativa do step")

    verification_row = connection.execute(
        """
        SELECT subject_type, subject_id, status, observed_json
        FROM verification_results
        WHERE id = ?
        """,
        (verification_id,),
    ).fetchone()
    if verification_row is None:
        raise ValueError(
            f"Verification fonte do replanejamento não encontrada: {verification_id}"
        )
    if str(verification_row[0]) != "ACTION" or str(verification_row[1]) != action_id:
        raise ValueError("Verification fonte não pertence à Action registrada")

    latest_verification = connection.execute(
        """
        SELECT id
        FROM verification_results
        WHERE subject_type = 'ACTION' AND subject_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (action_id,),
    ).fetchone()
    if latest_verification is None or str(latest_verification[0]) != verification_id:
        raise ValueError("proposta de replanejamento ficou obsoleta por nova Verification")

    observed = json.loads(str(verification_row[3]))
    if not isinstance(observed, dict):
        raise TypeError("Verification fonte possui observed inválido")
    _validate_source_failure_status(
        blocker_kind=blocker_kind,
        verification_status=str(verification_row[2]),
        observed=observed,
    )


def _required_source_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} inválido")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} vazio")
    return normalized


def _validate_source_failure_status(
    *,
    blocker_kind: str,
    verification_status: str,
    observed: dict[str, object],
) -> None:
    if blocker_kind == "VERIFICATION_FAILED" and verification_status == "FAILED":
        return
    if blocker_kind == "VERIFICATION_INCONCLUSIVE" and verification_status == "INCONCLUSIVE":
        return
    if (
        blocker_kind == "CRITERION_NOT_SATISFIED"
        and verification_status == "ASSESSED"
        and observed.get("verdict") == "NOT_SATISFIED"
    ):
        return
    if (
        blocker_kind == "ASSESSMENT_INCONCLUSIVE"
        and verification_status == "ASSESSED"
        and observed.get("verdict") == "UNCLEAR"
    ):
        return
    raise ValueError("proveniência de replanejamento não corresponde mais à falha registrada")


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
