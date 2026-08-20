BEGIN IMMEDIATE;

CREATE TABLE knowledge_records (
    record_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    knowledge_type TEXT NOT NULL,
    knowledge_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    event_effective_at TEXT,
    source_published_at TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    tradable_at TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (length(content_hash) = 64),
    CHECK (first_observed_at <= downloaded_at),
    CHECK (downloaded_at <= processed_at),
    CHECK (source_published_at <= tradable_at)
);

CREATE INDEX idx_knowledge_entity_time
    ON knowledge_records (entity_id, tradable_at, knowledge_type, knowledge_key);
CREATE UNIQUE INDEX idx_knowledge_source_policy
    ON knowledge_records (source_id, knowledge_type, knowledge_key, policy_version);

INSERT INTO temporal_schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
