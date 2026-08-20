import hashlib
import json
import sqlite3
from datetime import date
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str], status: int = 200) -> None:
        self.body = body
        self.headers = Message()
        for name, value in headers.items():
            self.headers[name] = value
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeOpener:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.requests = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def __call__(self, request, timeout: float):
        self.requests.append((request, timeout))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _collector(tmp_path, opener, **overrides):
    from financial_event_model.ingestion import SecCollector

    return SecCollector(
        raw_root=tmp_path / "raw",
        manifest_path=tmp_path / "sec_manifest.sqlite3",
        user_agent="Quani Hoott Research admin@example.com",
        collector_version="sec-collector-v0.1",
        max_requests_per_second=8,
        max_retries=overrides.get("max_retries", 0),
        open_url=opener,
        sleep=overrides.get("sleep", lambda _seconds: None),
    )


def test_collector_preserves_response_and_provenance(tmp_path) -> None:
    payload = b'{"cik":"0000320193"}'
    opener = FakeOpener(
        FakeResponse(
            payload,
            {
                "Content-Type": "application/json; charset=utf-8",
                "Last-Modified": "Wed, 19 Aug 2026 12:00:00 GMT",
            },
        )
    )
    collector = _collector(tmp_path, opener)

    result = collector.fetch(
        "https://data.sec.gov/submissions/CIK0000320193.json",
        document_role="submissions",
    )

    request, timeout = opener.requests[0]
    assert request.get_header("User-agent") == "Quani Hoott Research admin@example.com"
    assert request.get_header("Accept-encoding") == "gzip, deflate"
    assert timeout == 30
    assert result.http_status == 200
    assert result.content_hash == hashlib.sha256(payload).hexdigest()
    assert result.local_path.read_bytes() == payload
    assert result.content_type == "application/json"
    assert result.source_last_modified == "Wed, 19 Aug 2026 12:00:00 GMT"
    assert result.document_role == "submissions"

    with sqlite3.connect(tmp_path / "sec_manifest.sqlite3") as connection:
        row = connection.execute(
            """
            SELECT request_url, http_status, content_hash, collector_version,
                   local_path, document_role, error
            FROM sec_requests
            """
        ).fetchone()
    assert row == (
        "https://data.sec.gov/submissions/CIK0000320193.json",
        200,
        hashlib.sha256(payload).hexdigest(),
        "sec-collector-v0.1",
        str(result.local_path),
        "submissions",
        None,
    )


def test_manifest_connections_enforce_foreign_keys(tmp_path) -> None:
    collector = _collector(tmp_path, FakeOpener())

    with collector._connect() as connection:
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1


def test_document_storage_deduplicates_missing_optional_metadata(tmp_path) -> None:
    from financial_event_model.ingestion import parse_submission_documents

    raw_document = b"<DOCUMENT>\n<TYPE>TEXT\n<TEXT>body</TEXT>\n</DOCUMENT>"
    collector = _collector(
        tmp_path,
        FakeOpener(FakeResponse(raw_document, {"Content-Type": "text/plain"})),
    )
    source = collector.fetch(
        "https://www.sec.gov/Archives/edgar/data/320193/submission.txt",
        accession_number="0000320193-24-000001",
        document_role="complete_submission",
    )
    documents = parse_submission_documents(raw_document, source.accession_number)

    first = collector.store_documents(source, documents)
    second = collector.store_documents(source, documents)

    assert first[0].document_id == second[0].document_id
    with sqlite3.connect(tmp_path / "sec_manifest.sqlite3") as connection:
        count = connection.execute("SELECT COUNT(*) FROM sec_documents").fetchone()[0]
    assert count == 1


def test_collector_resumes_and_detects_forced_content_changes(tmp_path) -> None:
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    first_body = b'{"version":1}'
    changed_body = b'{"version":2}'
    opener = FakeOpener(
        FakeResponse(first_body, {"Content-Type": "application/json"}),
        FakeResponse(changed_body, {"Content-Type": "application/json"}),
    )
    collector = _collector(tmp_path, opener)

    first = collector.fetch(url)
    cached = collector.fetch(url)
    changed = collector.fetch(url, force=True)

    assert cached.request_id == first.request_id
    assert cached.cached is True
    assert changed.request_id != first.request_id
    assert changed.content_changed is True
    assert changed.local_path.read_bytes() == changed_body
    assert opener.call_count == 2


def test_collector_records_and_retries_temporary_http_failures(tmp_path) -> None:
    url = "https://www.sec.gov/Archives/edgar/data/320193/example.txt"
    headers = Message()
    headers["Retry-After"] = "0"
    temporary = HTTPError(url, 503, "Service Unavailable", headers, BytesIO(b"busy"))
    opener = FakeOpener(
        temporary,
        FakeResponse(b"filing", {"Content-Type": "text/plain"}),
    )
    delays = []
    collector = _collector(
        tmp_path,
        opener,
        max_retries=1,
        sleep=delays.append,
    )

    result = collector.fetch(url, accession_number="0000320193-24-000001")

    assert result.http_status == 200
    assert opener.call_count == 2
    assert 0.0 in delays
    with sqlite3.connect(tmp_path / "sec_manifest.sqlite3") as connection:
        attempts = connection.execute(
            "SELECT http_status, error FROM sec_requests ORDER BY request_id"
        ).fetchall()
    assert attempts[0][0] == 503
    assert "Service Unavailable" in attempts[0][1]
    assert attempts[1] == (200, None)


def test_collector_rejects_undeclared_identity_and_non_sec_urls(tmp_path) -> None:
    from financial_event_model.ingestion import SecCollector

    with pytest.raises(ValueError, match="company/contact"):
        SecCollector(
            raw_root=tmp_path / "raw",
            manifest_path=tmp_path / "manifest.sqlite3",
            user_agent="anonymous",
            collector_version="v1",
        )

    collector = _collector(tmp_path, FakeOpener())
    with pytest.raises(ValueError, match="official SEC HTTPS hosts"):
        collector.fetch("https://example.com/not-sec")


def test_submission_discovery_preserves_amendments_and_history_files() -> None:
    from financial_event_model.ingestion import (
        historical_submission_files,
        parse_submission_filings,
    )

    payload = {
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-24-000001",
                    "0000320193-24-000002",
                    "0000320193-24-000003",
                ],
                "filingDate": ["2024-01-02", "2024-01-03", "2024-01-04"],
                "acceptanceDateTime": [
                    "2024-01-02T12:00:00.000Z",
                    "2024-01-03T12:00:00.000Z",
                    "2024-01-04T12:00:00.000Z",
                ],
                "form": ["8-K", "8-K/A", "4"],
                "primaryDocument": ["first.htm", "amended.htm", "owner.xml"],
                "items": ["2.02", "2.02", ""],
            },
            "files": [
                {
                    "name": "CIK0000320193-submissions-001.json",
                    "filingFrom": "2015-01-01",
                    "filingTo": "2019-12-31",
                },
                {
                    "name": "CIK0000320193-submissions-002.json",
                    "filingFrom": "2000-01-01",
                    "filingTo": "2014-12-31",
                },
            ],
        }
    }

    filings = parse_submission_filings(
        payload,
        "320193",
        date(2024, 1, 1),
        date(2024, 12, 31),
        {"8-K", "8-K/A"},
    )
    history = historical_submission_files(
        payload,
        date(2015, 1, 1),
        date(2020, 1, 1),
    )

    assert [filing.accession_number for filing in filings] == [
        "0000320193-24-000001",
        "0000320193-24-000002",
    ]
    assert filings[1].is_amendment is True
    assert filings[0].primary_document_url.endswith(
        "/320193/000032019324000001/first.htm"
    )
    assert filings[0].complete_submission_url.endswith(
        "/320193/000032019324000001/000032019324000001.txt"
    )
    assert history == ("CIK0000320193-submissions-001.json",)


def test_historical_submission_shape_and_sgml_documents_are_preserved() -> None:
    from financial_event_model.ingestion import (
        parse_submission_documents,
        parse_submission_filings,
    )

    historical_payload = {
        "accessionNumber": ["0000320193-18-000001"],
        "filingDate": ["2018-05-01"],
        "acceptanceDateTime": ["2018-05-01T16:30:00.000Z"],
        "form": ["10-Q"],
        "primaryDocument": ["quarter.htm"],
        "items": [""],
    }
    filings = parse_submission_filings(
        historical_payload,
        "320193",
        date(2018, 1, 1),
        date(2018, 12, 31),
        {"10-Q"},
    )
    primary = (
        b"<DOCUMENT>\n<TYPE>10-Q\n<SEQUENCE>1\n<FILENAME>quarter.htm\n"
        b"<DESCRIPTION>Quarterly report\n<TEXT>primary bytes</TEXT>\n</DOCUMENT>"
    )
    exhibit = (
        b"<DOCUMENT>\n<TYPE>EX-99.1\n<SEQUENCE>2\n<FILENAME>release.htm\n"
        b"<DESCRIPTION>Earnings release\n<TEXT>exhibit bytes</TEXT>\n</DOCUMENT>"
    )
    documents = parse_submission_documents(
        b"SEC-HEADER\n" + primary + b"\n" + exhibit,
        "0000320193-18-000001",
    )

    assert filings[0].form == "10-Q"
    assert len(documents) == 2
    assert documents[0].raw_content == primary
    assert documents[0].document_type == "10-Q"
    assert documents[0].sequence == "1"
    assert documents[1].raw_content == exhibit
    assert documents[1].document_type == "EX-99.1"
    assert documents[1].filename == "release.htm"
    assert documents[1].description == "Earnings release"
    assert documents[1].accession_number == "0000320193-18-000001"
    assert documents[1].content_hash == hashlib.sha256(exhibit).hexdigest()


def test_ingestor_collects_and_resumes_one_company_with_linked_documents(tmp_path) -> None:
    from financial_event_model.ingestion import SecIngestor

    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-24-000001"],
                "filingDate": ["2024-01-02"],
                "acceptanceDateTime": ["2024-01-02T12:00:00.000Z"],
                "form": ["8-K"],
                "primaryDocument": ["first.htm"],
                "items": ["2.02"],
            },
            "files": [],
        }
    }
    primary = b"<html>primary filing</html>"
    complete = (
        b"<DOCUMENT>\n<TYPE>8-K\n<SEQUENCE>1\n<FILENAME>first.htm\n"
        b"<DESCRIPTION>Current report\n<TEXT>primary</TEXT>\n</DOCUMENT>\n"
        b"<DOCUMENT>\n<TYPE>EX-99.1\n<SEQUENCE>2\n<FILENAME>release.htm\n"
        b"<DESCRIPTION>Press release\n<TEXT>exhibit</TEXT>\n</DOCUMENT>"
    )
    index = b"<html>filing index</html>"
    opener = FakeOpener(
        FakeResponse(json.dumps(submissions).encode(), {"Content-Type": "application/json"}),
        FakeResponse(primary, {"Content-Type": "text/html"}),
        FakeResponse(complete, {"Content-Type": "text/plain"}),
        FakeResponse(index, {"Content-Type": "text/html"}),
    )
    collector = _collector(tmp_path, opener)
    ingestor = SecIngestor(collector)

    result = ingestor.collect_company(
        "320193",
        date(2024, 1, 1),
        date(2024, 12, 31),
        {"8-K", "8-K/A"},
        include_companyfacts=False,
    )
    resumed = ingestor.collect_company(
        "320193",
        date(2024, 1, 1),
        date(2024, 12, 31),
        {"8-K", "8-K/A"},
        include_companyfacts=False,
    )

    assert len(result.filings) == 1
    assert {item.document_role for item in result.source_results} == {
        "primary_document",
        "complete_submission",
        "filing_index",
    }
    assert len(result.documents) == 2
    assert result.documents[1].document_type == "EX-99.1"
    assert result.documents[1].accession_number == result.filings[0].accession_number
    assert result.documents[1].local_path.read_bytes().endswith(b"</DOCUMENT>")
    assert resumed.submissions.cached is True
    assert all(item.cached for item in resumed.source_results)
    assert opener.call_count == 4

    with sqlite3.connect(tmp_path / "sec_manifest.sqlite3") as connection:
        linked = connection.execute(
            """
            SELECT document_type, accession_number, source_request_id
            FROM sec_documents
            ORDER BY sequence
            """
        ).fetchall()
    complete_request_id = next(
        item.request_id
        for item in result.source_results
        if item.document_role == "complete_submission"
    )
    assert linked == [
        ("8-K", "0000320193-24-000001", complete_request_id),
        ("EX-99.1", "0000320193-24-000001", complete_request_id),
    ]
