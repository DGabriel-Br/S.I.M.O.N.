BEGIN IMMEDIATE;

CREATE TABLE experiences (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_id TEXT,
    parent_experience_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    outcome TEXT CHECK (
        outcome IS NULL OR outcome IN (
            'SUCCESS',
            'FAILURE',
            'PARTIAL',
            'INCONCLUSIVE',
            'INTERRUPTED'
        )
    ),
    event_ids_json TEXT NOT NULL DEFAULT '[]',
    action_ids_json TEXT NOT NULL DEFAULT '[]',
    verification_ids_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    updated_at TEXT NOT NULL,
    CHECK (
        (status = 'CLOSED' AND outcome IS NOT NULL AND ended_at IS NOT NULL)
        OR
        (status IN ('ACTIVE', 'SUSPENDED') AND outcome IS NULL AND ended_at IS NULL)
    )
);

CREATE INDEX experiences_goal_idx
ON experiences (goal_id, started_at);

CREATE INDEX experiences_parent_idx
ON experiences (parent_experience_id, started_at);

CREATE INDEX experiences_status_idx
ON experiences (status, started_at);

PRAGMA user_version = 8;

COMMIT;
