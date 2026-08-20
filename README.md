# Financial Event Model

An independently trained, point-in-time financial-event research system built from open-source components. This repository is not a generative trading wrapper. Its learned components must produce traceable event representations, calibrated outcome distributions, uncertainty, and abstention under the rules in the [project charter](docs/PROJECT_CHARTER.md).

## Status

Stages 0–4 are implemented through the timestamp-disciplined historical knowledge layer. The Stage 5 market/outcome engine is fixture-verified, but its live 100-filing gate remains open because authenticated consolidated daily bars are not configured. Ontology v0.1 and its agreement audit are implemented; the Stage 6 two-human, 100-real-event gate remains open. The Stage 7 local annotation application and leakage-safe release controls are fixture-verified, while the real 500–1,000-event human gold set remains open. Authoritative historical-universe population also remains open. Research and paper operation only; broker and live-trading paths do not exist.

## Install

```powershell
python -m pip install -e ".[dev]"
```

## Test

```powershell
python -m pytest
```

## Record an experiment

```python
from financial_event_model.experiments import ExperimentStore

store = ExperimentStore("reports/experiments.sqlite3")
record = store.record(
    ["configs/universe.yaml", "configs/ontology.yaml", "configs/training.yaml"],
    model_version="baseline-v0.1",
)
print(record.run_id, record.config_hash)
```

The ledger stores the parsed configuration itself and its deterministic SHA-256 digest, so later edits cannot rewrite what a run used.

## Repository boundaries

- `configs/`: versioned universe, ontology, and training policy.
- `data/raw/`: immutable downloaded source objects.
- `data/normalized/`: deterministic parsed representations.
- `data/events/`: extracted event objects and evidence.
- `data/labels/`: generated event annotations and point-in-time outcome labels.
- `data/market/`: market observations and corporate-action inputs.
- `data/security_master/`: generated point-in-time entity, security, identifier, and universe database.
- `models/`: generated checkpoints and calibration artifacts.
- `reports/`: generated experiment evidence; the local SQLite ledger defaults here.
- `src/financial_event_model/`: all reusable business logic.
- `notebooks/`: disposable analysis clients; no authoritative logic.

Generated data, models, and reports are ignored by Git. Commit schemas, configs, manifests, tests, and documentation—not irreplaceable runtime artifacts.

## Canonical references

Read [the project charter](docs/PROJECT_CHARTER.md) before changing scope or proof claims, then follow the staged [development roadmap](docs/ROADMAP.md). Current proof boundaries are recorded in [Stage 1: Point-in-Time Security Master](docs/STAGE_1_SECURITY_MASTER.md), [Stage 2: SEC Ingestion](docs/STAGE_2_SEC_INGESTION.md), [Stage 3: Normalization and Evidence Mapping](docs/STAGE_3_NORMALIZATION.md), [Stage 4: Timestamp Discipline and Historical Knowledge](docs/STAGE_4_TIMESTAMP_DISCIPLINE.md), [Stage 5: Market Data and Outcome Labels](docs/STAGE_5_MARKET_OUTCOMES.md), [Stage 6: Event Ontology v0.1](docs/STAGE_6_ONTOLOGY.md), and [Stage 7: Annotation Application and Gold-Set Controls](docs/STAGE_7_ANNOTATION.md).
