BEGIN IMMEDIATE;

CREATE TABLE market_requests (
    request_id INTEGER PRIMARY KEY,
    request_url TEXT NOT NULL,
    adjustment TEXT NOT NULL,
    feed TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    response_received_at TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    local_path TEXT NOT NULL,
    error TEXT
);

CREATE TABLE market_bars (
    bar_id INTEGER PRIMARY KEY,
    security_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    session_date TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    source_timestamp TEXT,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    adjusted_open REAL NOT NULL,
    adjusted_high REAL NOT NULL,
    adjusted_low REAL NOT NULL,
    adjusted_close REAL NOT NULL,
    adjustment_factor REAL NOT NULL,
    trading_status TEXT NOT NULL,
    source TEXT NOT NULL,
    source_received_at TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    UNIQUE (security_id, session_date, source, source_content_hash),
    CHECK (volume >= 0),
    CHECK (adjustment_factor > 0),
    CHECK (length(source_content_hash) = 64)
);

CREATE INDEX idx_market_bars_asof
    ON market_bars (security_id, session_date, source_received_at);

CREATE TABLE factor_observations (
    factor_id INTEGER PRIMARY KEY,
    session_date TEXT NOT NULL,
    market_excess_return REAL NOT NULL,
    smb REAL NOT NULL,
    hml REAL NOT NULL,
    risk_free_rate REAL NOT NULL,
    source TEXT NOT NULL,
    received_at TEXT NOT NULL,
    source_content_hash TEXT,
    UNIQUE (session_date, source, source_content_hash)
);

CREATE INDEX idx_factor_observations_asof
    ON factor_observations (session_date, received_at);

CREATE TABLE outcome_labels (
    event_id TEXT NOT NULL,
    label_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (event_id, label_version)
);

INSERT INTO market_schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
