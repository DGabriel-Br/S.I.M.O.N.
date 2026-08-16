BEGIN IMMEDIATE;

CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('EPISODIC', 'SEMANTIC', 'PROCEDURAL', 'META')),
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    scope TEXT NOT NULL CHECK (
        scope IN ('GLOBAL', 'PROJECT', 'WORKSPACE', 'SESSION', 'PRIVATE', 'SYSTEM', 'LAB')
    ),
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    source_experience_ids_json TEXT NOT NULL,
    source_claim_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED', 'SUPERSEDED', 'RETRACTED')),
    created_at TEXT NOT NULL,
    last_used_at TEXT
);

CREATE INDEX memories_status_created_idx
ON memories (status, created_at DESC);

CREATE INDEX memories_kind_scope_idx
ON memories (kind, scope, status);

PRAGMA user_version = 9;

COMMIT;
