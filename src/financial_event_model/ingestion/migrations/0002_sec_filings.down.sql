BEGIN IMMEDIATE;

DROP INDEX IF EXISTS idx_sec_filings_cik_accepted;
DROP TABLE IF EXISTS sec_filings;
DELETE FROM sec_schema_migrations WHERE version = 2;

COMMIT;
