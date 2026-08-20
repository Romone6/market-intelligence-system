BEGIN IMMEDIATE;

DROP INDEX IF EXISTS idx_corporate_actions_asof;
DROP TABLE IF EXISTS corporate_actions;
DELETE FROM market_schema_migrations WHERE version = 2;

COMMIT;
