import json
import sqlite3
from pathlib import Path

from simon.cognition import GoalProposal
from simon.events import Event, append_event
from simon.goal_intake import accept_goal_proposal
from simon.storage import initialize_storage


def _create_proposal_event(database_path: Path) -> Event:
    proposal = GoalProposal(
        title="Corrigir falha no script",
        desired_state="O script executa sem reproduzir a falha relatada.",
        success_criteria=[
            "A execução termina sem a falha original.",
            "O resultado esperado é produzido.",
        ],
        open_questions=["Qual arquivo contém o script?"],
    )
    event = Event.create(
        kind="cognition.goal_proposal.completed",
        source="cognition",
        payload={
            "model": "fake-model",
            "proposal": proposal.model_dump(mode="json"),
        },
        trace_id="trc_proposal",
    )
    append_event(database_path, event)
    return event


def test_accept_goal_proposal_persists_user_goal_and_lineage(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    proposal_event = _create_proposal_event(database_path)

    acceptance = accept_goal_proposal(
        database_path,
        proposal_event.id,
        trace_id="trc_acceptance",
    )

    assert acceptance.created is True
    assert acceptance.goal.origin == "USER"
    assert acceptance.goal.status == "ACTIVE"
    assert acceptance.goal.desired_state == {
        "description": "O script executa sem reproduzir a falha relatada."
    }
    assert acceptance.goal.success_criteria == (
        {"description": "A execução termina sem a falha original."},
        {"description": "O resultado esperado é produzido."},
    )

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT source, payload_json, trace_id, goal_id
            FROM events
            WHERE kind = 'goal.proposal.accepted'
            """
        ).fetchone()

    assert row is not None
    payload = json.loads(str(row[1]))
    assert row[0] == "user"
    assert row[2] == "trc_acceptance"
    assert row[3] == acceptance.goal.id
    assert payload["proposal_event_id"] == proposal_event.id
    assert payload["proposal_trace_id"] == "trc_proposal"
    assert payload["proposal_model"] == "fake-model"
    assert payload["open_questions"] == ["Qual arquivo contém o script?"]


def test_accept_goal_proposal_is_idempotent(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    proposal_event = _create_proposal_event(database_path)

    first = accept_goal_proposal(database_path, proposal_event.id)
    second = accept_goal_proposal(database_path, proposal_event.id)

    assert first.created is True
    assert second.created is False
    assert second.goal.id == first.goal.id

    with sqlite3.connect(database_path) as connection:
        goal_count = connection.execute("SELECT COUNT(*) FROM goals").fetchone()
        acceptance_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'goal.proposal.accepted'"
        ).fetchone()

    assert goal_count == (1,)
    assert acceptance_count == (1,)


def test_accept_goal_proposal_rejects_wrong_event_kind(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    event = Event.create(kind="user.input.received", source="user", payload={"text": "oi"})
    append_event(database_path, event)

    try:
        accept_goal_proposal(database_path, event.id)
    except ValueError as exc:
        assert "não representa uma proposta" in str(exc)
    else:
        raise AssertionError("Event que não é proposta deveria ser rejeitado")
