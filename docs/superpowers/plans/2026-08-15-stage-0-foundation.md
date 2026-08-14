# Stage 0 Foundation Implementation Plan

> **For agentic workers:** Implement task-by-task with test-first red/green cycles. Do not add training or trading behavior to this plan.

**Goal:** Establish a reproducible repository whose project intent, core data contracts, configuration, and experiment provenance cannot drift or become mixed with generated artifacts.

**Architecture:** Use one importable Python package under `src/`, Pydantic contracts at data boundaries, YAML for human-owned configuration, and SQLite from the Python standard library for the local experiment ledger. Generated research artifacts remain in ignored, purpose-specific directories.

**Tech Stack:** Python 3.11+, Pydantic 2, PyYAML 6, SQLite, pytest, Git.

## Global Constraints

- Research/paper mode only; broker and live trading remain disabled.
- No generative trade-decider or external-model API dependency.
- Every experiment stores a configuration snapshot and digest.
- Every event prediction includes a non-empty model version.
- No irreplaceable business logic in notebooks.

---

### Task 1: Public package and typed contracts

**Files:**
- Create: `src/financial_event_model/__init__.py`
- Create: `src/financial_event_model/contracts.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces: `RawDocument`, `FinancialEvent`, and `EventPrediction` Pydantic models.

- [ ] Write a failing importability test and run `python -m pytest tests/test_package.py -q`.
- [ ] Add the minimal package so the import test passes.
- [ ] Write contract tests for timezone-aware timestamps and non-empty model versions; run them red.
- [ ] Implement only the specified fields and validation; run the contract tests green.

### Task 2: Configuration and experiment provenance

**Files:**
- Create: `src/financial_event_model/experiments.py`
- Test: `tests/test_experiments.py`
- Verify: `configs/universe.yaml`, `configs/ontology.yaml`, `configs/training.yaml`

**Interfaces:**
- Consumes: one or more YAML paths and a model version.
- Produces: `ExperimentStore.record(...) -> ExperimentRecord` and persistent SQLite rows containing the full merged configuration and SHA-256 digest.

- [ ] Write a failing test that records temporary YAML configs and reads the exact stored snapshot back.
- [ ] Implement deterministic config loading, hashing, SQLite creation, recording, and lookup.
- [ ] Run `python -m pytest tests/test_experiments.py -q` green.

### Task 3: Repository boundaries and operator documentation

**Files:**
- Create: `README.md`
- Create: required data/model/report/source directories with tracked keep-files.
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: a one-command install, one-command test, canonical charter link, and explicit paper/live gates.

- [ ] Write a failing structure/config test.
- [ ] Create only the directories required by the supplied Stage 0 specification.
- [ ] Document install, test, experiment recording, and artifact boundaries.
- [ ] Run the full `python -m pytest` suite and inspect `git status --short`.

