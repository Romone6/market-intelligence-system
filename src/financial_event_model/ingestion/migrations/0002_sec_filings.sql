BEGIN IMMEDIATE;

CREATE TABLE sec_filings (
    accession_number TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    acceptance_at TEXT,
    form TEXT NOT NULL,
    primary_document TEXT NOT NULL,
    items_json TEXT NOT NULL,
    is_amendment INTEGER NOT NULL,
    metadata_request_id INTEGER NOT NULL,
    first_observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (is_amendment IN (0, 1)),
    FOREIGN KEY (metadata_request_id) REFERENCES sec_requests(request_id)
);

CREATE INDEX idx_sec_filings_cik_accepted
    ON sec_filings (cik, acceptance_at, accession_number);

INSERT INTO sec_schema_migrations (version, applied_at)
VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
