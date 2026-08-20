# Stage 4: Timestamp Discipline and Historical Knowledge

## Implemented boundary

Stage 4 adds a conservative, policy-versioned availability layer before labels or backtests exist. Every temporal knowledge record stores the six distinct timestamps required by the specification:

- `event_effective_at`: the underlying economic effective instant, nullable when it has not yet been extracted;
- `source_published_at`: the SEC acceptance timestamp from submissions metadata;
- `first_observed_at`: when this collector first observed the filing metadata;
- `downloaded_at`: when the exact complete-submission response was received;
- `processed_at`: when the normalized artifact was persisted;
- `tradable_at`: the first daily outcome boundary allowed by `sec-daily-v0.1`.

Historical backfill deliberately preserves the fact that local observation, download, and processing happened after publication. It does not replace those timestamps with the filing date.

## SEC provenance correction

Stage 2 parsed SEC acceptance timestamps but its first manifest schema did not persist the filing-level metadata. The additive and reversible `0002_sec_filings` migration now stores accession, CIK, filing date, acceptance instant, form, amendment flag, source metadata request, and first observation time.

The accepted Q1 2024 cohort was backfilled only from already cached official SEC submissions JSON. The backfill produced 161 filing records, including 7 amendments, with zero missing acceptance timestamps and zero network requests.

## Conservative daily policy

The committed policy uses the XNYS regular-session calendar and a 15-minute assumed processing latency:

- a release during a regular session becomes eligible at the next regular-session open; the processing delay is fully absorbed before that later daily boundary;
- a release before open, after close, or on a non-session day becomes eligible at the next regular-session open plus 15 minutes;
- an early close is treated as the actual close, not 16:00 Eastern;
- a trading halt can only delay eligibility, to the next daily boundary after trading resumes.

This is intentionally more conservative than pretending daily close data was available at the filing instant. Stage 5 must begin outcome measurement at `tradable_at` and may not replace this policy silently.

## Exact historical query

```python
from financial_event_model.temporal import KnowledgeStore

store = KnowledgeStore("data/events/knowledge.sqlite3")
known = store.get_known_information(
    entity_id="sec-cik:0000320193",
    decision_time="2024-01-03T14:30:00Z",
)
```

The query includes only records where `tradable_at <= decision_time`. The equality is deliberate: a test at one microsecond before the boundary excludes the record, while the exact boundary includes it. `latest_per_key=True` produces an as-of view for versioned classifications or facts without allowing a future version to rewrite history.

The frozen acceptance cohort uses deterministic `sec-cik:##########` entity keys because authoritative Stage 1 historical security-master population remains open. `SecKnowledgeMaterializer` accepts an injected resolver so those technical keys can be replaced with canonical entity IDs without changing timestamp logic.

## Automated leakage controls

Tests verify that:

- an amendment is absent before its own conservative boundary;
- a future XBRL revision cannot enter an earlier query;
- a future sector version cannot replace the historical value;
- a later price-adjustment revision cannot reveal a future corporate action;
- equal content hashes cannot cross a train/test boundary;
- half-open outcome windows cannot overlap across folds;
- naive timestamps and impossible observation/download/processing order fail closed.

The duplicate-hash and outcome-window guards are reusable checks for Stage 5 and later split builders. They are not claims that market data or outcome folds already exist.

## 100-record acceptance evidence

The 2026-08-20 cache-only acceptance materialized the 100 successful Stage 3 documents across 44 CIK identities:

- 100 selected, 100 materialized, and zero skipped;
- 2 amended-filing documents retained separately;
- zero missing required timestamp values other than the explicitly nullable `event_effective_at`;
- zero timestamp-order violations;
- zero records visible one microsecond before `tradable_at`;
- all 100 records visible at the exact `tradable_at` boundary;
- zero duplicate normalized-content hashes;
- 100 records again on an idempotent rerun;
- zero new SEC requests during provenance backfill or materialization.

## Proof boundary

This proves filing-level publication provenance, conservative XNYS daily availability, exact as-of retrieval, and reusable leakage guards for the frozen technical cohort. The audit contains normalized filing evidence, not extracted semantic events or market features. Therefore the required timestamp machinery is implemented, while feature-by-feature replay validation remains a continuous gate as Stage 5 market inputs and Stage 6 event objects are introduced.
