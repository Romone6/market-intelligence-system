BEGIN IMMEDIATE;

DROP TABLE IF EXISTS outcome_labels;
DROP INDEX IF EXISTS idx_factor_observations_asof;
DROP TABLE IF EXISTS factor_observations;
DROP INDEX IF EXISTS idx_market_bars_asof;
DROP TABLE IF EXISTS market_bars;
DROP TABLE IF EXISTS market_requests;
DELETE FROM market_schema_migrations WHERE version = 1;

COMMIT;
