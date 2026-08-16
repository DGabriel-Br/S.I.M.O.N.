BEGIN IMMEDIATE;

CREATE TABLE verification_results (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('ACTION', 'GOAL')),
    subject_id TEXT NOT NULL,
    criteria_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('VERIFIED', 'FAILED', 'INCONCLUSIVE', 'ASSESSED')
    ),
    evidence_event_ids_json TEXT NOT NULL,
    observed_json TEXT NOT NULL,
    strength INTEGER NOT NULL CHECK (strength BETWEEN 1 AND 5),
    created_at TEXT NOT NULL
);

CREATE INDEX verification_results_subject_idx
ON verification_results (subject_type, subject_id, created_at);

CREATE INDEX verification_results_status_idx
ON verification_results (status, created_at);

PRAGMA user_version = 7;

COMMIT;
