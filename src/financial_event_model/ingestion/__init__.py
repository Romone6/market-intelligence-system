"""SEC source ingestion."""

from .sec import (
    CompanyIngestionResult,
    FilingReference,
    SecCollector,
    SecDownloadError,
    SecFetchResult,
    SecIngestor,
    StoredDocument,
    SubmissionDocument,
    historical_submission_files,
    parse_submission_documents,
    parse_submission_filings,
)

__all__ = [
    "CompanyIngestionResult",
    "FilingReference",
    "SecCollector",
    "SecDownloadError",
    "SecFetchResult",
    "SecIngestor",
    "StoredDocument",
    "SubmissionDocument",
    "historical_submission_files",
    "parse_submission_documents",
    "parse_submission_filings",
]
