# Stage 5: Market Data and Outcome Labels

## Implemented boundary

Stage 5 now has a provider-gated daily-market pipeline and deterministic label engine. It does not have a completed live 100-filing acceptance because no authenticated consolidated-market source is currently configured.

The implementation adds:

- immutable, content-addressed provider responses and an append-only request manifest;
- versioned daily raw and adjusted OHLCV observations;
- an exact adjustment factor and separate provider/source timestamps;
- point-in-time corporate-action records filtered by first observation time;
- official daily Fama/French market, SMB, HML, and risk-free observations;
- 1/5/20-session raw and market-adjusted returns;
- 5-session sector-adjusted return;
- 20-session factor residual, realized volatility, adverse/favourable excursion, and 5-session volume abnormality;
- tri-state contamination flags that preserve unknown external data.

Market data and labels remain in `data/market/` and the committed schema; generated databases and raw provider objects remain ignored.

## Daily-bar contract

Each `MarketBar` stores the required security ID, timestamp, open, high, low, close, volume, adjustment factor, trading status, source, and receipt time. It additionally stores session date, symbol, the provider timestamp, adjusted OHLC, and source-content hash.

Alpaca bars are requested twice: once with `adjustment=raw` and once with `adjustment=all`. Rows are paired by symbol and provider timestamp. Raw OHLCV is retained, adjusted OHLC is used for total-return labels, and `adjusted_close / raw_close` is stored as the explicit adjustment factor. The official specification distinguishes raw, split, dividend, spin-off, and all adjustments and identifies SIP as all US exchanges ([Alpaca OpenAPI](https://github.com/alpacahq/cli/blob/main/api/specs/market-data-api.json)).

The committed default is SIP. Alpaca states that IEX is a single exchange, so an IEX-only run may test integration but cannot pass the consolidated-market acceptance gate ([Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)).

## Outcome timing

The label start is the first stored regular-session open whose timestamp is greater than or equal to Stage 4 `tradable_at`.

This distinction matters after an out-of-hours filing. If latency makes the filing tradable at 09:45, that day's 09:30 open is already in the past and cannot be used. With daily bars, the engine advances to the following eligible session open.

For horizon `h`:

```text
raw_return_h = adjusted_close_of_session_h / adjusted_open_of_start_session - 1
market_adjusted_return_h = raw_return_h - benchmark_return_h
```

The 20-session realized volatility is the sample standard deviation of daily returns annualized by `sqrt(252)`. Maximum adverse and favourable excursion use adjusted daily lows and highs relative to the start open. Volume abnormality compares mean volume over the first five outcome sessions with the preceding 20 observations.

## Factor residual

The factor model fits an intercept plus market, SMB, and HML coefficients with `numpy.linalg.lstsq`. It uses at most the latest 252 matched observations strictly before the event start and requires 120 by default. The official Fama/French definition provides daily `Rm-Rf`, SMB, HML, and the one-month Treasury-bill rate ([factor definitions](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/f-f_factors.html)).

The current downloaded factor file is an ex-post research vintage. It is suitable for outcome normalization, but it is not represented as information known to the model in 2024 and may not enter historical features without a vintage archive.

## Corporate actions and contamination

Corporate-action payloads are stored with exact source JSON, effective date, receipt time, and content hash. Querying with `as_of` excludes actions not yet observed. Alpaca warns that it does not guarantee corporate-action creation time and that provider/processing delays occur ([corporate-actions reference](https://docs.alpaca.markets/us/reference/corporateactions-1)).

Known values are computed for missing prices, multiple same-day filings, liquidity, extreme benchmark movement, and explicit trading status. Earnings, macro announcement, acquisition, historical halt, and delisting-return fields remain `null` when no authoritative source is present. An unknown trading status is not converted into either a clean session or a halt.

## Verification evidence

Fixture-backed checks currently demonstrate:

- exact raw and adjusted bar pairing across paginated responses;
- credential headers without secret persistence;
- reversible migrations and idempotent versioned bar storage;
- exact as-of corporate-action filtering;
- correct percentage-to-decimal factor parsing;
- a strict 252-row pre-event factor window;
- exact 1/5/20-session source-price reproduction for 100 deterministic fixture events;
- correct open selection at and after `tradable_at`;
- fail-closed missing-horizon behavior;
- daily-low/high excursion calculations and abnormal-volume calculations.

The official Fama/French archive was downloaded successfully on 2026-08-20: 26,274 daily rows parsed, including 355 rows from 2023-01-03 through 2024-05-31.

## Open live gate

Neither `APCA_API_KEY_ID` nor `APCA_API_SECRET_KEY` is configured. Consequently:

- zero live Alpaca stock, ETF, or corporate-action requests were attempted;
- zero live filing labels were generated;
- the required manual reproduction of 100 real filing outcomes has not passed;
- sector benchmarks remain an injected input until the point-in-time security master has authoritative sector history;
- historical halt data and delisting returns still require authoritative coverage.

The implementation is ready for the live run once authenticated SIP access or a licensed equivalent daily-bar export is supplied. No undocumented Yahoo endpoint, scraped source, or premium endpoint without entitlement was substituted to manufacture acceptance evidence.
