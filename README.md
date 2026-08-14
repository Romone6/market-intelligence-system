# Financial Event Model

An independently trained, point-in-time financial-event research system built from open-source components. This repository is not a generative trading wrapper. Its learned components must produce traceable event representations, calibrated outcome distributions, uncertainty, and abstention under the rules in the [project charter](docs/PROJECT_CHARTER.md).

## Status

Stage 0 foundation. Research and paper operation only. Broker and live-trading paths do not exist.

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
- `data/labels/`: point-in-time outcome labels.
- `data/market/`: market observations and corporate-action inputs.
- `models/`: generated checkpoints and calibration artifacts.
- `reports/`: generated experiment evidence; the local SQLite ledger defaults here.
- `src/financial_event_model/`: all reusable business logic.
- `notebooks/`: disposable analysis clients; no authoritative logic.

Generated data, models, and reports are ignored by Git. Commit schemas, configs, manifests, tests, and documentation—not irreplaceable runtime artifacts.

## Canonical references

Read [the project charter](docs/PROJECT_CHARTER.md) before changing scope or proof claims, then follow the staged [development roadmap](docs/ROADMAP.md).
