# Stage 4 Timestamp Discipline Implementation Plan

**Goal:** Make historical replay reject information that was not conservatively tradable at an exact decision time.

**Architecture:** Persist SEC filing acceptance provenance additively in the immutable-source manifest. A separate temporal SQLite store records the six required timestamps for normalized evidence and exposes one exact point-in-time query. An XNYS calendar adapter owns sessions and holidays; the initial daily policy deliberately delays availability to the next eligible regular-session open.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite, `exchange-calendars`, pytest.

## Constraints

- Raw and normalized artifacts remain unchanged.
- `source_published_at` comes from SEC acceptance metadata; it is never inferred from download time.
- `first_observed_at`, `downloaded_at`, and `processed_at` remain distinct even during historical backfill.
- Daily `tradable_at` is conservative and policy-versioned.
- Query predicates use `tradable_at <= decision_time` and timezone-aware instants.
- Missing entity identity, publication time, normalization success, or source linkage fails closed.

## Tasks

- [x] Add red tests for filing-provenance persistence, calendar boundaries, six-timestamp validation, exact historical queries, amendments, revisions, duplicate split hashes, and fold-window overlap.
- [x] Add reversible SEC manifest migration `0002` and cache-only filing metadata backfill.
- [x] Add versioned timestamp configuration, temporal contracts, XNYS daily policy, reversible temporal schema, and `get_known_information`.
- [x] Materialize a real 100-record audit from accepted Stage 2/3 data, inspect every timestamp invariant, and rerun without network access.
- [x] Document proof boundaries, run the complete verification suite, and commit Stage 4.
