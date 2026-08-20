BEGIN IMMEDIATE;

DROP INDEX IF EXISTS idx_knowledge_source_policy;
DROP INDEX IF EXISTS idx_knowledge_entity_time;
DROP TABLE IF EXISTS knowledge_records;
DELETE FROM temporal_schema_migrations WHERE version = 1;

COMMIT;
