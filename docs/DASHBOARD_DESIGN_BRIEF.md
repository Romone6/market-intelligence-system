# Portfolio Intelligence Dashboard Design Contract

## Product role

The dashboard is the operator interface for the financial event model. It must make portfolio state, provenance, risk, activity, catalysts, and system health visible without implying that unsupported live trading capability exists.

The first implementation uses fixtures and research outputs. An eventual IBKR connection is read-only first. Order entry and autonomous execution remain disabled until the explicit live-trading gate in the project roadmap is passed.

## Visual direction

- Dark-only foundation: near-black graphite surfaces, a restrained charcoal-to-black radial gradient, thin low-contrast borders, and off-white type.
- Positive data uses green; negative data uses red. Neutral and benchmark series use cool grey or muted violet. Colour is always reinforced by a sign, label, or pattern.
- Dense information is grouped into quiet, double-bezel cards with generous internal spacing. Motion is limited to state changes and chart inspection, and respects reduced-motion preferences.
- Typography should feel like an institutional research terminal, not a generic admin template. Tabular figures use aligned numerals.
- Every panel shows its data state: `fixture`, `paper`, `read-only broker`, or `live`. Stale and unavailable data are visually distinct from zero.

The supplied screenshots are visual references only. They do not authorize copying code or commercial template assets.

## Information architecture

### Overview

1. Portfolio value, daily P&L, total return, cash, gross exposure, and net exposure summary.
2. Full-width portfolio growth area/line chart with portfolio, invested capital, and optional benchmark series.
3. Holdings distribution donut by position, sector, or event thesis.
4. Risk radar with normalized dimensions and adjacent raw values.
5. Daily-return calendar heatmap.
6. Recent stock activity.
7. Upcoming event strip.

### Holdings

Positions, cost basis, current value, unrealized/realized P&L, weight, exposure, thesis, catalysts, risk flags, source timestamp, and broker reconciliation state. Position details link to their event and analysis history.

### Activity

Stock transactions and model actions in reverse chronology. Each row records side, symbol, quantity, price, fees, venue, account mode, source, event time, ingestion time, and immutable activity ID.

### Calendar

Earnings, SEC filings, corporate actions, economic releases, thesis-review dates, and model maintenance events. Event type is encoded by both colour and label.

### News

A separate text-first feed inspired by professional equity-research products. Items show source, publication and tradable timestamps, affected holdings, event family, novelty, and read/unread state. Publisher content is linked and summarized within its licence; full articles are not republished.

### Analysis

Daily, weekly, and monthly briefs. Each brief separates:

- observed facts and linked evidence;
- current thesis;
- catalysts and expected timing;
- risks and disconfirming evidence;
- where the measurable edge may remain;
- position implications;
- model inference and uncertainty.

Briefs are append-only research artifacts with `as_of`, data cutoff, model/checkpoint identity, and revision history. Generated analysis is never presented as a fact or an order instruction.

### Connections

Connection-health cards for market data, SEC, news, model artifacts, and the future broker adapter. The UI shows provider, mode, scopes, last success, latency, quota, and masked key suffix only. Secret values are never returned to the browser or made recoverable from the dashboard.

## Component mapping

| Need | Reference | Implementation contract |
|---|---|---|
| Holdings distribution | EvilCharts Market Share donut | Value-weighted slices; centre shows total portfolio value; legend shows symbol, value, and weight; toggle position/sector/thesis. |
| Risk overview | EvilCharts radar | Axes: volatility control, drawdown control, Sharpe quality, alpha quality, beta control, concentration control. Plot normalized 0–100 scores only; show raw metric, lookback, benchmark, and normalization formula beside the chart. Higher always means better/safer. |
| Portfolio growth | EvilCharts Audience Growth / Portfolio area style | Portfolio value, invested capital, and benchmark over selectable ranges; no smoothing that changes point values; tooltip shows timestamp and exact source values. |
| Daily return map | RareUI GitHub Activity adapted for portfolio returns | Trading-day cells diverge red/green. Intensity is based on frozen absolute-return bands. Hover/focus shows date, signed return percentage, P&L, and data state. Non-trading and missing days are different states. |
| Recent activity | Stock adaptation of the supplied crypto-dashboard layout | Buy/sell/dividend/fee/corporate-action/model-decision badges; never conflate a model recommendation with an executed trade. |
| Invested versus value | Supplied performance-chart layout | Side-by-side time series with exact tooltip values and cash-flow-aware return context. |
| Events | Supplied calendar layout | Month/week/list modes, filters, timezone, event source, and linked holdings. |
| Connections | Supplied API-key-management layout | Status dashboard, not a secret vault. Key creation/input is deferred until an OS-backed encrypted store and explicit threat model exist. |

EvilCharts publishes shadcn-compatible chart components and its repository is MIT licensed. The intended starting imports, to be executed only after a React dashboard workspace exists, are:

```powershell
npx shadcn@latest add @evilcharts/market-share-echarts-pie-chart
npx shadcn@latest add @evilcharts/audience-echarts-area-chart
```

The current EvilCharts radar documentation exposes the Recharts registry component as:

```powershell
npx shadcn@latest add @evilcharts/recharts-radar-chart
```

The screenshot's older `@evilcharts/echarts-radar-chart` name must not be assumed current without a registry check at implementation time.

RareUI's repository describes its components as free and open source, but a licence file was not exposed in the repository metadata checked on 2026-08-20. The project owner explicitly directed use of the component regardless on 2026-08-20. Its source URL, retrieved revision, and attribution must be recorded when the dashboard workspace imports it. ShadcnKit screenshots are used as composition references only.

## Data contracts

Every dashboard payload includes:

- `as_of` and provider/source timestamp;
- ingestion timestamp;
- account mode;
- currency and FX basis where relevant;
- provenance identifier;
- stale/error state;
- reconciliation status for broker-derived data.

Performance calculations must distinguish deposits/withdrawals from investment returns. Alpha, beta, Sharpe, volatility, and drawdown must disclose their lookback, sampling frequency, risk-free-rate source, and benchmark.

## IBKR sequence

1. Create and fund an eligible IBKR Pro account and its simulated paper account.
2. Connect the dashboard to the paper account in read-only mode.
3. Reconcile positions, cash, transactions, P&L, and timestamps against the broker UI.
4. Run sustained paper observation with session-loss and stale-data handling.
5. Add order-preview capability only behind a separate explicit gate.
6. Add live order submission only after the project charter's execution, legal, risk, and capital gates pass.

IBKR documents a read-only session subset for portfolio retrieval. Individual Web API use requires a fully open and funded IBKR Pro live account even when accessing the associated paper account, and broker/market-data functions have session and pacing constraints. Those constraints are part of the adapter contract, not dashboard implementation details to hide.

## Non-goals for the first dashboard increment

- No live broker orders.
- No browser-stored broker or provider secrets.
- No fabricated portfolio history.
- No unlabelled mixture of fact, inference, and recommendation.
- No copied commercial dashboard source.
- No claim that visual completion is trading-system completion.
