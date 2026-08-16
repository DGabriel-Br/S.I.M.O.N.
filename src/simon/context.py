import json
from dataclasses import dataclass
from pathlib import Path

from simon.claims import Claim, list_active_claims_for_subject
from simon.entities import Entity, find_entities_mentioned_in_text
from simon.goals import Goal, list_open_goals
from simon.memories import Memory, retrieve_memories


@dataclass(frozen=True, slots=True)
class CognitiveContext:
    goals: tuple[Goal, ...]
    entities: tuple[Entity, ...]
    claims: tuple[Claim, ...]
    memories: tuple[Memory, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.goals or self.entities or self.claims or self.memories)

    def to_model_payload(self) -> dict[str, object]:
        return {
            "goals": [
                {
                    "id": goal.id,
                    "title": goal.title,
                    "status": goal.status,
                }
                for goal in self.goals
            ],
            "entities": [
                {
                    "id": entity.id,
                    "kind": entity.kind,
                    "name": entity.name,
                }
                for entity in self.entities
            ],
            "claims": [
                {
                    "id": claim.id,
                    "subject_id": claim.subject_id,
                    "predicate": claim.predicate,
                    "value": claim.value,
                    "epistemic_status": claim.epistemic_status,
                }
                for claim in self.claims
            ],
            "memories": [
                {
                    "id": memory.id,
                    "kind": memory.kind,
                    "scope": memory.scope,
                    "content": memory.content,
                    "entity_ids": list(memory.entity_ids),
                }
                for memory in self.memories
            ],
        }

    def to_model_text(self) -> str:
        return json.dumps(
            self.to_model_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )


def build_cognitive_context(
    database_path: Path,
    *,
    text: str,
    goal_limit: int = 3,
    entity_limit: int = 5,
    claim_limit: int = 10,
    memory_limit: int = 5,
) -> CognitiveContext:
    if not text.strip():
        raise ValueError("texto para contexto não pode ser vazio")
    for name, value in (
        ("goal_limit", goal_limit),
        ("entity_limit", entity_limit),
        ("claim_limit", claim_limit),
        ("memory_limit", memory_limit),
    ):
        if value <= 0:
            raise ValueError(f"{name} precisa ser positivo")

    open_goals = sorted(
        list_open_goals(database_path),
        key=lambda goal: (goal.updated_at, goal.id),
        reverse=True,
    )
    goals = tuple(open_goals[:goal_limit])

    entities = find_entities_mentioned_in_text(
        database_path,
        text=text,
        limit=entity_limit,
    )

    claims: list[Claim] = []
    for entity in entities:
        remaining = claim_limit - len(claims)
        if remaining <= 0:
            break
        claims.extend(
            list_active_claims_for_subject(
                database_path,
                subject_id=entity.id,
                limit=remaining,
            )
        )

    memories: list[Memory] = []
    seen_memory_ids: set[str] = set()

    text_matches = retrieve_memories(
        database_path,
        query=text,
        limit=memory_limit,
    )
    for memory in text_matches:
        memories.append(memory)
        seen_memory_ids.add(memory.id)

    for entity in entities:
        remaining = memory_limit - len(memories)
        if remaining <= 0:
            break
        entity_memories = retrieve_memories(
            database_path,
            entity_id=entity.id,
            limit=remaining,
        )
        for memory in entity_memories:
            if memory.id in seen_memory_ids:
                continue
            memories.append(memory)
            seen_memory_ids.add(memory.id)
            if len(memories) == memory_limit:
                break

    return CognitiveContext(
        goals=goals,
        entities=entities,
        claims=tuple(claims),
        memories=tuple(memories),
    )
