from pathlib import Path

from simon.events import Event, append_event, get_event
from simon.storage import initialize_storage


def test_event_survives_new_database_connection(tmp_path: Path) -> None:
    database_path, _ = initialize_storage(tmp_path)
    event = Event.create(
        kind="user.message",
        source="user",
        payload={"text": "Vamos construir o SIMON."},
        trace_id="trace_1",
    )

    append_event(database_path, event)
    restored = get_event(database_path, event.id)

    assert restored == event
