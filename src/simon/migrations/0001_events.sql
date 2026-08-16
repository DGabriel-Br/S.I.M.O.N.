BEGIN IMMEDIATE;

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    trace_id TEXT,
    related_entity_ids_json TEXT NOT NULL DEFAULT '[]',
    goal_id TEXT,
    experience_id TEXT
);

PRAGMA user_version = 1;

COMMIT;
