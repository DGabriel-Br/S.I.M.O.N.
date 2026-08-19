from pathlib import Path

from simon.claims import Claim, insert_claim, set_current_claim, transition_claim
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.storage import initialize_storage
from simon.world import get_world_revision


def test_world_revision_advances_only_when_current_claim_view_changes(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    assert get_world_revision(database_path) == 0

    claim = Claim.create(
        subject_id="ent_project",
        predicate="status",
        value="failing",
        epistemic_status="DIRECT_OBSERVATION",
    )
    insert_claim(database_path, claim)
    assert get_world_revision(database_path) == 1

    transition_claim(database_path, claim.id, "RETRACTED")
    assert get_world_revision(database_path) == 2


def test_set_current_claim_is_atomic_at_world_revision_level(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)

    first = set_current_claim(
        database_path,
        subject_id="ent_project",
        predicate="status",
        value="failing",
        epistemic_status="DIRECT_OBSERVATION",
    )
    assert get_world_revision(database_path) == 1

    same = set_current_claim(
        database_path,
        subject_id="ent_project",
        predicate="status",
        value="failing",
        epistemic_status="DIRECT_OBSERVATION",
    )
    assert same.id == first.id
    assert get_world_revision(database_path) == 1

    replacement = set_current_claim(
        database_path,
        subject_id="ent_project",
        predicate="status",
        value="fixed",
        epistemic_status="DIRECT_OBSERVATION",
    )
    assert replacement.id != first.id
    assert get_world_revision(database_path) == 2


def test_plan_records_world_revision_used_when_it_is_created(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    set_current_claim(
        database_path,
        subject_id="ent_project",
        predicate="status",
        value="failing",
        epistemic_status="DIRECT_OBSERVATION",
    )

    goal = Goal.create(
        title="Corrigir projeto",
        origin="USER",
        desired_state={"status": "fixed"},
        success_criteria=({"kind": "fixed"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_1", "description": "Corrigir"},),
    )

    assert plan.based_on_world_revision == 1

    set_current_claim(
        database_path,
        subject_id="ent_project",
        predicate="status",
        value="fixed",
        epistemic_status="DIRECT_OBSERVATION",
    )
    assert get_world_revision(database_path) == 2
    assert plan.based_on_world_revision == 1
