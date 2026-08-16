BEGIN IMMEDIATE;

CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (
        origin IN ('USER', 'SYSTEM', 'DERIVED', 'MAINTENANCE', 'LAB')
    ),
    parent_goal_id TEXT,
    desired_state_json TEXT NOT NULL,
    success_criteria_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE', 'WAITING', 'BLOCKED', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX goals_status_idx
ON goals (status);

CREATE INDEX goals_parent_goal_id_idx
ON goals (parent_goal_id);

PRAGMA user_version = 4;

COMMIT;
