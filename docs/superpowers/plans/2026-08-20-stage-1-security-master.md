# Stage 1 Security Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven development and execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local point-in-time identity system that resolves a filing-date CIK to its legal entity, valid securities, historical tickers, tradability, and named-universe membership.

**Architecture:** Use one additive, versioned SQLite migration and one `SecurityMaster` repository in the existing `identifiers` package. Store ISO dates with half-open intervals (`start <= date < end`), keep identifier history separate from stable entity/security records, and return every valid security instead of guessing which share class the caller meant.

**Tech Stack:** Python 3.11+, standard-library `sqlite3`, Pydantic 2, pytest.

## Global Constraints

- Never infer historical universe membership from current constituents.
- Treat `valid_to`, `membership_end`, and identifier-history `valid_to` as exclusive.
- Preserve ticker and identifier changes instead of overwriting history.
- Keep the implementation local and additive; do not add SQLAlchemy, Alembic, DuckDB, or a market-data dependency.
- This stage proves schema and query semantics with fixtures, not historical-data completeness.

---

### Task 1: Versioned schema migration

**Files:**
- Create: `src/financial_event_model/identifiers/migrations/0001_security_master.sql`
- Create: `src/financial_event_model/identifiers/migrations/0001_security_master.down.sql`
- Create: `src/financial_event_model/identifiers/security_master.py`
- Test: `tests/test_security_master.py`

**Interfaces:**
- Produces: `SecurityMaster(database_path)` which creates `schema_migrations`, applies migration 1 once, and enables SQLite foreign keys on every connection.

- [x] **Step 1: Write and run the failing migration test**

```python
def test_security_master_applies_versioned_schema_once(tmp_path):
    SecurityMaster(tmp_path / "security_master.sqlite3")
    SecurityMaster(tmp_path / "security_master.sqlite3")
    with sqlite3.connect(tmp_path / "security_master.sqlite3") as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
        assert {"entities", "securities", "identifier_history", "universe_membership"} <= tables
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
```

Run: `python -m pytest tests/test_security_master.py::test_security_master_applies_versioned_schema_once -q`

Expected: FAIL because `financial_event_model.identifiers.security_master` does not exist.

- [x] **Step 2: Add the forward schema**

```sql
CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    legal_name TEXT NOT NULL,
    cik TEXT NOT NULL,
    incorporation_country TEXT,
    sector TEXT,
    industry TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE TABLE securities (
    security_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    ticker TEXT NOT NULL,
    exchange TEXT NOT NULL,
    security_type TEXT NOT NULL,
    currency TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    delisted_at TEXT,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE TABLE identifier_history (
    identifier_history_id INTEGER PRIMARY KEY,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    security_id TEXT REFERENCES securities(security_id),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    source TEXT NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE TABLE universe_membership (
    security_id TEXT NOT NULL REFERENCES securities(security_id),
    universe_name TEXT NOT NULL,
    membership_start TEXT NOT NULL,
    membership_end TEXT,
    reason_added TEXT NOT NULL,
    reason_removed TEXT,
    PRIMARY KEY (security_id, universe_name, membership_start),
    CHECK (membership_end IS NULL OR membership_end > membership_start)
);
```

The concrete migration must contain every field from the supplied Stage 1 specification, primary/unique keys, half-open interval checks, and lookup indexes. The down migration drops only these new tables and indexes in reverse dependency order.

- [x] **Step 3: Implement and verify the migration runner**

```python
class SecurityMaster:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()
```

Run: `python -m pytest tests/test_security_master.py::test_security_master_applies_versioned_schema_once -q`

Expected: PASS.

### Task 2: Point-in-time records and resolution

**Files:**
- Modify: `src/financial_event_model/identifiers/security_master.py`
- Create: `src/financial_event_model/identifiers/__init__.py`
- Test: `tests/test_security_master.py`

**Interfaces:**
- Consumes: `EntityRecord`, `SecurityRecord`, `IdentifierRecord`, and `UniverseMembershipRecord`.
- Produces: `add_entity`, `add_security`, `add_identifier`, `add_universe_membership`, and `resolve_filing(cik, filing_date, universe_name) -> FilingResolution | None`.

- [x] **Step 1: Write point-in-time query tests**

```python
resolution = master.resolve_filing("320193", date(2020, 1, 2), "us_liquid_equities")
assert resolution.cik == "0000320193"
assert resolution.securities[0].ticker == "AAPL"
assert resolution.securities[0].tradable is True
assert resolution.securities[0].in_universe is True
```

Tests must also prove that a ticker change becomes visible exactly at its `valid_from`, membership ends exactly at `membership_end`, a delisted security is returned but marked non-tradable, and an entity outside its validity interval does not resolve.

- [x] **Step 2: Run the focused tests red**

Run: `python -m pytest tests/test_security_master.py -q`

Expected: FAIL because the records and resolution methods do not exist.

- [x] **Step 3: Implement the minimal records and query**

```python
def resolve_filing(
    self,
    cik: str,
    filing_date: date,
    universe_name: str,
) -> FilingResolution | None:
    normalized_cik = cik.zfill(10)
    as_of = filing_date.isoformat()
    entity = self._resolve_entity(normalized_cik, as_of)
    if entity is None:
        return None
    securities = self._resolve_securities(entity["entity_id"], as_of, universe_name)
    return FilingResolution(
        entity_id=entity["entity_id"],
        legal_name=entity["legal_name"],
        cik=normalized_cik,
        securities=securities,
    )
```

Use parameterized SQL. Resolve ticker from `identifier_history` first and use the security table ticker only as the fallback. Return all valid securities ordered by `security_id`.

- [x] **Step 4: Run the focused tests green**

Run: `python -m pytest tests/test_security_master.py -q`

Expected: PASS.

### Task 3: Documentation and full verification

**Files:**
- Create: `docs/STAGE_1_SECURITY_MASTER.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`

- [x] Document interval semantics, supported query, data-source boundary, and the explicit fact that fixture success is not a populated historical universe.
- [x] Run `python -m pip install -e ".[dev]"`.
- [x] Run `python -m pytest` and `python -m compileall -q src tests`.
- [x] Run `git diff --check`, inspect the staged diff, and create a Conventional Commit only after all checks pass.
