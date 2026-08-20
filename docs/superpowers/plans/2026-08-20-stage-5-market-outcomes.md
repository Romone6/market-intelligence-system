# Stage 5 Market Data and Outcome Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create point-in-time daily market observations and reproducible 1/5/20-session outcome labels that begin no earlier than the Stage 4 tradability boundary.

**Architecture:** Preserve exact provider responses, store raw and adjusted daily bars separately from labels, and derive each label from one explicit start bar plus ordered future sessions. Use an authenticated Alpaca adapter for stock and ETF bars, the official Fama/French daily three-factor file for factor observations, and a deterministic NumPy least-squares fit using only pre-event rows.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite, NumPy 2.x, `urllib.request`, pytest.

## Global Constraints

- Daily bars only; no minute-data approximation.
- Raw provider objects are immutable and content-addressed.
- Bar rows retain raw OHLCV, adjusted OHLCV, adjustment factor, trading status, source, and receipt time.
- Outcome start is the first regular-session open at or after `tradable_at`; a 09:45 tradability instant cannot reuse that day's 09:30 open.
- Factor coefficients use only observations strictly before the event start session.
- Missing halts, delisting returns, macro calendars, or point-in-time sector mappings remain explicit unknowns rather than false negatives.
- Alpaca credentials are required for a live acceptance run and are never committed.
- The current IEX free feed is not treated as consolidated-market proof: Alpaca documents that “IEX ... is a single stock exchange” ([Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)).

---

### Task 1: Freeze market and label contracts

**Files:**
- Create: `configs/market.yaml`
- Create: `src/financial_event_model/market/models.py`
- Create: `tests/test_market_outcomes.py`

**Interfaces:**
- Produces: `MarketBar`, `FactorObservation`, `FilingOutcomeInput`, `OutcomeLabel`, and `ContaminationFlags`.

- [x] **Step 1: Write failing validation tests**

```python
with pytest.raises(ValidationError):
    MarketBar(high=9.0, open=10.0, low=8.0, close=9.5, **required)
```

The store uses SQLite because it is a “lightweight disk-based database” ([Python sqlite3](https://docs.python.org/3/library/sqlite3.html)).

- [x] **Step 2: Run the focused test and confirm the package is absent**

```powershell
python -m pytest tests/test_market_outcomes.py -q
```

- [x] **Step 3: Implement only the validated contracts and configuration**

```python
class MarketBar(Contract):
    security_id: str
    timestamp: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: int
```

Alpaca defines bar adjustment modes where `raw` means “no adjustments” and `all` applies every supported adjustment ([official OpenAPI specification](https://github.com/alpacahq/cli/blob/main/api/specs/market-data-api.json)).

### Task 2: Persist and collect daily bars

**Files:**
- Create: `src/financial_event_model/market/migrations/0001_market_data.sql`
- Create: `src/financial_event_model/market/migrations/0001_market_data.down.sql`
- Create: `src/financial_event_model/market/store.py`
- Create: `src/financial_event_model/market/alpaca.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_market_outcomes.py`

**Interfaces:**
- Produces: `MarketStore.put_bars(...)`, `MarketStore.bars(...)`, and `AlpacaDailyBarCollector.collect(...)`.

- [x] **Step 1: Add red migration, idempotence, authentication, pagination, and raw/adjusted pairing tests**

```python
collector = AlpacaDailyBarCollector(api_key="key", api_secret="secret", open_url=fake)
bars = collector.collect(symbols={"AAPL": "security_apple"}, start=start, end=end)
assert bars[0].adjustment_factor == pytest.approx(adjusted_close / raw_close)
```

The HTTP layer uses `urllib.request.urlopen`, which “returns an object which can work as a context manager” ([Python urllib](https://docs.python.org/3.13/library/urllib.request.html)).

- [x] **Step 2: Implement the reversible schema and minimal collector**

```python
request = Request(url, headers={
    "APCA-API-KEY-ID": api_key,
    "APCA-API-SECRET-KEY": api_secret,
})
```

The provider requires authentication and returns `401` when “authentication headers are missing or invalid” ([Alpaca corporate-actions reference](https://docs.alpaca.markets/us/reference/corporateactions-1)).

- [x] **Step 3: Keep current and future corporate-action knowledge separate**

Persist response receipt time and requested adjustment mode. Do not treat the latest adjusted series as historical feature knowledge; Alpaca warns corporate actions “may not be available immediately after they are announced” ([Alpaca corporate-actions reference](https://docs.alpaca.markets/us/reference/corporateactions-1)).

### Task 3: Import factors and generate labels

**Files:**
- Create: `src/financial_event_model/market/factors.py`
- Create: `src/financial_event_model/market/outcomes.py`
- Modify: `tests/test_market_outcomes.py`

**Interfaces:**
- Produces: `parse_french_daily_factors(...)`, `estimate_factor_model(...)`, and `generate_outcome_label(...)`.

- [x] **Step 1: Add red tests for percent conversion, pre-event fitting, start-session selection, exact returns, excursions, volatility, volume abnormality, and missing-data flags**

```python
label = generate_outcome_label(event, stock, benchmark, sector, factors)
assert label.raw_return_5d == pytest.approx(stock[4].adjusted_close / stock[0].adjusted_open - 1)
```

The official library publishes “Fama/French 3 Factors [Daily]” ([Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)).

- [x] **Step 2: Implement a pre-event least-squares factor fit**

```python
coefficients, _, rank, _ = np.linalg.lstsq(design, excess_returns, rcond=None)
```

NumPy specifies that `lstsq` “minimizes the Euclidean 2-norm” ([NumPy `linalg.lstsq`](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html)). Fama/French defines `Rm-Rf` as market return “minus the one-month Treasury bill rate” ([factor definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/f-f_factors.html)).

- [x] **Step 3: Persist labels and contamination flags**

Unknown external calendars and unavailable delisting returns remain `null`. Missing bars, low liquidity, multiple same-day filings, extreme benchmark moves, and known trading-status problems are deterministic.

### Task 4: Acceptance and proof boundary

**Files:**
- Create: `docs/STAGE_5_MARKET_OUTCOMES.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: this plan

**Interfaces:**
- Produces: fixture-backed reproducibility evidence and, only when credentials permit, the live 100-filing acceptance report.

- [x] **Step 1: Run fixture reproduction and the complete repository suite**

```powershell
python -m pytest
python -m compileall -q src tests
git diff --check
```

The provider distinguishes consolidated SIP from IEX; “all US exchanges” is the SIP feed ([Alpaca OpenAPI specification](https://github.com/alpacahq/cli/blob/main/api/specs/market-data-api.json)).

- [x] **Step 2: Attempt the live credential gate without substituting an unlicensed source**

If `APCA_API_KEY_ID` or `APCA_API_SECRET_KEY` is absent, record the exact blocker. Alpha Vantage is not a silent fallback because its adjusted daily endpoint is marked “Trending Premium” ([Alpha Vantage documentation](https://www.alphavantage.co/documentation/)).

- [x] **Step 3: Document demonstrated and undemonstrated claims, then commit**

Do not claim the 100-event return audit unless 100 real filing labels were independently reconstructed from licensed source bars.
