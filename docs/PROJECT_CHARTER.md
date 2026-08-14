# Financial Event Model Project Charter

## Authority

This file is the canonical engineering reference for this repository. Every design, experiment, model, automation, and execution decision must be consistent with it. If a later request conflicts with this charter, record the deliberate amendment here before changing system behavior.

## Mission

Build an independent financial-event intelligence and decision system from open-source model components and reproducible training pipelines. The permanent product is not a prompt wrapper, a generic generative model, or an LLM asked to invent trades. It must learn from point-in-time corporate disclosures and market outcomes, produce calibrated distributions with evidence and provenance, abstain when evidence is weak, and eventually support an autonomous research-to-execution loop.

“Independent” means the system owns its data contracts, labels, training, evaluation, calibration, replay, and decision logic. Open-source pretrained encoders may be used as starting weights; their value must be demonstrated against simple frozen baselines. Deterministic protocol and risk code remains authoritative over learned components.

## Initial MVP

- US equities only; approximately 500–1,000 liquid securities.
- Daily market data, with historical coverage from 2015 where defensible.
- SEC filings as the primary event source: 8-K first, then 10-Q earnings material.
- Event families: earnings, guidance, contracts, capital allocation, and management changes; corporate actions are included in ontology v0.1.
- Outputs: event type and attributes, evidence, novelty, materiality, historical analogues, 1/5/20-day abnormal-return distributions, probability of positive/cost-exceeding outcomes, uncertainty, and abstention.
- Research and paper operation only during the MVP. No broker integration in the initial stages.

## Non-negotiable research rules

1. Preserve raw source objects exactly and attach request, publication, observation, processing, and content-hash provenance.
2. Never use a current company universe to represent historical membership without explicitly marking survivorship bias.
3. A feature may enter historical replay only if it was known before the event's conservative `tradable_at` timestamp.
4. Keep raw documents, normalized documents, events, labels, market data, models, calibration artifacts, and reports separate.
5. Split evaluation by time and audit company/related-event leakage. Do not tune repeatedly on the final holdout.
6. Compare every learned model with frozen non-neural and generic-embedding baselines.
7. Predict distributions and calibrated probabilities, not fabricated certainty or unexplained buy/sell commands.
8. Preserve semantic extraction and retrieval quality when adding outcome-alignment training.
9. Abstention is a first-class output. Missing data, weak analogues, OOD inputs, wide intervals, and insufficient edge must fail closed.
10. Every experiment records the complete configuration and every model output includes a non-empty model version.

## Autonomous loops and live-capital gate

The research loop may autonomously ingest, validate, train, evaluate, calibrate, and produce paper decisions once its stage-specific checks exist. Automation may not weaken data provenance, leakage controls, frozen holdouts, or acceptance thresholds.

The execution loop is a separate system and starts disabled. Elevated filesystem permissions do not constitute authority to place orders. Live trading requires all of the following to be recorded and verified:

- explicit live-trading authorization and supplied capital;
- approved broker/account configuration and secret handling;
- position, exposure, liquidity, loss, and transaction-cost limits;
- pre-trade validation, idempotent order handling, reconciliation, and audit logs;
- a tested kill switch and fail-closed behavior;
- paper/forward-test evidence that satisfies frozen promotion criteria;
- a named model, data, calibration, and policy version for every decision.

Until that gate is completed, `broker_enabled`, `live_trading_enabled`, and all order routes remain false or absent.

## Engineering rules

- Python 3.11+; one-command editable installation and one-command tests.
- Configuration lives under `configs/`, never as untracked notebook state.
- Reusable logic lives under `src/financial_event_model/`; notebooks are disposable analysis clients only.
- Prefer the standard library and existing dependencies. Add PyTorch, Transformers, DuckDB, Polars/Parquet, and FAISS only when their implementing stage begins.
- Generated datasets, checkpoints, calibration artifacts, and reports are not committed by default; manifests and schemas are.
- Facts, assumptions, inferences, and unproven product claims remain distinguishable in code and reports.

## Completion standard

A stage is complete only when its stated assertions and artifacts pass. A partial run, mocked provider, starter dataset, or local unit test is evidence for that boundary only—not proof of end-to-end model quality, profitability, or live readiness.

