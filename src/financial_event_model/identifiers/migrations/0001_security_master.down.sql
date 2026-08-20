BEGIN IMMEDIATE;

DROP INDEX IF EXISTS idx_universe_membership_lookup;
DROP INDEX IF EXISTS uq_identifier_history_version;
DROP INDEX IF EXISTS idx_identifier_history_lookup;
DROP INDEX IF EXISTS idx_securities_entity_validity;
DROP INDEX IF EXISTS idx_entities_cik_validity;
DROP TABLE IF EXISTS universe_membership;
DROP TABLE IF EXISTS identifier_history;
DROP TABLE IF EXISTS securities;
DROP TABLE IF EXISTS entities;
DELETE FROM schema_migrations WHERE version = 1;

COMMIT;
