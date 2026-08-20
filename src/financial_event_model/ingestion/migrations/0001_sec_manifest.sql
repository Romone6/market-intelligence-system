BEGIN IMMEDIATE;

CREATE TABLE sec_requests (
    request_id INTEGER PRIMARY KEY,
    request_url TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    response_received_at TEXT NOT NULL,
    http_status INTEGER,
    content_type TEXT,
    source_last_modified TEXT,
    content_hash TEXT,
    collector_version TEXT NOT NULL,
    local_path TEXT,
    accession_number TEXT,
    document_role TEXT,
    content_changed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE INDEX idx_sec_requests_resume
    ON sec_requests (request_url, http_status, response_received_at);
CREATE INDEX idx_sec_requests_accession
    ON sec_requests (accession_number, document_role);

CREATE TABLE sec_documents (
    document_id INTEGER PRIMARY KEY,
    accession_number TEXT NOT NULL,
    document_type TEXT,
    sequence TEXT,
    filename TEXT,
    description TEXT,
    content_hash TEXT NOT NULL,
    local_path TEXT NOT NULL,
    source_request_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (accession_number, sequence, filename, content_hash),
    FOREIGN KEY (source_request_id) REFERENCES sec_requests(request_id)
);

CREATE INDEX idx_sec_documents_accession
    ON sec_documents (accession_number, sequence);
CREATE UNIQUE INDEX idx_sec_documents_identity
    ON sec_documents (
        accession_number,
        COALESCE(sequence, ''),
        COALESCE(filename, ''),
        content_hash
    );

INSERT INTO sec_schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
