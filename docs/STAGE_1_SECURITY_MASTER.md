# Stage 1: Point-in-Time Security Master

## Implemented boundary

The repository now owns a versioned SQLite schema and query path for:

- legal entities and SEC CIKs;
- tradable securities and listing metadata;
- historical identifiers, including ticker changes;
- named-universe membership intervals;
- filing-date resolution of entity, security, ticker, tradability, and membership.

All stored validity periods are half-open: the start date is included and the end date is excluded. An identifier with `valid_to: 2020-01-01` is unavailable on 2020-01-01; its successor may begin on that same date without overlap.

## Local use

```python
from datetime import date

from financial_event_model.identifiers import SecurityMaster

master = SecurityMaster("data/security_master/security_master.sqlite3")
resolution = master.resolve_filing(
    cik="320193",
    filing_date=date(2020, 1, 2),
    universe_name="us_liquid_equities",
)
```

`resolution.securities` contains every security valid for the entity on that date. The API does not guess a preferred share class. Historical ticker identifiers override the stable security record's fallback ticker.

## Integrity behavior

- CIK input is normalized to ten digits.
- End dates must be strictly later than start dates.
- Overlapping mappings for the same identifier are rejected.
- Overlapping membership periods for the same security and universe are rejected.
- Ambiguous point-in-time CIK resolution raises `SecurityMasterIntegrityError` instead of selecting a row.
- SQLite foreign keys are enabled on every connection.

## Evidence and open gate

The automated fixtures prove migration idempotence and the query's date-boundary behavior. They do **not** prove that the database contains a historically complete 500–1,000-security US universe.

Stage 1's real-data gate remains open until authoritative source importers populate the master and a coverage report samples filing dates across ticker changes, delistings, multiple share classes, mergers, and universe entries/exits. If only current constituents are available, the generated dataset must retain `prototype_survivorship_biased: true`.

The SEC ingestion stage may use this query engine immediately, but research results cannot claim survivorship-safe historical coverage before that population gate closes.
