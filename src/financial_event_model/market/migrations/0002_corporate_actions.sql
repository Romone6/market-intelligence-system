BEGIN IMMEDIATE;

CREATE TABLE corporate_actions (
    action_id TEXT NOT NULL,
    security_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action_type TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    announced_at TEXT,
    first_observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    source_payload_json TEXT NOT NULL,
    PRIMARY KEY (action_id, source_content_hash),
    CHECK (length(source_content_hash) = 64)
);

CREATE INDEX idx_corporate_actions_asof
    ON corporate_actions (security_id, first_observed_at, effective_date);

INSERT INTO market_schema_migrations (version, applied_at)
VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
