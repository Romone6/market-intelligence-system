"""Policy-compliant SEC raw-data collection and filing discovery."""

import gzip
import hashlib
import json
import re
import sqlite3
import time
import zlib
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import AwareDatetime, Field

from financial_event_model.contracts import Contract
from financial_event_model.identifiers import normalize_cik


SEC_HOSTS = {"data.sec.gov", "www.sec.gov"}
RETRY_HTTP_STATUSES = {429, 500, 502, 503, 504}


class SecDownloadError(RuntimeError):
    """Raised after a SEC request reaches a terminal failure."""


class SecFetchResult(Contract):
    request_id: int
    request_url: str
    requested_at: AwareDatetime
    response_received_at: AwareDatetime
    http_status: int
    content_type: str | None
    source_last_modified: str | None
    content_hash: str = Field(min_length=64, max_length=64)
    collector_version: str
    local_path: Path
    accession_number: str | None
    document_role: str | None
    content_changed: bool
    cached: bool = False


class FilingReference(Contract):
    cik: str
    accession_number: str
    filing_date: date
    acceptance_at: AwareDatetime | None
    form: str
    primary_document: str
    items: tuple[str, ...]
    is_amendment: bool

    @property
    def archive_directory_url(self) -> str:
        return (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{int(self.cik)}/{self.accession_number.replace('-', '')}"
        )

    @property
    def primary_document_url(self) -> str:
        return f"{self.archive_directory_url}/{self.primary_document}"

    @property
    def complete_submission_url(self) -> str:
        return f"{self.archive_directory_url}/{self.accession_number}.txt"

    @property
    def filing_index_url(self) -> str:
        return f"{self.archive_directory_url}/{self.accession_number}-index.html"


class SubmissionDocument(Contract):
    accession_number: str
    document_type: str | None
    sequence: str | None
    filename: str | None
    description: str | None
    raw_content: bytes
    content_hash: str = Field(min_length=64, max_length=64)


class StoredDocument(Contract):
    document_id: int
    accession_number: str
    document_type: str | None
    sequence: str | None
    filename: str | None
    description: str | None
    content_hash: str = Field(min_length=64, max_length=64)
    local_path: Path
    source_request_id: int


class CompanyIngestionResult(Contract):
    cik: str
    submissions: SecFetchResult
    historical_submissions: tuple[SecFetchResult, ...]
    companyfacts: SecFetchResult | None
    filings: tuple[FilingReference, ...]
    source_results: tuple[SecFetchResult, ...]
    documents: tuple[StoredDocument, ...]


class SecCollector:
    def __init__(
        self,
        *,
        raw_root: str | Path,
        manifest_path: str | Path,
        user_agent: str,
        collector_version: str,
        max_requests_per_second: float = 8,
        max_retries: int = 3,
        timeout: float = 30,
        open_url: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if len(user_agent.split()) < 2 or re.search(r"\S+@\S+\.\S+", user_agent) is None:
            raise ValueError("SEC user agent must identify a company/contact email")
        if not 0 < max_requests_per_second <= 10:
            raise ValueError("max_requests_per_second must be between 0 and 10")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.raw_root = Path(raw_root)
        self.manifest_path = Path(manifest_path)
        self.user_agent = user_agent
        self.collector_version = collector_version
        self.minimum_interval = 1 / max_requests_per_second
        self.max_retries = max_retries
        self.timeout = timeout
        self.open_url = open_url
        self.sleep = sleep
        self._last_request_at: float | None = None
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def fetch(
        self,
        url: str,
        *,
        accession_number: str | None = None,
        document_role: str | None = None,
        force: bool = False,
    ) -> SecFetchResult:
        self._validate_url(url)
        previous = self._latest_success(url)
        if not force and previous is not None and Path(previous["local_path"]).is_file():
            return self._result_from_row(
                previous,
                cached=True,
                accession_number=accession_number,
                document_role=document_role,
            )

        for attempt in range(self.max_retries + 1):
            self._throttle()
            requested_at = datetime.now(timezone.utc)
            request = Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            try:
                with self.open_url(request, timeout=self.timeout) as response:
                    body = _decode_body(response.read(), response.headers)
                    received_at = datetime.now(timezone.utc)
                    status = int(response.status)
                    content_type = _media_type(response.headers.get("Content-Type"))
                    source_last_modified = response.headers.get("Last-Modified")
                content_hash = hashlib.sha256(body).hexdigest()
                local_path = self._store_raw(body, content_hash, content_type, url)
                content_changed = (
                    previous is not None
                    and previous["content_hash"] != content_hash
                )
                request_id = self._record_attempt(
                    request_url=url,
                    requested_at=requested_at,
                    response_received_at=received_at,
                    http_status=status,
                    content_type=content_type,
                    source_last_modified=source_last_modified,
                    content_hash=content_hash,
                    local_path=local_path,
                    accession_number=accession_number,
                    document_role=document_role,
                    content_changed=content_changed,
                    error=None,
                )
                return SecFetchResult(
                    request_id=request_id,
                    request_url=url,
                    requested_at=requested_at,
                    response_received_at=received_at,
                    http_status=status,
                    content_type=content_type,
                    source_last_modified=source_last_modified,
                    content_hash=content_hash,
                    collector_version=self.collector_version,
                    local_path=local_path,
                    accession_number=accession_number,
                    document_role=document_role,
                    content_changed=content_changed,
                )
            except HTTPError as error:
                received_at = datetime.now(timezone.utc)
                message = f"HTTP {error.code}: {error.reason}"
                self._record_attempt(
                    request_url=url,
                    requested_at=requested_at,
                    response_received_at=received_at,
                    http_status=error.code,
                    content_type=_media_type(error.headers.get("Content-Type")),
                    source_last_modified=error.headers.get("Last-Modified"),
                    content_hash=None,
                    local_path=None,
                    accession_number=accession_number,
                    document_role=document_role,
                    content_changed=False,
                    error=message,
                )
                if error.code in RETRY_HTTP_STATUSES and attempt < self.max_retries:
                    self.sleep(_retry_delay(error.headers.get("Retry-After"), attempt))
                    continue
                raise SecDownloadError(message) from error
            except (URLError, OSError) as error:
                received_at = datetime.now(timezone.utc)
                message = f"network error: {error}"
                self._record_attempt(
                    request_url=url,
                    requested_at=requested_at,
                    response_received_at=received_at,
                    http_status=None,
                    content_type=None,
                    source_last_modified=None,
                    content_hash=None,
                    local_path=None,
                    accession_number=accession_number,
                    document_role=document_role,
                    content_changed=False,
                    error=message,
                )
                if attempt < self.max_retries:
                    self.sleep(float(2**attempt))
                    continue
                raise SecDownloadError(message) from error

        raise AssertionError("retry loop exited without returning or raising")

    def store_documents(
        self,
        source: SecFetchResult,
        documents: tuple[SubmissionDocument, ...],
    ) -> tuple[StoredDocument, ...]:
        stored = []
        for document in documents:
            local_path = self._store_raw(
                document.raw_content,
                document.content_hash,
                None,
                document.filename or "document.txt",
            )
            created_at = datetime.now(timezone.utc).isoformat()
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO sec_documents (
                        accession_number,
                        document_type,
                        sequence,
                        filename,
                        description,
                        content_hash,
                        local_path,
                        source_request_id,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.accession_number,
                        document.document_type,
                        document.sequence,
                        document.filename,
                        document.description,
                        document.content_hash,
                        str(local_path),
                        source.request_id,
                        created_at,
                    ),
                )
                row = connection.execute(
                    """
                    SELECT *
                    FROM sec_documents
                    WHERE accession_number = ?
                      AND sequence IS ?
                      AND filename IS ?
                      AND content_hash = ?
                    """,
                    (
                        document.accession_number,
                        document.sequence,
                        document.filename,
                        document.content_hash,
                    ),
                ).fetchone()
            stored.append(
                StoredDocument(
                    document_id=row["document_id"],
                    accession_number=row["accession_number"],
                    document_type=row["document_type"],
                    sequence=row["sequence"],
                    filename=row["filename"],
                    description=row["description"],
                    content_hash=row["content_hash"],
                    local_path=Path(row["local_path"]),
                    source_request_id=row["source_request_id"],
                )
            )
        return tuple(stored)

    def store_filings(
        self,
        source: SecFetchResult,
        filings: tuple[FilingReference, ...],
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO sec_filings (
                    accession_number, cik, filing_date, acceptance_at, form,
                    primary_document, items_json, is_amendment,
                    metadata_request_id, first_observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (accession_number) DO UPDATE SET
                    cik = excluded.cik,
                    filing_date = excluded.filing_date,
                    acceptance_at = excluded.acceptance_at,
                    form = excluded.form,
                    primary_document = excluded.primary_document,
                    items_json = excluded.items_json,
                    is_amendment = excluded.is_amendment,
                    metadata_request_id = excluded.metadata_request_id,
                    first_observed_at = min(
                        sec_filings.first_observed_at,
                        excluded.first_observed_at
                    )
                """,
                [
                    (
                        filing.accession_number,
                        filing.cik,
                        filing.filing_date.isoformat(),
                        (
                            filing.acceptance_at.isoformat()
                            if filing.acceptance_at is not None
                            else None
                        ),
                        filing.form,
                        filing.primary_document,
                        json.dumps(filing.items),
                        int(filing.is_amendment),
                        source.request_id,
                        source.response_received_at.isoformat(),
                        created_at,
                    )
                    for filing in filings
                ],
            )

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sec_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                int(row[0])
                for row in connection.execute(
                    "SELECT version FROM sec_schema_migrations"
                ).fetchall()
            }
            migration_root = Path(__file__).with_name("migrations")
            for path in sorted(migration_root.glob("[0-9][0-9][0-9][0-9]_*.sql")):
                version = int(path.name[:4])
                if version not in applied:
                    connection.executescript(path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.manifest_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def _latest_success(self, url: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM sec_requests
                WHERE request_url = ?
                  AND http_status BETWEEN 200 AND 299
                  AND content_hash IS NOT NULL
                ORDER BY request_id DESC
                LIMIT 1
                """,
                (url,),
            ).fetchone()

    def _record_attempt(
        self,
        *,
        request_url: str,
        requested_at: datetime,
        response_received_at: datetime,
        http_status: int | None,
        content_type: str | None,
        source_last_modified: str | None,
        content_hash: str | None,
        local_path: Path | None,
        accession_number: str | None,
        document_role: str | None,
        content_changed: bool,
        error: str | None,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sec_requests (
                    request_url,
                    requested_at,
                    response_received_at,
                    http_status,
                    content_type,
                    source_last_modified,
                    content_hash,
                    collector_version,
                    local_path,
                    accession_number,
                    document_role,
                    content_changed,
                    error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_url,
                    requested_at.isoformat(),
                    response_received_at.isoformat(),
                    http_status,
                    content_type,
                    source_last_modified,
                    content_hash,
                    self.collector_version,
                    str(local_path) if local_path is not None else None,
                    accession_number,
                    document_role,
                    int(content_changed),
                    error,
                ),
            )
            return int(cursor.lastrowid)

    def _store_raw(
        self,
        body: bytes,
        content_hash: str,
        content_type: str | None,
        url: str,
    ) -> Path:
        extension = _extension(content_type, url)
        destination = self.raw_root / "sec" / content_hash[:2] / f"{content_hash}{extension}"
        if destination.exists():
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
        temporary.write_bytes(body)
        temporary.replace(destination)
        return destination

    def _result_from_row(
        self,
        row: sqlite3.Row,
        *,
        cached: bool,
        accession_number: str | None = None,
        document_role: str | None = None,
    ) -> SecFetchResult:
        return SecFetchResult(
            request_id=row["request_id"],
            request_url=row["request_url"],
            requested_at=datetime.fromisoformat(row["requested_at"]),
            response_received_at=datetime.fromisoformat(row["response_received_at"]),
            http_status=row["http_status"],
            content_type=row["content_type"],
            source_last_modified=row["source_last_modified"],
            content_hash=row["content_hash"],
            collector_version=row["collector_version"],
            local_path=Path(row["local_path"]),
            accession_number=accession_number or row["accession_number"],
            document_role=document_role or row["document_role"],
            content_changed=bool(row["content_changed"]),
            cached=cached,
        )

    def _throttle(self) -> None:
        now = time.monotonic()
        if self._last_request_at is not None:
            remaining = self.minimum_interval - (now - self._last_request_at)
            if remaining > 0:
                self.sleep(remaining)
        self._last_request_at = time.monotonic()

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in SEC_HOSTS:
            raise ValueError("SEC collector accepts only official SEC HTTPS hosts")


class SecIngestor:
    def __init__(self, collector: SecCollector) -> None:
        self.collector = collector

    def collect_company(
        self,
        cik: str,
        start: date,
        end: date,
        forms: set[str],
        *,
        include_companyfacts: bool = True,
    ) -> CompanyIngestionResult:
        normalized_cik = normalize_cik(cik)
        submissions = self.collector.fetch(
            f"https://data.sec.gov/submissions/CIK{normalized_cik}.json",
            document_role="submissions",
        )
        root_payload = _load_json(submissions.local_path)
        current_filings = parse_submission_filings(
            root_payload, normalized_cik, start, end, forms
        )
        self.collector.store_filings(submissions, current_filings)
        filing_by_accession = {
            filing.accession_number: filing
            for filing in current_filings
        }

        historical_results = []
        for filename in historical_submission_files(root_payload, start, end):
            result = self.collector.fetch(
                f"https://data.sec.gov/submissions/{filename}",
                document_role="historical_submissions",
            )
            historical_results.append(result)
            historical_filings = parse_submission_filings(
                _load_json(result.local_path), normalized_cik, start, end, forms
            )
            self.collector.store_filings(result, historical_filings)
            for filing in historical_filings:
                filing_by_accession.setdefault(filing.accession_number, filing)

        filings = tuple(
            sorted(
                filing_by_accession.values(),
                key=lambda item: (
                    item.acceptance_at
                    or datetime.combine(item.filing_date, datetime_time.min, timezone.utc),
                    item.accession_number,
                ),
            )
        )
        companyfacts = (
            self.collector.fetch(
                "https://data.sec.gov/api/xbrl/companyfacts/"
                f"CIK{normalized_cik}.json",
                document_role="companyfacts",
            )
            if include_companyfacts
            else None
        )

        source_results = []
        stored_documents = []
        for filing in filings:
            primary = self.collector.fetch(
                filing.primary_document_url,
                accession_number=filing.accession_number,
                document_role="primary_document",
            )
            complete = self.collector.fetch(
                filing.complete_submission_url,
                accession_number=filing.accession_number,
                document_role="complete_submission",
            )
            index = self.collector.fetch(
                filing.filing_index_url,
                accession_number=filing.accession_number,
                document_role="filing_index",
            )
            source_results.extend((primary, complete, index))
            documents = parse_submission_documents(
                complete.local_path.read_bytes(),
                filing.accession_number,
            )
            stored_documents.extend(self.collector.store_documents(complete, documents))

        return CompanyIngestionResult(
            cik=normalized_cik,
            submissions=submissions,
            historical_submissions=tuple(historical_results),
            companyfacts=companyfacts,
            filings=filings,
            source_results=tuple(source_results),
            documents=tuple(stored_documents),
        )


def _decode_body(body: bytes, headers: Any) -> bytes:
    encoding = (headers.get("Content-Encoding") or "").casefold()
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    return body


def _media_type(content_type: str | None) -> str | None:
    return content_type.split(";", 1)[0].strip().casefold() if content_type else None


def _extension(content_type: str | None, url: str) -> str:
    known = {
        "application/json": ".json",
        "application/xml": ".xml",
        "text/html": ".html",
        "text/plain": ".txt",
        "text/xml": ".xml",
    }
    if content_type in known:
        return known[content_type]
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if 1 < len(suffix) <= 10 else ".bin"


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after is not None and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    return min(float(2**attempt), 60.0)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"SEC JSON root must be an object: {path}")
    return payload


def parse_submission_filings(
    payload: dict[str, Any],
    cik: str,
    start: date,
    end: date,
    forms: set[str],
) -> tuple[FilingReference, ...]:
    if end < start:
        raise ValueError("end date must not precede start date")
    normalized_cik = normalize_cik(cik)
    filings = payload.get("filings")
    columns = filings.get("recent", {}) if isinstance(filings, dict) else payload
    accessions = _required_column(columns, "accessionNumber")
    filing_dates = _required_column(columns, "filingDate")
    form_values = _required_column(columns, "form")
    primary_documents = _required_column(columns, "primaryDocument")
    acceptance_values = columns.get("acceptanceDateTime", [])
    item_values = columns.get("items", [])
    lengths = {len(accessions), len(filing_dates), len(form_values), len(primary_documents)}
    if len(lengths) != 1:
        raise ValueError("SEC submissions columns have inconsistent lengths")

    references: list[FilingReference] = []
    for index, accession in enumerate(accessions):
        filing_date = date.fromisoformat(filing_dates[index])
        form = form_values[index]
        if not start <= filing_date <= end or form not in forms:
            continue
        acceptance_value = _optional_column_value(acceptance_values, index)
        items_value = _optional_column_value(item_values, index) or ""
        references.append(
            FilingReference(
                cik=normalized_cik,
                accession_number=accession,
                filing_date=filing_date,
                acceptance_at=_parse_sec_datetime(acceptance_value),
                form=form,
                primary_document=primary_documents[index],
                items=tuple(
                    item.strip() for item in items_value.split(",") if item.strip()
                ),
                is_amendment=form.endswith("/A"),
            )
        )

    def sort_key(reference: FilingReference) -> tuple[datetime, str]:
        accepted = reference.acceptance_at or datetime.combine(
            reference.filing_date,
            datetime_time.min,
            timezone.utc,
        )
        return accepted, reference.accession_number

    return tuple(sorted(references, key=sort_key))


def historical_submission_files(
    payload: dict[str, Any],
    start: date,
    end: date,
) -> tuple[str, ...]:
    if end < start:
        raise ValueError("end date must not precede start date")
    filings = payload.get("filings")
    file_entries = filings.get("files", []) if isinstance(filings, dict) else []
    selected = []
    for entry in file_entries:
        file_start = date.fromisoformat(entry["filingFrom"])
        file_end = date.fromisoformat(entry["filingTo"])
        if file_start <= end and file_end >= start:
            selected.append(entry["name"])
    return tuple(selected)


def parse_submission_documents(
    raw_submission: bytes,
    accession_number: str,
) -> tuple[SubmissionDocument, ...]:
    documents = []
    for match in re.finditer(
        rb"<DOCUMENT\s*>(.*?)</DOCUMENT\s*>",
        raw_submission,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_content = match.group(0)
        documents.append(
            SubmissionDocument(
                accession_number=accession_number,
                document_type=_sgml_tag(raw_content, b"TYPE"),
                sequence=_sgml_tag(raw_content, b"SEQUENCE"),
                filename=_sgml_tag(raw_content, b"FILENAME"),
                description=_sgml_tag(raw_content, b"DESCRIPTION"),
                raw_content=raw_content,
                content_hash=hashlib.sha256(raw_content).hexdigest(),
            )
        )
    return tuple(documents)


def _required_column(columns: dict[str, Any], name: str) -> list[str]:
    values = columns.get(name)
    if not isinstance(values, list):
        raise ValueError(f"SEC submissions column is missing: {name}")
    return values


def _optional_column_value(values: Any, index: int) -> str | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    return value if isinstance(value, str) and value else None


def _parse_sec_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sgml_tag(document: bytes, tag: bytes) -> str | None:
    match = re.search(
        rb"<" + tag + rb">\s*([^\r\n<]*)",
        document,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group(1).decode("utf-8", errors="replace").strip() or None
