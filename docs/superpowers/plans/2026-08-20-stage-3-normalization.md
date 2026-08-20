# Stage 3 Normalization and Evidence Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert stored SEC HTML documents into deterministic structured text whose sections and tables retain exact byte ranges into the immutable Stage 2 source object.

**Architecture:** A standard-library `HTMLParser` reads a Latin-1 view of each raw byte object so parser character positions equal source byte positions. Normalized Pydantic contracts are serialized deterministically into content-addressed JSON, while a separate additive SQLite manifest records parser version, source hash, quality, warnings, exhibit-parent links, success, and failure.

**Tech Stack:** Python 3.11+, standard-library `html.parser`, Pydantic v2, SQLite, JSON, pytest.

## Global Constraints

- Raw SEC objects under `data/raw/` are immutable and are never rewritten.
- `source_start` and `source_end` are half-open byte offsets into the exact Stage 2 `sec_documents.local_path` bytes.
- The same source hash and parser version must produce byte-identical normalized JSON.
- Tables remain separately typed sections with row and cell boundaries; they are not flattened into undifferentiated prose.
- Missing headings, malformed structure, empty text, unsupported binary content, and low text density are explicit warnings or failures.
- The 100-document acceptance sample is stratified across CIKs from the frozen Stage 2 cohort; it is not a point-in-time research universe.
- No model, network service, crawler framework, or new package is added.

---

### Task 1: Freeze normalized contracts and parser configuration

**Files:**
- Create: `configs/normalization.yaml`
- Create: `src/financial_event_model/normalization/models.py`
- Create: `src/financial_event_model/normalization/__init__.py`
- Test: `tests/test_sec_normalization.py`

**Interfaces:**
- Produces: `NormalizedSection`, `NormalizedDocument`, and `NormalizationRunResult`.
- `NormalizedSection.source_start: int` and `source_end: int` define a validated half-open byte range.
- `NormalizedDocument` carries source identity, parser version, exhibit relationship, language, quality, warnings, and ordered sections.

- [x] **Step 1: Write the failing contract test**

```python
def test_normalized_section_rejects_an_empty_source_range():
    with pytest.raises(ValueError):
        NormalizedSection(
            section_id="section_001",
            heading=None,
            text="evidence",
            source_start=10,
            source_end=10,
        )
```

- [x] **Step 2: Run the contract test and confirm it fails because the normalization package is absent**

Run: `python -m pytest tests/test_sec_normalization.py::test_normalized_section_rejects_an_empty_source_range -q`

- [x] **Step 3: Implement the contracts and versioned configuration**

Use Pydantic bounds for scores, a model validator for `source_end > source_start`, tuples for deterministic ordered collections, and `parser_version: sec-html-v0.1` in `configs/normalization.yaml`.

- [x] **Step 4: Run the focused test green**

Run: `python -m pytest tests/test_sec_normalization.py::test_normalized_section_rejects_an_empty_source_range -q`

### Task 2: Parse HTML, headings, paragraphs, tables, language, and byte offsets

**Files:**
- Create: `src/financial_event_model/normalization/sec_html.py`
- Create: `tests/fixtures/sec_normalization_cases.json`
- Modify: `tests/test_sec_normalization.py`

**Interfaces:**
- Consumes: exact raw bytes plus Stage 2 document metadata.
- Produces: `normalize_sec_html(...) -> NormalizedDocument`.

- [x] **Step 1: Add failing tests for traceable prose and typed tables**

```python
document = normalize_sec_html(
    b"<html><body><h1>Item 1.01 Agreement</h1><p>Alpha &amp; Beta signed.</p>"
    b"<table><tr><th>Year</th><th>Value</th></tr><tr><td>2024</td><td>10</td></tr></table>"
    b"</body></html>",
    source_document_id=7,
    accession_number="0000000001-24-000001",
    source_content_hash="a" * 64,
    document_type="8-K",
    filename="filing.htm",
    parser_version="sec-html-v0.1",
)
assert document.sections[0].heading == "Item 1.01 Agreement"
assert b"Alpha &amp; Beta signed." in raw[
    document.sections[0].source_start:document.sections[0].source_end
]
assert document.sections[1].is_table is True
assert document.sections[1].text == "Year\tValue\n2024\t10"
```

- [x] **Step 2: Run the parser tests red**

Run: `python -m pytest tests/test_sec_normalization.py -q`

- [x] **Step 3: Implement the minimum byte-position parser**

Decode with Latin-1 only for parsing, convert text fragments with `html.unescape`, normalize Unicode and whitespace, skip `head/script/style/header/footer/nav/ix:hidden`, group block text under detected headings, preserve tables as row/tab text, flag boilerplate, detect English versus unknown, and calculate a deterministic quality score from explicit warnings.

- [x] **Step 4: Add the manually inspected fixture matrix**

The JSON fixture cases cover ordinary filing HTML, malformed nesting, inline XBRL, tables, an amended filing, multiple exhibits, a long filing, and missing headings. Each case declares its expected warning, heading, table count, or deterministic property.

- [x] **Step 5: Run parser tests green twice and compare serialized bytes**

Run: `python -m pytest tests/test_sec_normalization.py -q`

### Task 3: Persist normalized artifacts separately and link exhibits

**Files:**
- Create: `src/financial_event_model/normalization/migrations/0001_normalized_documents.sql`
- Create: `src/financial_event_model/normalization/migrations/0001_normalized_documents.down.sql`
- Create: `src/financial_event_model/normalization/store.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_sec_normalization.py`

**Interfaces:**
- Produces: `NormalizationStore.save(document)` and `SecNormalizationPipeline.run(limit=100)`.
- Reads Stage 2 `sec_documents` without altering its database.
- Writes normalized JSON under `data/normalized/sec/` and records success/failure in a separate normalization manifest.

- [x] **Step 1: Add failing persistence, rollback, idempotence, and exhibit-link tests**

```python
first = pipeline.run(limit=2)
second = pipeline.run(limit=2)
assert first.completed == 2
assert second.reused == 2
assert exhibit.parent_document_id == primary.source_document_id
assert raw_path.read_bytes() == raw_before
```

- [x] **Step 2: Run the storage tests red**

Run: `python -m pytest tests/test_sec_normalization.py -q`

- [x] **Step 3: Add the reversible schema and minimum store**

Use an additive table keyed by `(source_document_id, parser_version)` with source/output hashes, paths, parent document ID, quality, language, warnings JSON, success, error, and created time. Enable foreign keys on every local manifest connection; do not cross-link SQLite databases with unenforceable foreign keys.

- [x] **Step 4: Implement CIK-stratified selection and pipeline failure recording**

Select only `.htm`, `.html`, and `.txt` Stage 2 blocks, group by the CIK prefix in accession number, and round-robin groups deterministically. Unsupported objects are not silently parsed. Catch each document failure, persist the error, and continue the bounded run.

- [x] **Step 5: Run the complete Stage 3 unit suite green**

Run: `python -m pytest tests/test_sec_normalization.py -q`

### Task 4: Run the 100-document acceptance and document the proof boundary

**Files:**
- Create: `docs/STAGE_3_NORMALIZATION.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-08-20-stage-3-normalization.md`

**Interfaces:**
- Consumes: local Stage 2 manifest and exact raw objects from the accepted 50-company cohort.
- Produces: ignored normalized JSON/SQLite artifacts and a committed evidence summary.

- [x] **Step 1: Run 100 real documents**

Run the pipeline with `parser_version=sec-html-v0.1`, `limit=100`, `data/raw/sec_manifest.sqlite3`, `data/normalized/sec/`, and `data/normalized/normalization_manifest.sqlite3`.

- [x] **Step 2: Audit offsets, table typing, warnings, determinism, and raw immutability**

Require 100 recorded successes, zero unrecorded failures, every section range within its source bytes, every table separately typed, byte-identical output hashes on rerun, zero new SEC requests, and unchanged source hashes before/after normalization.

- [x] **Step 3: Record observed quality honestly**

Document counts and warning categories from the real run. A deterministic parser pass proves traceability and failure visibility only; it does not claim that every economically relevant section was found reliably without manual review.

- [x] **Step 4: Run final verification and commit**

Run: `python -m pip install -e ".[dev]"`

Run: `python -m pytest`

Run: `python -m compileall -q src tests`

Run: `git diff --check`

Review: `git diff --cached`

Commit: `feat(normalization): add traceable SEC document parser`
