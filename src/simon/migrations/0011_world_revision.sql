BEGIN IMMEDIATE;

CREATE TABLE world_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision INTEGER NOT NULL CHECK (revision >= 0)
);

INSERT INTO world_state (singleton, revision)
VALUES (
    1,
    CASE
        WHEN EXISTS (SELECT 1 FROM claims WHERE status = 'ACTIVE') THEN 1
        ELSE 0
    END
);

ALTER TABLE plans ADD COLUMN based_on_world_revision INTEGER NOT NULL DEFAULT 0;

UPDATE plans
SET based_on_world_revision = (
    SELECT revision FROM world_state WHERE singleton = 1
);

PRAGMA user_version = 11;

COMMIT;
