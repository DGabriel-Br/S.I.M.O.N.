from pathlib import Path

from simon.claims import Claim, insert_claim
from simon.context import build_cognitive_context
from simon.entities import Entity, insert_entity
from simon.experiences import close_experience, create_experience
from simon.goals import Goal, insert_goal
from simon.memories import create_memory
from simon.storage import initialize_storage


def test_context_includes_recent_open_goals_as_summaries(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    first = Goal.create(
        title="Primeiro objetivo",
        origin="USER",
        desired_state={"state": "first"},
        success_criteria=({"kind": "done"},),
    )
    second = Goal.create(
        title="Objetivo mais recente",
        origin="USER",
        desired_state={"state": "second"},
        success_criteria=({"kind": "done"},),
    )
    insert_goal(database_path, first)
    insert_goal(database_path, second)

    context = build_cognitive_context(
        database_path,
        text="Continue de onde paramos",
        goal_limit=1,
    )

    assert tuple(goal.id for goal in context.goals) == (second.id,)
    payload = context.to_model_payload()
    assert payload["goals"] == [
        {"id": second.id, "title": "Objetivo mais recente", "status": "ACTIVE"}
    ]


def test_context_uses_exact_entity_to_retrieve_claims_and_memories(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    alpha = Entity.create(kind="project", name="Projeto Alpha", aliases=("Alpha",))
    beta = Entity.create(kind="project", name="Projeto Beta", aliases=("Beta",))
    insert_entity(database_path, alpha)
    insert_entity(database_path, beta)

    alpha_claim = Claim.create(
        subject_id=alpha.id,
        predicate="runtime.status",
        value="ready",
        epistemic_status="DIRECT_OBSERVATION",
    )
    beta_claim = Claim.create(
        subject_id=beta.id,
        predicate="runtime.status",
        value="offline",
        epistemic_status="DIRECT_OBSERVATION",
    )
    insert_claim(database_path, alpha_claim)
    insert_claim(database_path, beta_claim)

    experience = create_experience(database_path, title="Preparar Alpha")
    close_experience(
        database_path,
        experience.id,
        outcome="SUCCESS",
        summary="Alpha preparado",
    )
    alpha_memory = create_memory(
        database_path,
        kind="SEMANTIC",
        content="O Projeto Alpha usa execução local.",
        scope="PROJECT",
        source_experience_ids=(experience.id,),
        entity_ids=(alpha.id,),
        source_claim_ids=(alpha_claim.id,),
    )

    context = build_cognitive_context(database_path, text="Continue o Alpha")

    assert tuple(entity.id for entity in context.entities) == (alpha.id,)
    assert tuple(claim.id for claim in context.claims) == (alpha_claim.id,)
    assert tuple(memory.id for memory in context.memories) == (alpha_memory.id,)


def test_context_entity_matching_respects_word_boundaries(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    entity = Entity.create(kind="system", name="SIMON")
    insert_entity(database_path, entity)

    context = build_cognitive_context(database_path, text="O nome simonete apareceu aqui")

    assert context.entities == ()
    assert context.claims == ()
    assert context.memories == ()
