BEGIN IMMEDIATE;

DROP INDEX IF EXISTS idx_sec_documents_accession;
DROP INDEX IF EXISTS idx_sec_documents_identity;
DROP INDEX IF EXISTS idx_sec_requests_accession;
DROP INDEX IF EXISTS idx_sec_requests_resume;
DROP TABLE IF EXISTS sec_documents;
DROP TABLE IF EXISTS sec_requests;
DELETE FROM sec_schema_migrations WHERE version = 1;

COMMIT;
