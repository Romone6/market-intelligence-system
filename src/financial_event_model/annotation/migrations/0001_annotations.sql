CREATE TABLE annotation_tasks (
    event_id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    related_event_group TEXT,
    source_published_at TEXT NOT NULL,
    tradable_at TEXT NOT NULL,
    filing_type TEXT NOT NULL,
    annotation_round TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX annotation_tasks_round_idx
    ON annotation_tasks (annotation_round, event_id);
CREATE INDEX annotation_tasks_entity_idx
    ON annotation_tasks (entity_id, related_event_group);

CREATE TABLE annotations (
    annotation_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES annotation_tasks(event_id),
    annotator_id TEXT NOT NULL,
    ontology_version TEXT NOT NULL,
    labels_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    evidence_spans_json TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    ambiguity_flag INTEGER NOT NULL CHECK (ambiguity_flag IN (0, 1)),
    no_material_event INTEGER NOT NULL CHECK (no_material_event IN (0, 1)),
    created_at TEXT NOT NULL,
    supersedes_annotation_id TEXT UNIQUE REFERENCES annotations(annotation_id),
    adjudication_status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX annotations_event_annotator_idx
    ON annotations (event_id, annotator_id, created_at);

CREATE TABLE annotation_releases (
    release_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    ontology_version TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO annotation_schema_migrations (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
