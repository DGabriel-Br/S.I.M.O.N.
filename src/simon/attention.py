from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from simon.events import Event, append_event
from simon.perception import Observation, get_observation

AttentionDestination = Literal["IGNORE", "RECORD", "UPDATE_WORLD", "ATTEND", "INTERRUPT"]


@dataclass(frozen=True, slots=True)
class AttentionSignals:
    urgent: bool = False
    risk: bool = False
    goal_relevant: bool = False
    subscribed: bool = False
    world_change: bool = False
    known_noise: bool = False


@dataclass(frozen=True, slots=True)
class AttentionDecision:
    destination: AttentionDestination
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttentionAssessment:
    observation: Observation
    decision: AttentionDecision
    event: Event


def decide_attention(signals: AttentionSignals) -> AttentionDecision:
    """Classifica uma observação por regras pequenas e explicitamente ordenadas."""
    if signals.urgent or signals.risk:
        reasons = tuple(
            reason
            for enabled, reason in (
                (signals.urgent, "urgent"),
                (signals.risk, "risk"),
            )
            if enabled
        )
        return AttentionDecision(destination="INTERRUPT", reasons=reasons)

    if signals.goal_relevant or signals.subscribed:
        reasons = tuple(
            reason
            for enabled, reason in (
                (signals.goal_relevant, "goal_relevant"),
                (signals.subscribed, "subscribed"),
            )
            if enabled
        )
        return AttentionDecision(destination="ATTEND", reasons=reasons)

    if signals.world_change:
        return AttentionDecision(destination="UPDATE_WORLD", reasons=("world_change",))

    if signals.known_noise:
        return AttentionDecision(destination="IGNORE", reasons=("known_noise",))

    return AttentionDecision(destination="RECORD", reasons=("no_escalation_signal",))


def assess_observation_attention(
    database_path: Path,
    *,
    observation_event_id: str,
    signals: AttentionSignals,
) -> AttentionAssessment:
    """Persiste a decisão de Attention sem aplicar o destino ao World ou Executive."""
    observation = get_observation(database_path, observation_event_id)
    if observation is None:
        raise ValueError(f"observation não encontrada: {observation_event_id}")

    decision = decide_attention(signals)
    event = Event.create(
        kind="attention.assessed",
        source="attention",
        payload={
            "observation_event_id": observation.event.id,
            "destination": decision.destination,
            "signals": asdict(signals),
            "reasons": list(decision.reasons),
            "effect_applied": False,
        },
        trace_id=observation.event.trace_id or observation.event.id,
        related_entity_ids=observation.event.related_entity_ids,
        goal_id=observation.event.goal_id,
    )
    append_event(database_path, event)
    return AttentionAssessment(
        observation=observation,
        decision=decision,
        event=event,
    )
