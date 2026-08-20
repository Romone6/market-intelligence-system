BEGIN IMMEDIATE;

CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL CHECK (length(trim(legal_name)) > 0),
    cik TEXT NOT NULL CHECK (length(cik) = 10),
    incorporation_country TEXT,
    sector TEXT,
    industry TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE securities (
    security_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    ticker TEXT NOT NULL CHECK (length(trim(ticker)) > 0),
    exchange TEXT NOT NULL,
    security_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    delisted_at TEXT,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
);

CREATE TABLE identifier_history (
    identifier_history_id INTEGER PRIMARY KEY,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    security_id TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    source TEXT NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
    FOREIGN KEY (security_id) REFERENCES securities(security_id)
);

CREATE TABLE universe_membership (
    security_id TEXT NOT NULL,
    universe_name TEXT NOT NULL,
    membership_start TEXT NOT NULL,
    membership_end TEXT,
    reason_added TEXT NOT NULL,
    reason_removed TEXT,
    PRIMARY KEY (security_id, universe_name, membership_start),
    CHECK (membership_end IS NULL OR membership_end > membership_start),
    FOREIGN KEY (security_id) REFERENCES securities(security_id)
);

CREATE INDEX idx_entities_cik_validity
    ON entities (cik, valid_from, valid_to);
CREATE INDEX idx_securities_entity_validity
    ON securities (entity_id, valid_from, valid_to);
CREATE INDEX idx_identifier_history_lookup
    ON identifier_history (
        identifier_type,
        identifier_value,
        valid_from,
        valid_to
    );
CREATE UNIQUE INDEX uq_identifier_history_version
    ON identifier_history (
        identifier_type,
        identifier_value,
        entity_id,
        ifnull(security_id, ''),
        valid_from
    );
CREATE INDEX idx_universe_membership_lookup
    ON universe_membership (
        security_id,
        universe_name,
        membership_start,
        membership_end
    );

INSERT INTO schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
