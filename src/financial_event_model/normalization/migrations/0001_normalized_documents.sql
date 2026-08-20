BEGIN IMMEDIATE;

CREATE TABLE normalized_documents (
    normalization_id INTEGER PRIMARY KEY,
    source_document_id INTEGER NOT NULL,
    source_content_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    output_hash TEXT,
    local_path TEXT,
    parent_document_id INTEGER,
    is_exhibit INTEGER NOT NULL,
    language TEXT,
    parsing_quality REAL,
    warnings_json TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (source_document_id, parser_version),
    CHECK (success IN (0, 1)),
    CHECK (is_exhibit IN (0, 1)),
    CHECK (parsing_quality IS NULL OR parsing_quality BETWEEN 0.0 AND 1.0)
);

CREATE INDEX idx_normalized_documents_source
    ON normalized_documents (source_document_id, parser_version, success);
CREATE INDEX idx_normalized_documents_parent
    ON normalized_documents (parent_document_id, is_exhibit);

INSERT INTO normalization_schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

COMMIT;
