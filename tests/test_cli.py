import json
import sqlite3
from pathlib import Path

from simon.actions import create_action, get_action, transition_action
from simon.cli import main
from simon.entities import SIMON_ENTITY_ID
from simon.experiences import create_experience, get_experience
from simon.goals import Goal, insert_goal
from simon.plans import create_plan
from simon.storage import initialize_storage


def test_main_initializes_storage_and_records_current_world_state(
    tmp_path: Path,
    capsys: object,
) -> None:
    result = main(["--data-dir", str(tmp_path)])

    assert result == 0
    database_path = tmp_path / "simon.db"
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        entity = connection.execute(
            "SELECT kind, name FROM entities WHERE id = ?",
            (SIMON_ENTITY_ID,),
        ).fetchone()
        event = connection.execute(
            """
            SELECT id, kind, source, related_entity_ids_json
            FROM events
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()
        claim = connection.execute(
            """
            SELECT predicate, value_json, epistemic_status, evidence_event_ids_json, status
            FROM claims
            WHERE subject_id = ? AND status = 'ACTIVE'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()

    assert entity == ("system", "SIMON")
    assert event is not None
    assert event[1:3] == ("system.started", "system")
    assert tuple(json.loads(str(event[3]))) == (SIMON_ENTITY_ID,)

    assert claim is not None
    assert claim[0] == "storage.schema_version"
    assert json.loads(str(claim[1])) == 9
    assert claim[2] == "DIRECT_OBSERVATION"
    assert tuple(json.loads(str(claim[3]))) == (str(event[0]),)
    assert claim[4] == "ACTIVE"


def test_repeated_startup_does_not_duplicate_same_current_claim(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main(["--data-dir", str(tmp_path)]) == 0
    assert main(["--data-dir", str(tmp_path)]) == 0

    with sqlite3.connect(tmp_path / "simon.db") as connection:
        claim_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM claims
            WHERE subject_id = ?
              AND predicate = 'storage.schema_version'
              AND status = 'ACTIVE'
            """,
            (SIMON_ENTITY_ID,),
        ).fetchone()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'system.started'"
        ).fetchone()

    assert claim_count == (1,)
    assert event_count == (2,)


def test_startup_marks_previous_running_action_as_interrupted(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    goal = Goal.create(
        title="Testar recuperação",
        origin="USER",
        desired_state={"state": "recovered"},
        success_criteria=({"kind": "runtime_recovered"},),
    )
    insert_goal(database_path, goal)
    plan = create_plan(
        database_path,
        goal_id=goal.id,
        steps=({"id": "step_1", "description": "Executar ação longa"},),
    )
    action = create_action(
        database_path,
        goal_id=goal.id,
        plan_id=plan.id,
        step_id="step_1",
        kind="process.run",
    )
    transition_action(database_path, action.id, "RUNNING")

    assert main(["--data-dir", str(tmp_path)]) == 0

    restored = get_action(database_path, action.id)
    assert restored is not None
    assert restored.status == "INTERRUPTED"
    assert restored.failure is not None
    assert restored.failure["kind"] == "runtime_restart"


def test_startup_suspends_previous_active_experience(
    tmp_path: Path,
    capsys: object,
) -> None:
    database_path, _ = initialize_storage(tmp_path)
    experience = create_experience(
        database_path,
        title="Investigar antes do reinício",
    )

    assert main(["--data-dir", str(tmp_path)]) == 0

    restored = get_experience(database_path, experience.id)
    assert restored is not None
    assert restored.status == "SUSPENDED"
    assert restored.outcome is None


def test_model_check_lists_local_models(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def list_models(self) -> tuple[str, ...]:
            return ("model-a:latest", "model-b:q4")

    monkeypatch.setattr("simon.cli.OllamaProvider", FakeProvider)  # type: ignore[attr-defined]

    assert main(["--data-dir", str(tmp_path), "model-check"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Ollama: pronto" in output
    assert "model-a:latest" in output
    assert "model-b:q4" in output
