BEGIN IMMEDIATE;

CREATE TABLE plans (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    steps_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE', 'COMPLETED', 'FAILED', 'SUPERSEDED', 'CANCELLED')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (goal_id, revision)
);

CREATE INDEX plans_goal_revision_idx
ON plans (goal_id, revision);

CREATE UNIQUE INDEX plans_one_active_per_goal_idx
ON plans (goal_id)
WHERE status = 'ACTIVE';

PRAGMA user_version = 5;

COMMIT;
