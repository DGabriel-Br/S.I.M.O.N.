from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from simon.entities import get_entity
from simon.events import Event, append_event, get_event
from simon.goals import get_goal

OBSERVATION_EVENT_KIND = "perception.observation.recorded"


@dataclass(frozen=True, slots=True)
class Observation:
    event: Event
    observer: str
    signal_kind: str
    summary: str
    details: dict[str, object]


def record_observation(
    database_path: Path,
    *,
    observer: str,
    signal_kind: str,
    summary: str,
    details: dict[str, object] | None = None,
    trace_id: str | None = None,
    goal_id: str | None = None,
    related_entity_ids: tuple[str, ...] = (),
) -> Observation:
    """Persiste uma observação explícita sem inferir claims ou alterar o World."""
    normalized_observer = observer.strip()
    normalized_kind = signal_kind.strip()
    normalized_summary = summary.strip()
    if not normalized_observer:
        raise ValueError("observation exige observer")
    if not normalized_kind:
        raise ValueError("observation exige signal_kind")
    if not normalized_summary:
        raise ValueError("observation exige summary")

    if goal_id is not None and get_goal(database_path, goal_id) is None:
        raise ValueError(f"goal relacionado à observation não encontrado: {goal_id}")

    for entity_id in related_entity_ids:
        if get_entity(database_path, entity_id) is None:
            raise ValueError(f"entity relacionada à observation não encontrada: {entity_id}")

    normalized_details = dict(details or {})
    event = Event.create(
        kind=OBSERVATION_EVENT_KIND,
        source="perception",
        payload={
            "observer": normalized_observer,
            "signal_kind": normalized_kind,
            "summary": normalized_summary,
            "details": normalized_details,
        },
        trace_id=trace_id.strip() if trace_id is not None and trace_id.strip() else None,
        related_entity_ids=related_entity_ids,
        goal_id=goal_id,
    )
    append_event(database_path, event)
    return Observation(
        event=event,
        observer=normalized_observer,
        signal_kind=normalized_kind,
        summary=normalized_summary,
        details=normalized_details,
    )


def get_observation(database_path: Path, event_id: str) -> Observation | None:
    event = get_event(database_path, event_id)
    if event is None:
        return None
    if event.kind != OBSERVATION_EVENT_KIND:
        raise ValueError(f"event não é uma observation: {event_id} ({event.kind})")

    observer = event.payload.get("observer")
    signal_kind = event.payload.get("signal_kind")
    summary = event.payload.get("summary")
    details = event.payload.get("details")
    if not isinstance(observer, str):
        raise TypeError(f"observer inválido na observation: {event_id}")
    if not isinstance(signal_kind, str):
        raise TypeError(f"signal_kind inválido na observation: {event_id}")
    if not isinstance(summary, str):
        raise TypeError(f"summary inválido na observation: {event_id}")
    if not isinstance(details, dict):
        raise TypeError(f"details inválido na observation: {event_id}")

    return Observation(
        event=event,
        observer=observer,
        signal_kind=signal_kind,
        summary=summary,
        details=details,
    )
