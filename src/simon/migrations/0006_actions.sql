BEGIN IMMEDIATE;

CREATE TABLE actions (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    input_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'PENDING',
            'RUNNING',
            'COMPLETED',
            'FAILED',
            'BLOCKED',
            'DENIED',
            'INTERRUPTED',
            'CANCELLED'
        )
    ),
    reported_result_json TEXT,
    failure_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX actions_goal_idx
ON actions (goal_id, created_at);

CREATE INDEX actions_plan_idx
ON actions (plan_id, created_at);

CREATE INDEX actions_status_idx
ON actions (status, created_at);

PRAGMA user_version = 6;

COMMIT;
