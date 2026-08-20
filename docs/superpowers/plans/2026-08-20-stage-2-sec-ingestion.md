# Stage 2 SEC Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven development and execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect SEC submissions and filing source material into immutable, content-addressed storage with complete request provenance and accession-level document linkage.

**Architecture:** Use the Python standard library for HTTPS, compression, hashing, filesystem writes, HTML-independent EDGAR SGML splitting, and SQLite manifesting. One `SecCollector` owns policy-compliant fetching and one parser layer turns SEC submissions metadata and complete-submission files into typed references without normalizing filing content.

**Tech Stack:** Python 3.11+, `urllib`, `sqlite3`, `hashlib`, Pydantic 2, pytest.

## Global Constraints

- Send a declared company/contact `User-Agent`; refuse live collection when `SEC_USER_AGENT` is absent or malformed.
- Stay below the SEC maximum of 10 requests per second; repository default is 8.
- Preserve every received raw response byte-for-byte before parsing.
- Record requested/received timestamps, status, content type, last-modified value, hash, collector version, local path, accession, and failure details.
- Retry only temporary network failures and HTTP 429/500/502/503/504 responses.
- Treat each accession, including `/A` amendments, as a distinct filing.
- Do not feed SEC HTML or extracted documents into a model in this stage.
- Fixture tests prove collector semantics; the 50-company live acceptance gate requires an explicit `SEC_USER_AGENT` and a reviewed CIK/date manifest.

---

### Task 1: Append-only request manifest and immutable raw store

**Files:**
- Create: `src/financial_event_model/ingestion/sec.py`
- Create: `src/financial_event_model/ingestion/migrations/0001_sec_manifest.sql`
- Create: `src/financial_event_model/ingestion/migrations/0001_sec_manifest.down.sql`
- Create: `src/financial_event_model/ingestion/__init__.py`
- Test: `tests/test_sec_ingestion.py`

**Interfaces:**
- Produces: `SecCollector(raw_root, manifest_path, user_agent, collector_version, max_requests_per_second, max_retries, open_url, sleep)`.
- Produces: `fetch(url, accession_number=None, document_role=None, force=False) -> SecFetchResult`.

- [x] **Step 1: Write the failing provenance test**

```python
result = collector.fetch(
    "https://data.sec.gov/submissions/CIK0000320193.json",
    document_role="submissions",
)
assert result.http_status == 200
assert result.content_hash == hashlib.sha256(payload).hexdigest()
assert result.local_path.read_bytes() == payload
assert result.content_type == "application/json"
```

The fake opener must inspect the request and assert the declared `User-Agent` plus `Accept-Encoding: gzip, deflate` headers.

- [x] **Step 2: Run the focused test red**

Run: `python -m pytest tests/test_sec_ingestion.py::test_collector_preserves_response_and_provenance -q`

Expected: FAIL because `financial_event_model.ingestion.SecCollector` does not exist.

- [x] **Step 3: Implement the additive manifest migration**

```sql
CREATE TABLE sec_requests (
    request_id INTEGER PRIMARY KEY,
    request_url TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    response_received_at TEXT NOT NULL,
    http_status INTEGER,
    content_type TEXT,
    source_last_modified TEXT,
    content_hash TEXT,
    collector_version TEXT NOT NULL,
    local_path TEXT,
    accession_number TEXT,
    document_role TEXT,
    content_changed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX idx_sec_requests_resume
    ON sec_requests (request_url, http_status, response_received_at);
CREATE INDEX idx_sec_requests_accession
    ON sec_requests (accession_number, document_role);
```

The forward migration also creates `sec_schema_migrations`; the down migration removes only Stage 2 tables and indexes.

- [x] **Step 4: Implement raw storage and verify green**

Use `<raw_root>/sec/<first two hash characters>/<hash>.<extension>` and atomic `Path.replace`. If the latest successful URL already has a present file, return it without another request unless `force=True`.

Run: `python -m pytest tests/test_sec_ingestion.py::test_collector_preserves_response_and_provenance -q`

Expected: PASS.

### Task 2: Retry, resumption, and content-change semantics

**Files:**
- Modify: `src/financial_event_model/ingestion/sec.py`
- Modify: `tests/test_sec_ingestion.py`

- [x] **Step 1: Write tests that require exact behavior**

```python
first = collector.fetch(url)
cached = collector.fetch(url)
changed = collector.fetch(url, force=True)
assert first.request_id == cached.request_id
assert changed.content_changed is True
assert opener.call_count == 2
```

Add a retry fixture whose first response raises HTTP 503 and second response succeeds. Assert both attempts are manifest rows, only temporary errors retry, and missing/failed local files are fetched again.

- [x] **Step 2: Run the retry/resume tests red**

Run: `python -m pytest tests/test_sec_ingestion.py -q`

Expected: FAIL on missing cache, retry, and change-detection behavior.

- [x] **Step 3: Implement the minimal retry loop**

Throttle with `time.monotonic`, use `Retry-After` when it is a non-negative integer, and otherwise use bounded exponential delays of 1, 2, and 4 seconds. Store a manifest row for every attempted HTTP request, including terminal failures.

- [x] **Step 4: Run the collector tests green**

Run: `python -m pytest tests/test_sec_ingestion.py -q`

Expected: PASS.

### Task 3: Filing discovery and accession-linked documents

**Files:**
- Modify: `src/financial_event_model/ingestion/sec.py`
- Modify: `src/financial_event_model/ingestion/__init__.py`
- Modify: `tests/test_sec_ingestion.py`

**Interfaces:**
- Produces: `parse_submission_filings(payload, cik, start, end, forms) -> tuple[FilingReference, ...]`.
- Produces: `historical_submission_files(payload, start, end) -> tuple[str, ...]`.
- Produces: `parse_submission_documents(raw_submission, accession_number) -> tuple[SubmissionDocument, ...]`.
- Produces: `SecIngestor(collector).collect_company(cik, start, end, forms, include_companyfacts) -> CompanyIngestionResult`.

- [x] **Step 1: Write parser tests**

```python
filings = parse_submission_filings(payload, "320193", start, end, {"8-K", "8-K/A"})
assert [filing.accession_number for filing in filings] == [
    "0000320193-24-000001",
    "0000320193-24-000002",
]
assert filings[1].is_amendment is True
```

The SGML fixture must contain a primary 8-K and an `EX-99.1`; assert exact raw bytes, sequence, filename, description, type, and shared parent accession.

- [x] **Step 2: Run parser tests red**

Run: `python -m pytest tests/test_sec_ingestion.py -q`

Expected: FAIL because discovery and document parsers do not exist.

- [x] **Step 3: Implement columnar metadata and SGML parsing**

Recent submissions live under `filings.recent`; historical submission files use the same column arrays at the JSON root. Filter by inclusive filing dates and exact form names, keep amendments distinct, and sort by acceptance time then accession. Split only complete `<DOCUMENT>...</DOCUMENT>` blocks and preserve each block exactly.

- [x] **Step 4: Implement and test one-company orchestration**

```python
result = SecIngestor(collector).collect_company(
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
assert result.documents[0].accession_number == result.filings[0].accession_number
```

The orchestrator fetches relevant historical submissions files, deduplicates filing references by accession, optionally captures Company Facts once per CIK, downloads three source objects per filing, parses complete-submission documents, and persists exact blocks in `sec_documents` linked to the complete-submission request.

- [x] **Step 5: Run parser and orchestration tests green**

Run: `python -m pytest tests/test_sec_ingestion.py -q`

Expected: PASS.

### Task 4: Documentation and complete verification

**Files:**
- Create: `docs/STAGE_2_SEC_INGESTION.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: `pyproject.toml`

- [x] Package the Stage 2 SQL migration files and document `SEC_USER_AGENT`, the 8 requests/second default, live acceptance command shape, and proof boundary.
- [x] Run `python -m pip install -e ".[dev]"`.
- [x] Run `python -m pytest` and `python -m compileall -q src tests`.
- [x] Run `git diff --check`, inspect the staged diff, and create a Conventional Commit after all checks pass.
