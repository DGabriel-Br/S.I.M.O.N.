BEGIN IMMEDIATE;

CREATE TABLE actions_new (
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
            'WAITING',
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

INSERT INTO actions_new (
    id,
    goal_id,
    plan_id,
    step_id,
    kind,
    input_json,
    status,
    reported_result_json,
    failure_json,
    created_at,
    started_at,
    finished_at,
    updated_at
)
SELECT
    id,
    goal_id,
    plan_id,
    step_id,
    kind,
    input_json,
    status,
    reported_result_json,
    failure_json,
    created_at,
    started_at,
    finished_at,
    updated_at
FROM actions;

DROP TABLE actions;
ALTER TABLE actions_new RENAME TO actions;

CREATE INDEX actions_goal_idx
ON actions (goal_id, created_at);

CREATE INDEX actions_plan_idx
ON actions (plan_id, created_at);

CREATE INDEX actions_status_idx
ON actions (status, created_at);

CREATE UNIQUE INDEX actions_one_open_attempt_per_step_idx
ON actions (plan_id, step_id)
WHERE status IN ('PENDING', 'RUNNING', 'WAITING');

PRAGMA user_version = 10;

COMMIT;
