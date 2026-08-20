BEGIN IMMEDIATE;

DROP INDEX IF EXISTS idx_normalized_documents_parent;
DROP INDEX IF EXISTS idx_normalized_documents_source;
DROP TABLE IF EXISTS normalized_documents;
DELETE FROM normalization_schema_migrations WHERE version = 1;

COMMIT;
