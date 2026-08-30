import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from simon.entities import get_entity
from simon.events import Event, append_event, get_event
from simon.perception import get_observation
from simon.world import advance_world_revision_in_connection

ACTIVE = "ACTIVE"
TERMINAL_STATUSES = {"SUPERSEDED", "RETRACTED", "EXPIRED"}
PROPOSED_CLAIM_EVENT_KIND = "world.claim.proposed"
CLAIM_VALIDATION_EVENT_KIND = "world.claim.validation.completed"
CLAIM_ACCEPTED_EVENT_KIND = "world.claim.accepted"
CLAIM_EVIDENCE_BOUND_EVENT_KIND = "world.claim.evidence.bound"
CLAIM_CONFLICT_RESOLUTION_EVENT_KIND = "world.claim.conflict.resolution.proposed"
CLAIM_CONFLICT_RESOLUTION_APPLIED_EVENT_KIND = "world.claim.conflict.resolution.applied"
CLAIM_VALIDATION_OUTCOMES = {"READY", "DUPLICATE", "CONFLICT"}
CLAIM_CONFLICT_WINNER_KINDS = {"PROPOSED_CLAIM", "ACTIVE_CLAIM"}


@dataclass(frozen=True, slots=True)
class ProposedClaim:
    event: Event
    attention_event_id: str
    observation_event_id: str
    subject_id: str
    predicate: str
    value: object
    epistemic_status: str
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimValidation:
    event: Event
    proposed_claim_event_id: str
    outcome: str
    active_claim_ids: tuple[str, ...]
    matching_claim_ids: tuple[str, ...]
    conflicting_claim_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimAcceptance:
    claim: Claim
    event: Event
    created: bool


@dataclass(frozen=True, slots=True)
class ClaimEvidenceBinding:
    event: Event
    validation_event_id: str
    proposed_claim_event_id: str
    bound_claims: tuple[Claim, ...]
    evidence_event_ids_added: tuple[str, ...]
    created: bool


@dataclass(frozen=True, slots=True)
class ClaimConflictResolutionProposal:
    event: Event
    validation_event_id: str
    proposed_claim_event_id: str
    winner_kind: str
    winner_id: str
    expected_active_claim_ids: tuple[str, ...]
    matching_claim_ids: tuple[str, ...]
    conflicting_claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimConflictResolutionApplication:
    event: Event
    resolution_event_id: str
    validation_event_id: str
    proposed_claim_event_id: str
    winner_kind: str
    winner_claim: Claim
    superseded_claim_ids: tuple[str, ...]
    winner_claim_created: bool
    belief_store_changed: bool
    created: bool


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    subject_id: str
    predicate: str
    value: object
    epistemic_status: str
    valid_from: datetime | None
    valid_until: datetime | None
    learned_at: datetime
    evidence_event_ids: tuple[str, ...]
    status: str

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        predicate: str,
        value: object,
        epistemic_status: str,
        evidence_event_ids: tuple[str, ...] = (),
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> Claim:
        return cls(
            id=f"clm_{uuid4().hex}",
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            epistemic_status=epistemic_status,
            valid_from=valid_from,
            valid_until=valid_until,
            learned_at=datetime.now(UTC),
            evidence_event_ids=evidence_event_ids,
            status=ACTIVE,
        )


def propose_claim_from_attention(
    database_path: Path,
    *,
    attention_event_id: str,
    subject_id: str,
    predicate: str,
    value: object,
) -> ProposedClaim:
    """Cria uma Proposed Claim sem alterar o Belief Store nem a revisão do World."""
    normalized_subject_id = subject_id.strip()
    normalized_predicate = predicate.strip()
    if not normalized_subject_id:
        raise ValueError("proposed claim exige subject_id")
    if not normalized_predicate:
        raise ValueError("proposed claim exige predicate")
    if get_entity(database_path, normalized_subject_id) is None:
        raise ValueError(f"subject da proposed claim não encontrado: {normalized_subject_id}")

    attention_event = get_event(database_path, attention_event_id)
    if attention_event is None:
        raise ValueError(f"attention assessment não encontrado: {attention_event_id}")
    if attention_event.kind != "attention.assessed":
        raise ValueError(
            f"event não é um attention assessment: {attention_event_id} "
            f"({attention_event.kind})"
        )

    destination = attention_event.payload.get("destination")
    if destination != "UPDATE_WORLD":
        raise ValueError(
            "proposed claim exige attention assessment com destino UPDATE_WORLD"
        )
    effect_applied = attention_event.payload.get("effect_applied")
    if effect_applied is not False:
        raise ValueError("attention assessment não está disponível para proposed claim")

    observation_event_id = attention_event.payload.get("observation_event_id")
    if not isinstance(observation_event_id, str):
        raise TypeError(f"observation_event_id inválido no assessment: {attention_event_id}")
    observation = get_observation(database_path, observation_event_id)
    if observation is None:
        raise ValueError(f"observation não encontrada: {observation_event_id}")
    if normalized_subject_id not in observation.event.related_entity_ids:
        raise ValueError(
            "subject da proposed claim precisa estar relacionado à observation de origem"
        )

    # O mesmo contrato JSON do Belief Store deve valer antes de uma proposta avançar.
    json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    evidence_event_ids = (observation.event.id, attention_event.id)
    epistemic_status = "DIRECT_OBSERVATION"
    event = Event.create(
        kind=PROPOSED_CLAIM_EVENT_KIND,
        source="perception",
        payload={
            "attention_event_id": attention_event.id,
            "observation_event_id": observation.event.id,
            "subject_id": normalized_subject_id,
            "predicate": normalized_predicate,
            "value": value,
            "epistemic_status": epistemic_status,
            "evidence_event_ids": list(evidence_event_ids),
            "status": "PROPOSED",
            "effect_applied": False,
        },
        trace_id=attention_event.trace_id or observation.event.trace_id or observation.event.id,
        related_entity_ids=observation.event.related_entity_ids,
        goal_id=attention_event.goal_id,
    )
    append_event(database_path, event)
    return ProposedClaim(
        event=event,
        attention_event_id=attention_event.id,
        observation_event_id=observation.event.id,
        subject_id=normalized_subject_id,
        predicate=normalized_predicate,
        value=value,
        epistemic_status=epistemic_status,
        evidence_event_ids=evidence_event_ids,
    )


def get_proposed_claim(database_path: Path, event_id: str) -> ProposedClaim | None:
    event = get_event(database_path, event_id)
    if event is None:
        return None
    if event.kind != PROPOSED_CLAIM_EVENT_KIND:
        raise ValueError(f"event não é uma proposed claim: {event_id} ({event.kind})")

    attention_event_id = event.payload.get("attention_event_id")
    observation_event_id = event.payload.get("observation_event_id")
    subject_id = event.payload.get("subject_id")
    predicate = event.payload.get("predicate")
    epistemic_status = event.payload.get("epistemic_status")
    raw_evidence_event_ids = event.payload.get("evidence_event_ids")
    if not isinstance(attention_event_id, str):
        raise TypeError(f"attention_event_id inválido na proposed claim: {event_id}")
    if not isinstance(observation_event_id, str):
        raise TypeError(f"observation_event_id inválido na proposed claim: {event_id}")
    if not isinstance(subject_id, str):
        raise TypeError(f"subject_id inválido na proposed claim: {event_id}")
    if not isinstance(predicate, str):
        raise TypeError(f"predicate inválido na proposed claim: {event_id}")
    if not isinstance(epistemic_status, str):
        raise TypeError(f"epistemic_status inválido na proposed claim: {event_id}")
    if not isinstance(raw_evidence_event_ids, list) or not all(
        isinstance(item, str) for item in raw_evidence_event_ids
    ):
        raise TypeError(f"evidence_event_ids inválido na proposed claim: {event_id}")

    return ProposedClaim(
        event=event,
        attention_event_id=attention_event_id,
        observation_event_id=observation_event_id,
        subject_id=subject_id,
        predicate=predicate,
        value=event.payload.get("value"),
        epistemic_status=epistemic_status,
        evidence_event_ids=tuple(raw_evidence_event_ids),
    )


def validate_proposed_claim(
    database_path: Path,
    *,
    proposed_claim_event_id: str,
) -> ClaimValidation:
    """Classifica uma Proposed Claim contra o Belief Store sem aplicar efeito."""
    proposal = get_proposed_claim(database_path, proposed_claim_event_id)
    if proposal is None:
        raise ValueError(f"proposed claim não encontrada: {proposed_claim_event_id}")
    if proposal.event.payload.get("status") != "PROPOSED":
        raise ValueError("proposed claim não está disponível para validação")
    if proposal.event.payload.get("effect_applied") is not False:
        raise ValueError("proposed claim já possui efeito aplicado")

    active_claims = list_active_claims(
        database_path,
        subject_id=proposal.subject_id,
        predicate=proposal.predicate,
    )
    matching_claim_ids = tuple(
        claim.id
        for claim in active_claims
        if claim.value == proposal.value
        and claim.epistemic_status == proposal.epistemic_status
    )
    conflicting_claim_ids = tuple(
        claim.id
        for claim in active_claims
        if claim.id not in matching_claim_ids
    )
    active_claim_ids = tuple(claim.id for claim in active_claims)

    if conflicting_claim_ids:
        outcome = "CONFLICT"
        reasons = ("active_claim_conflict",)
    elif matching_claim_ids:
        outcome = "DUPLICATE"
        reasons = ("equivalent_active_claim",)
    else:
        outcome = "READY"
        reasons = ("no_active_claim",)

    event = Event.create(
        kind=CLAIM_VALIDATION_EVENT_KIND,
        source="world",
        payload={
            "proposed_claim_event_id": proposal.event.id,
            "outcome": outcome,
            "active_claim_ids": list(active_claim_ids),
            "matching_claim_ids": list(matching_claim_ids),
            "conflicting_claim_ids": list(conflicting_claim_ids),
            "reasons": list(reasons),
            "effect_applied": False,
        },
        trace_id=proposal.event.trace_id or proposal.event.id,
        related_entity_ids=proposal.event.related_entity_ids,
        goal_id=proposal.event.goal_id,
    )
    append_event(database_path, event)
    return ClaimValidation(
        event=event,
        proposed_claim_event_id=proposal.event.id,
        outcome=outcome,
        active_claim_ids=active_claim_ids,
        matching_claim_ids=matching_claim_ids,
        conflicting_claim_ids=conflicting_claim_ids,
        reasons=reasons,
    )


def get_claim_validation(database_path: Path, event_id: str) -> ClaimValidation | None:
    event = get_event(database_path, event_id)
    if event is None:
        return None
    if event.kind != CLAIM_VALIDATION_EVENT_KIND:
        raise ValueError(f"event não é uma claim validation: {event_id} ({event.kind})")

    proposed_claim_event_id = event.payload.get("proposed_claim_event_id")
    outcome = event.payload.get("outcome")
    raw_active_claim_ids = event.payload.get("active_claim_ids")
    raw_matching_claim_ids = event.payload.get("matching_claim_ids")
    raw_conflicting_claim_ids = event.payload.get("conflicting_claim_ids")
    raw_reasons = event.payload.get("reasons")
    if not isinstance(proposed_claim_event_id, str):
        raise TypeError(f"proposed_claim_event_id inválido na validation: {event_id}")
    if not isinstance(outcome, str) or outcome not in CLAIM_VALIDATION_OUTCOMES:
        raise TypeError(f"outcome inválido na claim validation: {event_id}")

    def _string_tuple(raw: object, field: str) -> tuple[str, ...]:
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise TypeError(f"{field} inválido na claim validation: {event_id}")
        return tuple(raw)

    return ClaimValidation(
        event=event,
        proposed_claim_event_id=proposed_claim_event_id,
        outcome=outcome,
        active_claim_ids=_string_tuple(raw_active_claim_ids, "active_claim_ids"),
        matching_claim_ids=_string_tuple(raw_matching_claim_ids, "matching_claim_ids"),
        conflicting_claim_ids=_string_tuple(
            raw_conflicting_claim_ids,
            "conflicting_claim_ids",
        ),
        reasons=_string_tuple(raw_reasons, "reasons"),
    )


def propose_claim_conflict_resolution(
    database_path: Path,
    *,
    validation_event_id: str,
    winner_id: str,
) -> ClaimConflictResolutionProposal:
    """Registra uma escolha humana de vencedor sem aplicar supersede no Belief Store."""
    normalized_validation_event_id = validation_event_id.strip()
    normalized_winner_id = winner_id.strip()
    if not normalized_validation_event_id:
        raise ValueError("conflict resolution exige validation_event_id")
    if not normalized_winner_id:
        raise ValueError("conflict resolution exige winner_id")

    validation = get_claim_validation(database_path, normalized_validation_event_id)
    if validation is None:
        raise ValueError(
            "conflict resolution exige world.claim.validation.completed existente: "
            f"{normalized_validation_event_id}"
        )
    if validation.event.source != "world":
        raise ValueError("claim validation não possui autoridade de origem esperada")
    if validation.outcome != "CONFLICT":
        raise ValueError(
            "conflict resolution exige validation CONFLICT; "
            f"outcome atual: {validation.outcome}"
        )
    if validation.event.payload.get("effect_applied") is not False:
        raise ValueError("claim validation já possui efeito aplicado")

    proposal = get_proposed_claim(database_path, validation.proposed_claim_event_id)
    if proposal is None:
        raise ValueError(
            f"proposed claim não encontrada: {validation.proposed_claim_event_id}"
        )
    if proposal.event.source != "perception":
        raise ValueError(
            "conflict resolution deste passo exige proposta originada em perception"
        )
    if proposal.epistemic_status != "DIRECT_OBSERVATION":
        raise ValueError(
            "conflict resolution deste passo exige epistemic_status DIRECT_OBSERVATION"
        )

    if normalized_winner_id == proposal.event.id:
        winner_kind = "PROPOSED_CLAIM"
    elif normalized_winner_id in validation.active_claim_ids:
        winner_kind = "ACTIVE_CLAIM"
    else:
        raise ValueError(
            "winner_id precisa referenciar a Proposed Claim ou uma Claim ACTIVE "
            "presente na validation CONFLICT"
        )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = _find_conflict_resolution_proposal_in_connection(
            connection,
            validation_event_id=normalized_validation_event_id,
        )
        if existing is not None:
            if existing.winner_id != normalized_winner_id:
                raise ValueError(
                    "validation CONFLICT já possui proposta de resolução diferente; "
                    "execute claim-validate novamente para uma nova decisão"
                )
            return existing

        current_rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (proposal.subject_id, proposal.predicate),
        ).fetchall()
        current_active_claim_ids = tuple(str(row[0]) for row in current_rows)
        if current_active_claim_ids != validation.active_claim_ids:
            raise ValueError(
                "Belief Store mudou após validation CONFLICT; "
                "execute claim-validate novamente"
            )

        event = Event.create(
            kind=CLAIM_CONFLICT_RESOLUTION_EVENT_KIND,
            source="user",
            payload={
                "validation_event_id": normalized_validation_event_id,
                "proposed_claim_event_id": proposal.event.id,
                "winner_kind": winner_kind,
                "winner_id": normalized_winner_id,
                "expected_active_claim_ids": list(validation.active_claim_ids),
                "matching_claim_ids": list(validation.matching_claim_ids),
                "conflicting_claim_ids": list(validation.conflicting_claim_ids),
                "authority": "USER_DECISION",
                "status": "PROPOSED",
                "effect_applied": False,
            },
            trace_id=validation.event.trace_id or proposal.event.trace_id or proposal.event.id,
            related_entity_ids=proposal.event.related_entity_ids,
            goal_id=proposal.event.goal_id,
        )
        _insert_event_in_connection(connection, event)

    return ClaimConflictResolutionProposal(
        event=event,
        validation_event_id=normalized_validation_event_id,
        proposed_claim_event_id=proposal.event.id,
        winner_kind=winner_kind,
        winner_id=normalized_winner_id,
        expected_active_claim_ids=validation.active_claim_ids,
        matching_claim_ids=validation.matching_claim_ids,
        conflicting_claim_ids=validation.conflicting_claim_ids,
    )


def get_claim_conflict_resolution_proposal(
    database_path: Path,
    event_id: str,
) -> ClaimConflictResolutionProposal | None:
    event = get_event(database_path, event_id)
    if event is None:
        return None
    if event.kind != CLAIM_CONFLICT_RESOLUTION_EVENT_KIND:
        raise ValueError(
            f"event não é uma conflict resolution proposal: {event_id} ({event.kind})"
        )

    validation_event_id = event.payload.get("validation_event_id")
    proposed_claim_event_id = event.payload.get("proposed_claim_event_id")
    winner_kind = event.payload.get("winner_kind")
    winner_id = event.payload.get("winner_id")
    raw_expected = event.payload.get("expected_active_claim_ids")
    raw_matching = event.payload.get("matching_claim_ids")
    raw_conflicting = event.payload.get("conflicting_claim_ids")
    if not isinstance(validation_event_id, str):
        raise TypeError(f"validation_event_id inválido na conflict resolution: {event_id}")
    if not isinstance(proposed_claim_event_id, str):
        raise TypeError(
            f"proposed_claim_event_id inválido na conflict resolution: {event_id}"
        )
    if not isinstance(winner_kind, str) or winner_kind not in CLAIM_CONFLICT_WINNER_KINDS:
        raise TypeError(f"winner_kind inválido na conflict resolution: {event_id}")
    if not isinstance(winner_id, str):
        raise TypeError(f"winner_id inválido na conflict resolution: {event_id}")

    def _string_tuple(raw: object, field: str) -> tuple[str, ...]:
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise TypeError(f"{field} inválido na conflict resolution: {event_id}")
        return tuple(raw)

    return ClaimConflictResolutionProposal(
        event=event,
        validation_event_id=validation_event_id,
        proposed_claim_event_id=proposed_claim_event_id,
        winner_kind=winner_kind,
        winner_id=winner_id,
        expected_active_claim_ids=_string_tuple(raw_expected, "expected_active_claim_ids"),
        matching_claim_ids=_string_tuple(raw_matching, "matching_claim_ids"),
        conflicting_claim_ids=_string_tuple(raw_conflicting, "conflicting_claim_ids"),
    )


def apply_claim_conflict_resolution(
    database_path: Path,
    *,
    resolution_event_id: str,
) -> ClaimConflictResolutionApplication:
    """Aplica uma resolução humana de CONFLICT sem inferir vencedor ou snapshot."""
    normalized_resolution_event_id = resolution_event_id.strip()
    if not normalized_resolution_event_id:
        raise ValueError("conflict resolution application exige resolution_event_id")

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing = _find_conflict_resolution_application_in_connection(
            connection,
            resolution_event_id=normalized_resolution_event_id,
        )
        if existing is not None:
            event, winner_claim_id = existing
            claim_row = connection.execute(
                _claim_select() + " WHERE id = ?",
                (winner_claim_id,),
            ).fetchone()
            if claim_row is None:
                raise RuntimeError(
                    "aplicação de conflito existente referencia Claim indisponível: "
                    f"{winner_claim_id}"
                )
            payload = event.payload
            return ClaimConflictResolutionApplication(
                event=event,
                resolution_event_id=normalized_resolution_event_id,
                validation_event_id=_required_payload_string(
                    payload, "validation_event_id", context="conflict resolution aplicada"
                ),
                proposed_claim_event_id=_required_payload_string(
                    payload,
                    "proposed_claim_event_id",
                    context="conflict resolution aplicada",
                ),
                winner_kind=_required_payload_string(
                    payload, "winner_kind", context="conflict resolution aplicada"
                ),
                winner_claim=_claim_from_row(claim_row),
                superseded_claim_ids=_string_tuple_from_payload(
                    payload, field="superseded_claim_ids"
                ),
                winner_claim_created=_required_payload_bool(
                    payload,
                    "winner_claim_created",
                    context="conflict resolution aplicada",
                ),
                belief_store_changed=_required_payload_bool(
                    payload,
                    "belief_store_changed",
                    context="conflict resolution aplicada",
                ),
                created=False,
            )

        resolution_row = connection.execute(
            """
            SELECT payload_json, trace_id, related_entity_ids_json, goal_id, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (normalized_resolution_event_id, CLAIM_CONFLICT_RESOLUTION_EVENT_KIND),
        ).fetchone()
        if resolution_row is None:
            raise ValueError(
                "conflict resolution application exige "
                "world.claim.conflict.resolution.proposed existente: "
                f"{normalized_resolution_event_id}"
            )
        if str(resolution_row[4]) != "user":
            raise ValueError("conflict resolution não possui autoridade de origem esperada")

        resolution_payload = json.loads(str(resolution_row[0]))
        if not isinstance(resolution_payload, dict):
            raise TypeError("payload da conflict resolution possui tipo inválido")
        if resolution_payload.get("authority") != "USER_DECISION":
            raise ValueError("conflict resolution não possui autoridade USER_DECISION")
        if resolution_payload.get("status") != "PROPOSED":
            raise ValueError("conflict resolution não está disponível para aplicação")
        if resolution_payload.get("effect_applied") is not False:
            raise ValueError("conflict resolution já possui efeito aplicado")

        validation_event_id = _required_payload_string(
            resolution_payload,
            "validation_event_id",
            context="conflict resolution",
        )
        proposed_claim_event_id = _required_payload_string(
            resolution_payload,
            "proposed_claim_event_id",
            context="conflict resolution",
        )
        winner_kind = _required_payload_string(
            resolution_payload,
            "winner_kind",
            context="conflict resolution",
        )
        winner_id = _required_payload_string(
            resolution_payload,
            "winner_id",
            context="conflict resolution",
        )
        if winner_kind not in CLAIM_CONFLICT_WINNER_KINDS:
            raise TypeError("conflict resolution possui winner_kind inválido")
        expected_active_claim_ids = _string_tuple_from_payload(
            resolution_payload,
            field="expected_active_claim_ids",
        )

        validation_row = connection.execute(
            """
            SELECT payload_json, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (validation_event_id, CLAIM_VALIDATION_EVENT_KIND),
        ).fetchone()
        if validation_row is None:
            raise ValueError(
                f"claim validation da resolução não encontrada: {validation_event_id}"
            )
        if str(validation_row[1]) != "world":
            raise ValueError("claim validation não possui autoridade de origem esperada")
        validation_payload = json.loads(str(validation_row[0]))
        if not isinstance(validation_payload, dict):
            raise TypeError("payload da claim validation possui tipo inválido")
        if validation_payload.get("outcome") != "CONFLICT":
            raise ValueError("conflict resolution application exige validation CONFLICT")
        if validation_payload.get("effect_applied") is not False:
            raise ValueError("claim validation já possui efeito aplicado")
        if validation_payload.get("proposed_claim_event_id") != proposed_claim_event_id:
            raise ValueError("conflict resolution diverge da Proposed Claim validada")
        validation_active_claim_ids = _string_tuple_from_payload(
            validation_payload,
            field="active_claim_ids",
        )
        if expected_active_claim_ids != validation_active_claim_ids:
            raise ValueError("conflict resolution diverge do snapshot da validation")

        proposal_row = connection.execute(
            """
            SELECT payload_json, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (proposed_claim_event_id, PROPOSED_CLAIM_EVENT_KIND),
        ).fetchone()
        if proposal_row is None:
            raise ValueError(f"proposed claim não encontrada: {proposed_claim_event_id}")
        if str(proposal_row[1]) != "perception":
            raise ValueError(
                "conflict resolution application exige proposta originada em perception"
            )
        proposal_payload = json.loads(str(proposal_row[0]))
        if not isinstance(proposal_payload, dict):
            raise TypeError("payload da proposed claim possui tipo inválido")
        subject_id = _required_payload_string(
            proposal_payload, "subject_id", context="proposed claim"
        )
        predicate = _required_payload_string(
            proposal_payload, "predicate", context="proposed claim"
        )
        epistemic_status = _required_payload_string(
            proposal_payload, "epistemic_status", context="proposed claim"
        )
        if epistemic_status != "DIRECT_OBSERVATION":
            raise ValueError(
                "conflict resolution application exige epistemic_status DIRECT_OBSERVATION"
            )
        raw_evidence_event_ids = proposal_payload.get("evidence_event_ids")
        if not isinstance(raw_evidence_event_ids, list) or not all(
            isinstance(item, str) for item in raw_evidence_event_ids
        ):
            raise TypeError("proposed claim não possui evidence_event_ids válidos")

        current_rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
        current_active_claim_ids = tuple(str(row[0]) for row in current_rows)
        if current_active_claim_ids != expected_active_claim_ids:
            raise ValueError(
                "Belief Store mudou após conflict resolution proposal; "
                "execute claim-validate novamente"
            )

        if winner_kind == "ACTIVE_CLAIM":
            if winner_id not in current_active_claim_ids:
                raise ValueError("Claim ACTIVE vencedora não pertence mais ao snapshot atual")
            winner_claim_id = winner_id
            superseded_claim_ids = tuple(
                claim_id for claim_id in current_active_claim_ids if claim_id != winner_id
            )
            winner_claim_created = False
        else:
            if winner_id != proposed_claim_event_id:
                raise ValueError("PROPOSED_CLAIM vencedora diverge da proposta validada")
            winner_claim_id = f"clm_{uuid4().hex}"
            superseded_claim_ids = current_active_claim_ids
            winner_claim_created = True

        belief_store_changed = winner_claim_created or bool(superseded_claim_ids)
        application_event = Event.create(
            kind=CLAIM_CONFLICT_RESOLUTION_APPLIED_EVENT_KIND,
            source="world",
            payload={
                "resolution_event_id": normalized_resolution_event_id,
                "validation_event_id": validation_event_id,
                "proposed_claim_event_id": proposed_claim_event_id,
                "winner_kind": winner_kind,
                "winner_id": winner_id,
                "winner_claim_id": winner_claim_id,
                "superseded_claim_ids": list(superseded_claim_ids),
                "winner_claim_created": winner_claim_created,
                "belief_store_changed": belief_store_changed,
                "authority": "USER_DECISION",
                "authority_event_id": normalized_resolution_event_id,
                "effect_applied": True,
            },
            trace_id=(
                str(resolution_row[1])
                if resolution_row[1] is not None
                else proposed_claim_event_id
            ),
            related_entity_ids=_string_tuple_from_json(
                resolution_row[2],
                field="related_entity_ids",
            ),
            goal_id=str(resolution_row[3]) if resolution_row[3] is not None else None,
        )

        for claim_id in superseded_claim_ids:
            cursor = connection.execute(
                """
                UPDATE claims
                SET status = 'SUPERSEDED'
                WHERE id = ? AND status = 'ACTIVE'
                """,
                (claim_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("snapshot mudou durante aplicação da conflict resolution")

        if winner_claim_created:
            evidence_event_ids = tuple(
                dict.fromkeys(
                    (
                        *raw_evidence_event_ids,
                        validation_event_id,
                        normalized_resolution_event_id,
                        application_event.id,
                    )
                )
            )
            winner_claim = Claim(
                id=winner_claim_id,
                subject_id=subject_id,
                predicate=predicate,
                value=proposal_payload.get("value"),
                epistemic_status=epistemic_status,
                valid_from=None,
                valid_until=None,
                learned_at=datetime.now(UTC),
                evidence_event_ids=evidence_event_ids,
                status=ACTIVE,
            )
            _insert_claim_in_connection(connection, winner_claim)
        else:
            winner_row = connection.execute(
                _claim_select() + " WHERE id = ? AND status = 'ACTIVE'",
                (winner_claim_id,),
            ).fetchone()
            if winner_row is None:
                raise RuntimeError(
                    f"Claim vencedora deixou de estar ACTIVE: {winner_claim_id}"
                )
            winner_claim = _claim_from_row(winner_row)

        _insert_event_in_connection(connection, application_event)
        if belief_store_changed:
            advance_world_revision_in_connection(connection)

    return ClaimConflictResolutionApplication(
        event=application_event,
        resolution_event_id=normalized_resolution_event_id,
        validation_event_id=validation_event_id,
        proposed_claim_event_id=proposed_claim_event_id,
        winner_kind=winner_kind,
        winner_claim=winner_claim,
        superseded_claim_ids=superseded_claim_ids,
        winner_claim_created=winner_claim_created,
        belief_store_changed=belief_store_changed,
        created=True,
    )


def bind_duplicate_claim_evidence(
    database_path: Path,
    *,
    validation_event_id: str,
) -> ClaimEvidenceBinding:
    """Anexa nova evidência a Claims equivalentes sem mudar a visão atual do World."""
    normalized_validation_event_id = validation_event_id.strip()
    if not normalized_validation_event_id:
        raise ValueError("duplicate evidence binding exige validation_event_id")

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        validation_row = connection.execute(
            """
            SELECT payload_json, trace_id, related_entity_ids_json, goal_id, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (normalized_validation_event_id, CLAIM_VALIDATION_EVENT_KIND),
        ).fetchone()
        if validation_row is None:
            raise ValueError(
                "duplicate evidence binding exige world.claim.validation.completed existente: "
                f"{normalized_validation_event_id}"
            )
        if str(validation_row[4]) != "world":
            raise ValueError("claim validation não possui autoridade de origem esperada")

        validation_payload = json.loads(str(validation_row[0]))
        if not isinstance(validation_payload, dict):
            raise TypeError("payload da claim validation possui tipo inválido")
        proposed_claim_event_id = _required_payload_string(
            validation_payload,
            "proposed_claim_event_id",
            context="claim validation",
        )
        if validation_payload.get("outcome") != "DUPLICATE":
            raise ValueError(
                "duplicate evidence binding exige validation DUPLICATE; "
                f"outcome atual: {validation_payload.get('outcome')}"
            )
        if validation_payload.get("effect_applied") is not False:
            raise ValueError("claim validation já possui efeito aplicado")

        active_claim_ids = _required_payload_string_tuple(
            validation_payload,
            "active_claim_ids",
            context="claim validation",
        )
        matching_claim_ids = _required_payload_string_tuple(
            validation_payload,
            "matching_claim_ids",
            context="claim validation",
        )
        conflicting_claim_ids = _required_payload_string_tuple(
            validation_payload,
            "conflicting_claim_ids",
            context="claim validation",
        )
        if not matching_claim_ids:
            raise ValueError("validation DUPLICATE não possui Claim equivalente")
        if conflicting_claim_ids:
            raise ValueError("validation DUPLICATE contém conflito persistido")
        if active_claim_ids != matching_claim_ids:
            raise ValueError("validation DUPLICATE possui snapshot inconsistente")

        existing = _find_claim_evidence_binding_in_connection(
            connection,
            validation_event_id=normalized_validation_event_id,
        )
        if existing is not None:
            bound_claims = tuple(
                _require_claim_in_connection(connection, claim_id)
                for claim_id in existing[1]
            )
            return ClaimEvidenceBinding(
                event=existing[0],
                validation_event_id=normalized_validation_event_id,
                proposed_claim_event_id=proposed_claim_event_id,
                bound_claims=bound_claims,
                evidence_event_ids_added=existing[2],
                created=False,
            )

        proposal_row = connection.execute(
            """
            SELECT payload_json, trace_id, related_entity_ids_json, goal_id, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (proposed_claim_event_id, PROPOSED_CLAIM_EVENT_KIND),
        ).fetchone()
        if proposal_row is None:
            raise ValueError(f"proposed claim não encontrada: {proposed_claim_event_id}")
        if str(proposal_row[4]) != "perception":
            raise ValueError(
                "duplicate evidence binding deste passo exige proposta originada em perception"
            )

        proposal_payload = json.loads(str(proposal_row[0]))
        if not isinstance(proposal_payload, dict):
            raise TypeError("payload da proposed claim possui tipo inválido")
        subject_id = _required_payload_string(
            proposal_payload,
            "subject_id",
            context="proposed claim",
        )
        predicate = _required_payload_string(
            proposal_payload,
            "predicate",
            context="proposed claim",
        )
        epistemic_status = _required_payload_string(
            proposal_payload,
            "epistemic_status",
            context="proposed claim",
        )
        if epistemic_status != "DIRECT_OBSERVATION":
            raise ValueError(
                "duplicate evidence binding deste passo exige DIRECT_OBSERVATION"
            )
        raw_evidence_event_ids = _required_payload_string_tuple(
            proposal_payload,
            "evidence_event_ids",
            context="proposed claim",
        )
        if proposal_payload.get("status") != "PROPOSED":
            raise ValueError("proposed claim não está disponível para confirmação")
        if proposal_payload.get("effect_applied") is not False:
            raise ValueError("proposed claim já possui efeito aplicado")

        current_rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
        current_claims = tuple(_claim_from_row(row) for row in current_rows)
        current_active_claim_ids = tuple(claim.id for claim in current_claims)
        if current_active_claim_ids != active_claim_ids:
            raise ValueError(
                "Belief Store mudou após validation DUPLICATE; "
                "execute claim-validate novamente"
            )
        if any(
            claim.value != proposal_payload.get("value")
            or claim.epistemic_status != epistemic_status
            for claim in current_claims
        ):
            raise ValueError(
                "Belief Store deixou de ser equivalente após validation DUPLICATE; "
                "execute claim-validate novamente"
            )

        binding_event_id = f"evt_{uuid4().hex}"
        evidence_event_ids_added = tuple(
            dict.fromkeys(
                (
                    *raw_evidence_event_ids,
                    normalized_validation_event_id,
                    binding_event_id,
                )
            )
        )
        binding_event = Event(
            id=binding_event_id,
            kind=CLAIM_EVIDENCE_BOUND_EVENT_KIND,
            occurred_at=datetime.now(UTC),
            source="world",
            payload={
                "validation_event_id": normalized_validation_event_id,
                "proposed_claim_event_id": proposed_claim_event_id,
                "bound_claim_ids": list(current_active_claim_ids),
                "evidence_event_ids_added": list(evidence_event_ids_added),
                "basis": "DETERMINISTIC_EQUIVALENCE",
                "claim_evidence_updated": True,
                "current_world_view_changed": False,
                "effect_applied": True,
            },
            trace_id=(
                str(validation_row[1])
                if validation_row[1] is not None
                else str(proposal_row[1])
                if proposal_row[1] is not None
                else proposed_claim_event_id
            ),
            related_entity_ids=_string_tuple_from_json(
                validation_row[2],
                field="related_entity_ids",
            ),
            goal_id=str(validation_row[3]) if validation_row[3] is not None else None,
        )

        for claim in current_claims:
            merged_evidence = tuple(
                dict.fromkeys((*claim.evidence_event_ids, *evidence_event_ids_added))
            )
            cursor = connection.execute(
                """
                UPDATE claims
                SET evidence_event_ids_json = ?
                WHERE id = ? AND status = 'ACTIVE'
                """,
                (
                    json.dumps(merged_evidence, separators=(",", ":")),
                    claim.id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "snapshot mudou durante confirmação de Claim DUPLICATE"
                )

        _insert_event_in_connection(connection, binding_event)
        bound_claims = tuple(
            _require_claim_in_connection(connection, claim_id)
            for claim_id in current_active_claim_ids
        )

    return ClaimEvidenceBinding(
        event=binding_event,
        validation_event_id=normalized_validation_event_id,
        proposed_claim_event_id=proposed_claim_event_id,
        bound_claims=bound_claims,
        evidence_event_ids_added=evidence_event_ids_added,
        created=True,
    )


def accept_ready_proposed_claim(
    database_path: Path,
    *,
    validation_event_id: str,
) -> ClaimAcceptance:
    """Aceita uma Proposed Claim READY com autoridade humana explícita."""
    normalized_validation_event_id = validation_event_id.strip()
    if not normalized_validation_event_id:
        raise ValueError("claim acceptance exige validation_event_id")

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        validation_row = connection.execute(
            """
            SELECT payload_json, trace_id, related_entity_ids_json, goal_id, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (normalized_validation_event_id, CLAIM_VALIDATION_EVENT_KIND),
        ).fetchone()
        if validation_row is None:
            raise ValueError(
                "claim acceptance exige world.claim.validation.completed existente: "
                f"{normalized_validation_event_id}"
            )
        if str(validation_row[4]) != "world":
            raise ValueError("claim validation não possui autoridade de origem esperada")

        validation_payload = json.loads(str(validation_row[0]))
        if not isinstance(validation_payload, dict):
            raise TypeError("payload da claim validation possui tipo inválido")
        proposed_claim_event_id = validation_payload.get("proposed_claim_event_id")
        outcome = validation_payload.get("outcome")
        if not isinstance(proposed_claim_event_id, str):
            raise TypeError("claim validation não possui proposed_claim_event_id válido")
        if outcome != "READY":
            raise ValueError(
                "claim acceptance exige validation READY; "
                f"outcome atual: {outcome}"
            )
        if validation_payload.get("effect_applied") is not False:
            raise ValueError("claim validation já possui efeito aplicado")

        existing = _find_existing_claim_acceptance_in_connection(
            connection,
            proposed_claim_event_id=proposed_claim_event_id,
        )
        if existing is not None:
            claim_id, acceptance_event = existing
            claim_row = connection.execute(
                _claim_select() + " WHERE id = ?",
                (claim_id,),
            ).fetchone()
            if claim_row is None:
                raise RuntimeError(
                    "aceitação existente referencia Claim indisponível: "
                    f"{claim_id}"
                )
            return ClaimAcceptance(
                claim=_claim_from_row(claim_row),
                event=acceptance_event,
                created=False,
            )

        proposal_row = connection.execute(
            """
            SELECT payload_json, trace_id, related_entity_ids_json, goal_id, source
            FROM events
            WHERE id = ? AND kind = ?
            """,
            (proposed_claim_event_id, PROPOSED_CLAIM_EVENT_KIND),
        ).fetchone()
        if proposal_row is None:
            raise ValueError(f"proposed claim não encontrada: {proposed_claim_event_id}")
        if str(proposal_row[4]) != "perception":
            raise ValueError(
                "claim acceptance deste passo exige proposta originada em perception"
            )

        proposal_payload = json.loads(str(proposal_row[0]))
        if not isinstance(proposal_payload, dict):
            raise TypeError("payload da proposed claim possui tipo inválido")
        subject_id = proposal_payload.get("subject_id")
        predicate = proposal_payload.get("predicate")
        epistemic_status = proposal_payload.get("epistemic_status")
        raw_evidence_event_ids = proposal_payload.get("evidence_event_ids")
        if not isinstance(subject_id, str) or not subject_id.strip():
            raise TypeError("proposed claim não possui subject_id válido")
        if not isinstance(predicate, str) or not predicate.strip():
            raise TypeError("proposed claim não possui predicate válido")
        if epistemic_status != "DIRECT_OBSERVATION":
            raise ValueError(
                "claim acceptance deste passo exige epistemic_status DIRECT_OBSERVATION"
            )
        if not isinstance(raw_evidence_event_ids, list) or not all(
            isinstance(item, str) for item in raw_evidence_event_ids
        ):
            raise TypeError("proposed claim não possui evidence_event_ids válidos")
        if proposal_payload.get("status") != "PROPOSED":
            raise ValueError("proposed claim não está disponível para aceitação")
        if proposal_payload.get("effect_applied") is not False:
            raise ValueError("proposed claim já possui efeito aplicado")

        # READY é um snapshot. A aceitação precisa provar novamente que o eixo
        # continua vazio dentro da mesma transação que criará a Claim.
        current_active = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
        if current_active:
            raise ValueError(
                "Belief Store mudou após validation READY; "
                "execute claim-validate novamente"
            )

        related_entity_ids = _string_tuple_from_json(
            proposal_row[2],
            field="related_entity_ids",
        )
        goal_id = str(proposal_row[3]) if proposal_row[3] is not None else None
        trace_id = (
            str(validation_row[1])
            if validation_row[1] is not None
            else str(proposal_row[1])
            if proposal_row[1] is not None
            else proposed_claim_event_id
        )

        claim_id = f"clm_{uuid4().hex}"
        acceptance_event = Event.create(
            kind=CLAIM_ACCEPTED_EVENT_KIND,
            source="user",
            payload={
                "proposed_claim_event_id": proposed_claim_event_id,
                "validation_event_id": normalized_validation_event_id,
                "claim_id": claim_id,
                "authority": "USER_CONFIRMATION",
                "effect_applied": True,
            },
            trace_id=trace_id,
            related_entity_ids=related_entity_ids,
            goal_id=goal_id,
        )
        evidence_event_ids = tuple(
            dict.fromkeys(
                (
                    *raw_evidence_event_ids,
                    normalized_validation_event_id,
                    acceptance_event.id,
                )
            )
        )
        claim = Claim(
            id=claim_id,
            subject_id=subject_id,
            predicate=predicate,
            value=proposal_payload.get("value"),
            epistemic_status=epistemic_status,
            valid_from=None,
            valid_until=None,
            learned_at=datetime.now(UTC),
            evidence_event_ids=evidence_event_ids,
            status=ACTIVE,
        )

        _insert_event_in_connection(connection, acceptance_event)
        _insert_claim_in_connection(connection, claim)
        advance_world_revision_in_connection(connection)

    return ClaimAcceptance(claim=claim, event=acceptance_event, created=True)


def _find_existing_claim_acceptance_in_connection(
    connection: sqlite3.Connection,
    *,
    proposed_claim_event_id: str,
) -> tuple[str, Event] | None:
    rows = connection.execute(
        """
        SELECT
            id, occurred_at, source, payload_json, trace_id,
            related_entity_ids_json, goal_id, experience_id
        FROM events
        WHERE kind = ?
        ORDER BY occurred_at, id
        """,
        (CLAIM_ACCEPTED_EVENT_KIND,),
    ).fetchall()
    for row in rows:
        payload = json.loads(str(row[3]))
        if not isinstance(payload, dict):
            continue
        if payload.get("proposed_claim_event_id") != proposed_claim_event_id:
            continue
        claim_id = payload.get("claim_id")
        if not isinstance(claim_id, str):
            raise TypeError("world.claim.accepted persistido sem claim_id válido")
        event = Event(
            id=str(row[0]),
            kind=CLAIM_ACCEPTED_EVENT_KIND,
            occurred_at=datetime.fromisoformat(str(row[1])),
            source=str(row[2]),
            payload=payload,
            trace_id=str(row[4]) if row[4] is not None else None,
            related_entity_ids=_string_tuple_from_json(
                row[5],
                field="related_entity_ids",
            ),
            goal_id=str(row[6]) if row[6] is not None else None,
            experience_id=str(row[7]) if row[7] is not None else None,
        )
        return claim_id, event
    return None



def _find_claim_evidence_binding_in_connection(
    connection: sqlite3.Connection,
    *,
    validation_event_id: str,
) -> tuple[Event, tuple[str, ...], tuple[str, ...]] | None:
    rows = connection.execute(
        """
        SELECT
            id, occurred_at, source, payload_json, trace_id,
            related_entity_ids_json, goal_id, experience_id
        FROM events
        WHERE kind = ?
        ORDER BY occurred_at DESC, rowid DESC
        """,
        (CLAIM_EVIDENCE_BOUND_EVENT_KIND,),
    ).fetchall()
    for row in rows:
        payload = json.loads(str(row[3]))
        if not isinstance(payload, dict):
            continue
        if payload.get("validation_event_id") != validation_event_id:
            continue
        event = Event(
            id=str(row[0]),
            kind=CLAIM_EVIDENCE_BOUND_EVENT_KIND,
            occurred_at=datetime.fromisoformat(str(row[1])),
            source=str(row[2]),
            payload=payload,
            trace_id=str(row[4]) if row[4] is not None else None,
            related_entity_ids=_string_tuple_from_json(
                row[5],
                field="related_entity_ids",
            ),
            goal_id=str(row[6]) if row[6] is not None else None,
            experience_id=str(row[7]) if row[7] is not None else None,
        )
        bound_claim_ids = _required_payload_string_tuple(
            payload,
            "bound_claim_ids",
            context="duplicate evidence binding",
        )
        evidence_event_ids_added = _required_payload_string_tuple(
            payload,
            "evidence_event_ids_added",
            context="duplicate evidence binding",
        )
        return event, bound_claim_ids, evidence_event_ids_added
    return None


def _require_claim_in_connection(
    connection: sqlite3.Connection,
    claim_id: str,
) -> Claim:
    row = connection.execute(_claim_select() + " WHERE id = ?", (claim_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"Claim referenciada não encontrada: {claim_id}")
    return _claim_from_row(row)

def _find_conflict_resolution_application_in_connection(
    connection: sqlite3.Connection,
    *,
    resolution_event_id: str,
) -> tuple[Event, str] | None:
    rows = connection.execute(
        """
        SELECT
            id, occurred_at, source, payload_json, trace_id,
            related_entity_ids_json, goal_id, experience_id
        FROM events
        WHERE kind = ?
        ORDER BY occurred_at DESC, rowid DESC
        """,
        (CLAIM_CONFLICT_RESOLUTION_APPLIED_EVENT_KIND,),
    ).fetchall()
    for row in rows:
        payload = json.loads(str(row[3]))
        if not isinstance(payload, dict):
            continue
        if payload.get("resolution_event_id") != resolution_event_id:
            continue
        winner_claim_id = payload.get("winner_claim_id")
        if not isinstance(winner_claim_id, str):
            raise TypeError(
                "world.claim.conflict.resolution.applied sem winner_claim_id válido"
            )
        event = Event(
            id=str(row[0]),
            kind=CLAIM_CONFLICT_RESOLUTION_APPLIED_EVENT_KIND,
            occurred_at=datetime.fromisoformat(str(row[1])),
            source=str(row[2]),
            payload=payload,
            trace_id=str(row[4]) if row[4] is not None else None,
            related_entity_ids=_string_tuple_from_json(
                row[5],
                field="related_entity_ids",
            ),
            goal_id=str(row[6]) if row[6] is not None else None,
            experience_id=str(row[7]) if row[7] is not None else None,
        )
        return event, winner_claim_id
    return None


def _required_payload_string(
    payload: dict[str, object],
    field: str,
    *,
    context: str,
) -> str:
    raw = payload.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise TypeError(f"{context} sem {field} válido")
    return raw


def _required_payload_string_tuple(
    payload: dict[str, object],
    field: str,
    *,
    context: str,
) -> tuple[str, ...]:
    raw = payload.get(field)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise TypeError(f"{context} sem {field} válido")
    return tuple(raw)


def _required_payload_bool(
    payload: dict[str, object],
    field: str,
    *,
    context: str,
) -> bool:
    raw = payload.get(field)
    if not isinstance(raw, bool):
        raise TypeError(f"{context} sem {field} válido")
    return raw


def _find_conflict_resolution_proposal_in_connection(
    connection: sqlite3.Connection,
    *,
    validation_event_id: str,
) -> ClaimConflictResolutionProposal | None:
    rows = connection.execute(
        """
        SELECT
            id, occurred_at, source, payload_json, trace_id,
            related_entity_ids_json, goal_id, experience_id
        FROM events
        WHERE kind = ?
        ORDER BY occurred_at DESC, rowid DESC
        """,
        (CLAIM_CONFLICT_RESOLUTION_EVENT_KIND,),
    ).fetchall()
    for row in rows:
        payload = json.loads(str(row[3]))
        if not isinstance(payload, dict):
            continue
        if payload.get("validation_event_id") != validation_event_id:
            continue
        event = Event(
            id=str(row[0]),
            kind=CLAIM_CONFLICT_RESOLUTION_EVENT_KIND,
            occurred_at=datetime.fromisoformat(str(row[1])),
            source=str(row[2]),
            payload=payload,
            trace_id=str(row[4]) if row[4] is not None else None,
            related_entity_ids=_string_tuple_from_json(
                row[5],
                field="related_entity_ids",
            ),
            goal_id=str(row[6]) if row[6] is not None else None,
            experience_id=str(row[7]) if row[7] is not None else None,
        )
        proposed_claim_event_id = payload.get("proposed_claim_event_id")
        winner_kind = payload.get("winner_kind")
        winner_id = payload.get("winner_id")
        if not isinstance(proposed_claim_event_id, str):
            raise TypeError("conflict resolution persistida sem proposed_claim_event_id válido")
        if not isinstance(winner_kind, str) or winner_kind not in CLAIM_CONFLICT_WINNER_KINDS:
            raise TypeError("conflict resolution persistida sem winner_kind válido")
        if not isinstance(winner_id, str):
            raise TypeError("conflict resolution persistida sem winner_id válido")

        return ClaimConflictResolutionProposal(
            event=event,
            validation_event_id=validation_event_id,
            proposed_claim_event_id=proposed_claim_event_id,
            winner_kind=winner_kind,
            winner_id=winner_id,
            expected_active_claim_ids=_string_tuple_from_payload(
                payload, field="expected_active_claim_ids"
            ),
            matching_claim_ids=_string_tuple_from_payload(
                payload, field="matching_claim_ids"
            ),
            conflicting_claim_ids=_string_tuple_from_payload(
                payload, field="conflicting_claim_ids"
            ),
        )
    return None


def _string_tuple_from_payload(
    payload: dict[str, object], *, field: str
) -> tuple[str, ...]:
    raw = payload.get(field)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise TypeError(f"conflict resolution persistida sem {field} válido")
    return tuple(raw)


def _string_tuple_from_json(raw: object, *, field: str) -> tuple[str, ...]:
    decoded = json.loads(str(raw))
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise TypeError(f"{field} persistido possui tipo inválido")
    return tuple(decoded)


def _insert_event_in_connection(connection: sqlite3.Connection, event: Event) -> None:
    connection.execute(
        """
        INSERT INTO events (
            id, kind, occurred_at, source, payload_json, trace_id,
            related_entity_ids_json, goal_id, experience_id
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


def _claim_from_row(row: tuple[object, ...]) -> Claim:
    return Claim(
        id=str(row[0]),
        subject_id=str(row[1]),
        predicate=str(row[2]),
        value=json.loads(str(row[3])),
        epistemic_status=str(row[4]),
        valid_from=datetime.fromisoformat(str(row[5])) if row[5] is not None else None,
        valid_until=datetime.fromisoformat(str(row[6])) if row[6] is not None else None,
        learned_at=datetime.fromisoformat(str(row[7])),
        evidence_event_ids=tuple(json.loads(str(row[8]))),
        status=str(row[9]),
    )


def _claim_select() -> str:
    return """
        SELECT
            id,
            subject_id,
            predicate,
            value_json,
            epistemic_status,
            valid_from,
            valid_until,
            learned_at,
            evidence_event_ids_json,
            status
        FROM claims
    """


def _insert_claim_in_connection(connection: sqlite3.Connection, claim: Claim) -> None:
    connection.execute(
        """
        INSERT INTO claims (
            id,
            subject_id,
            predicate,
            value_json,
            epistemic_status,
            valid_from,
            valid_until,
            learned_at,
            evidence_event_ids_json,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            claim.id,
            claim.subject_id,
            claim.predicate,
            json.dumps(claim.value, ensure_ascii=False, separators=(",", ":")),
            claim.epistemic_status,
            claim.valid_from.isoformat() if claim.valid_from is not None else None,
            claim.valid_until.isoformat() if claim.valid_until is not None else None,
            claim.learned_at.isoformat(),
            json.dumps(claim.evidence_event_ids, separators=(",", ":")),
            claim.status,
        ),
    )


def insert_claim(database_path: Path, claim: Claim) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _insert_claim_in_connection(connection, claim)
        if claim.status == ACTIVE:
            advance_world_revision_in_connection(connection)


def get_claim(database_path: Path, claim_id: str) -> Claim | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(_claim_select() + " WHERE id = ?", (claim_id,)).fetchone()
    return _claim_from_row(row) if row is not None else None


def list_active_claims(
    database_path: Path,
    *,
    subject_id: str,
    predicate: str,
) -> tuple[Claim, ...]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
    return tuple(_claim_from_row(row) for row in rows)


def list_active_claims_for_subject(
    database_path: Path,
    *,
    subject_id: str,
    limit: int = 20,
) -> tuple[Claim, ...]:
    if limit <= 0:
        raise ValueError("limit de claims precisa ser positivo")

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at DESC, id DESC LIMIT ?",
            (subject_id, limit),
        ).fetchall()
    return tuple(_claim_from_row(row) for row in rows)


def transition_claim(database_path: Path, claim_id: str, new_status: str) -> Claim:
    if new_status not in TERMINAL_STATUSES:
        raise ValueError(f"status terminal inválido: {new_status}")

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE claims
            SET status = ?
            WHERE id = ? AND status = 'ACTIVE'
            """,
            (new_status, claim_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"claim não está ACTIVE: {claim_id}")
        advance_world_revision_in_connection(connection)
        row = connection.execute(_claim_select() + " WHERE id = ?", (claim_id,)).fetchone()

    if row is None:
        raise RuntimeError(f"claim desapareceu após atualização: {claim_id}")
    return _claim_from_row(row)


def set_current_claim(
    database_path: Path,
    *,
    subject_id: str,
    predicate: str,
    value: object,
    epistemic_status: str,
    evidence_event_ids: tuple[str, ...] = (),
    valid_from: datetime | None = None,
) -> Claim:
    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            _claim_select()
            + " WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE' "
            "ORDER BY learned_at, id",
            (subject_id, predicate),
        ).fetchall()
        active_claims = tuple(_claim_from_row(row) for row in rows)

        for claim in active_claims:
            if claim.value == value and claim.epistemic_status == epistemic_status:
                return claim

        if active_claims:
            connection.execute(
                """
                UPDATE claims
                SET status = 'SUPERSEDED'
                WHERE subject_id = ? AND predicate = ? AND status = 'ACTIVE'
                """,
                (subject_id, predicate),
            )

        new_claim = Claim.create(
            subject_id=subject_id,
            predicate=predicate,
            value=value,
            epistemic_status=epistemic_status,
            evidence_event_ids=evidence_event_ids,
            valid_from=valid_from,
        )
        _insert_claim_in_connection(connection, new_claim)
        advance_world_revision_in_connection(connection)
        return new_claim
