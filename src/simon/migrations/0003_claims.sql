BEGIN IMMEDIATE;

CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    epistemic_status TEXT NOT NULL CHECK (
        epistemic_status IN (
            'DIRECT_OBSERVATION',
            'AUTHORITATIVE_REPORT',
            'USER_REPORT',
            'DERIVED',
            'INFERRED',
            'HYPOTHESIS',
            'UNKNOWN'
        )
    ),
    valid_from TEXT,
    valid_until TEXT,
    learned_at TEXT NOT NULL,
    evidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE', 'SUPERSEDED', 'RETRACTED', 'EXPIRED')
    )
);

CREATE INDEX claims_subject_predicate_status_idx
ON claims (subject_id, predicate, status);

PRAGMA user_version = 3;

COMMIT;
