# Autonomous Market Intelligence & Decision System

> **Status: research-stage.** The system is under active development and currently operates only as a research/paper system. It is not a production trading system and has no live-order capability.

An independently trained, point-in-time financial intelligence system designed to learn how corporate events translate into market outcomes.

The long-term objective is a complete research-to-decision architecture: ingest new information, represent events, retrieve economically comparable historical analogues, estimate calibrated outcome distributions, quantify uncertainty, abstain when evidence is weak, and eventually support a separately gated execution layer.

This is not a prompt wrapper that asks an LLM what to buy or sell. The system owns its data contracts, labels, evaluation, calibration, replay logic, and decision boundaries.

> Repository/package names still use `financial_event_model` internally while the project is being renamed. The codebase-wide rename will happen separately to avoid breaking imports, tests, and documentation links.

## System architecture

The project is being built as an end-to-end research stack:

1. **Point-in-time security universe**  
   Reconstruct which securities and identifiers were valid at each historical point rather than applying today's universe retrospectively.

2. **Corporate disclosure ingestion**  
   Collect filings and source material while preserving publication, observation, processing, and content-hash provenance.

3. **Deterministic normalization and evidence mapping**  
   Convert heterogeneous disclosures into structured representations while retaining byte-level links back to source evidence.

4. **Historical knowledge discipline**  
   Enforce conservative tradability timestamps so historical replay cannot use information that was not yet available.

5. **Market outcomes**  
   Connect events to subsequent market behaviour and abnormal-return labels across multiple horizons.

6. **Event ontology and extraction**  
   Learn structured representations of earnings, guidance, contracts, capital allocation, management changes, and corporate actions.

7. **Historical analogue retrieval**  
   Retrieve prior events that are genuinely comparable economically and temporally.

8. **Novelty, expectations, and materiality**  
   Distinguish routine information from events that meaningfully change the information set.

9. **Outcome-distribution modelling**  
   Estimate calibrated probabilities and return distributions rather than point predictions or unexplained trade calls.

10. **Uncertainty and abstention**  
    Reject cases with weak analogues, missing data, out-of-distribution inputs, or insufficient expected edge.

11. **Autonomous research loop**  
    Continuously ingest, validate, train, evaluate, calibrate, and generate paper decisions against frozen promotion criteria.

12. **Separately gated execution**  
    Live execution remains disabled unless research performance, risk, liquidity, exposure, reconciliation, audit, and kill-switch requirements are explicitly satisfied.

## Current research status

The repository already contains the implemented foundations for:

- repository/configuration and experiment provenance
- point-in-time security-master infrastructure
- SEC disclosure ingestion
- deterministic document normalization
- evidence mapping and timestamp discipline
- market-outcome engine and fixture validation
- corporate-event ontology
- annotation workflow and frozen development release
- non-neural baselines
- event-extraction development package

The next major research stages are learned event extraction, event embeddings and analogue retrieval, novelty/expectations modelling, calibrated outcome alignment, uncertainty/abstention, and the autonomous paper loop.

## Research rules

The project is deliberately built around constraints that prevent attractive but invalid results:

- no current-universe survivorship leakage
- no feature may enter replay before its conservative `tradable_at` time
- raw evidence, normalized documents, events, labels, market data, models, and reports remain separate
- evaluation is split by time and audited for company/related-event leakage
- learned models must beat simple baselines
- predictions are distributions with evidence and uncertainty
- abstention is a first-class output
- final holdouts remain sealed from iterative tuning
- every experiment records its complete configuration and model version

## Engineering

- Python 3.11+
- reproducible configuration under `configs/`
- reusable logic under `src/financial_event_model/`
- deterministic experiment ledger
- automated tests and stage-specific acceptance gates
- generated datasets/checkpoints kept out of version control by default

## Run

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Canonical references

- [Project charter](docs/PROJECT_CHARTER.md)
- [Development roadmap](docs/ROADMAP.md)

The project is currently research/paper only. Broker integration and live trading are intentionally outside the present operating boundary.
