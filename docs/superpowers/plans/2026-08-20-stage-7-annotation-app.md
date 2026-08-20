# Stage 7 Annotation Application Implementation Plan

> **For agentic workers:** Implement each task test-first and preserve the distinction between software fixtures and real human annotation evidence.

**Goal:** Build the local annotation workflow and immutable dataset-release controls needed to produce proprietary event labels without leaking companies or related events into evaluation.

**Architecture:** A strict Pydantic contract layer validates annotation tasks and append-only records against ontology v0.1. A small SQLite store applies reversible migrations and preserves supersession history. A localhost-only WSGI application renders an accessible server-side form. A deterministic release builder operates on adjudicated/current records, assigns connected company/related-event groups wholly to train or evaluation, and emits immutable manifests with agreement, distribution, rare-label, and acceptance reports.

**Tech Stack:** Python 3.11+, Pydantic, PyYAML, SQLite, standard-library WSGI/HTML/URL parsing, pytest.

## Global Constraints

- The canonical authority remains `docs/PROJECT_CHARTER.md`; this stage does not add model inference or trading.
- The UI must show every field in the supplied Stage 7 interface contract.
- Annotation writes are append-only. A correction creates a new record whose `supersedes_annotation_id` points to the annotator's current record for the same event.
- `no_material_event` is mutually exclusive with ontology labels; material records require at least one valid ontology label and valid required attributes.
- The application binds to `127.0.0.1`, escapes rendered source content, limits request bodies, and requires a process-local CSRF token on writes.
- Evaluation membership is deterministic and immutable per release. A company or connected related-event group may not span train and evaluation.
- Fixture data validates code only. Stage 7 acceptance requires 500–1,000 real human-labelled gold events, 20–30% double-label coverage, adjudicated disagreements, and a frozen leakage-free release.

Python describes SQLite as a “lightweight disk-based database” with no separate server and says to “Always use placeholders” for bound data ([Python `sqlite3`](https://docs.python.org/3.13/library/sqlite3.html)). Python also warns that `wsgiref` “is not recommended for production,” so this server is explicitly local research tooling, not a deployable service ([Python `wsgiref`](https://docs.python.org/3.13/library/wsgiref.html)).

---

### Task 1: Freeze annotation and round policy contracts

**Files:**
- Create: `configs/annotation.yaml`
- Create: `src/financial_event_model/annotation/models.py`
- Create: `src/financial_event_model/annotation/__init__.py`
- Create: `tests/test_annotation.py`

**Interfaces:**
- Produces `AnnotationTask`, `EvidenceSpan`, `AnnotationRecord`, `AdjudicationStatus`, and `AnnotationPolicy`.
- Validates timestamp order, exact ontology versions, evidence bounds, confidence, labels/attributes, no-material exclusivity, and supersession identifiers.

- [x] Write failing contract tests for valid material/no-material records and every rejected invariant.
- [x] Run `python -m pytest tests/test_annotation.py -q` and observe the missing-module failure.
- [x] Implement only the models and YAML policy required by those tests.
- [x] Re-run the focused tests.

```python
# Pydantic model validation: https://docs.pydantic.dev/latest/concepts/models/
record = AnnotationRecord.model_validate(payload)
record.validate_against(ontology)
```

The W3C says form labels should “describe the purpose of the form control,” so field names in the contract will also drive explicit visible labels in the UI ([W3C WAI form labels](https://www.w3.org/WAI/tutorials/forms/labels/)).

### Task 2: Add reversible append-only persistence

**Files:**
- Create: `src/financial_event_model/annotation/migrations/0001_annotations.sql`
- Create: `src/financial_event_model/annotation/migrations/0001_annotations.down.sql`
- Create: `src/financial_event_model/annotation/store.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_annotation.py`

**Interfaces:**
- `AnnotationStore(path)` migrates on construction.
- `add_tasks`, `get_task`, `list_tasks`, `save_annotation`, `current_annotations`, and `freeze_release` use parameterized SQL.
- Supersession must reference the current record for the same event and annotator; old rows never change.

- [x] Add failing migration, persistence, supersession, and immutable-release tests.
- [x] Observe those failures.
- [x] Implement the migration/store and include migration SQL as package data.
- [x] Re-run the focused tests and exercise the down migration on a temporary copy.

```python
# Parameter binding: https://docs.python.org/3.13/library/sqlite3.html
connection.execute("SELECT * FROM annotations WHERE event_id = ?", (event_id,))
```

Python documents that inserts open a transaction that “needs to be committed,” and its connection context manager supplies the required atomic boundary ([Python `sqlite3`](https://docs.python.org/3.13/library/sqlite3.html)).

### Task 3: Build the accessible localhost annotation workflow

**Files:**
- Create: `src/financial_event_model/annotation/app.py`
- Modify: `tests/test_annotation.py`

**Interfaces:**
- `AnnotationApp(store, ontology, policy, csrf_token)` is a WSGI callable.
- `GET /` renders one task plus prior disclosure, highlighted evidence, ontology controls, attributes, confidence, ambiguity, and no-material control.
- `POST /annotations` validates and saves a record, then redirects; bad input returns textual field errors with status 400.
- `serve()` binds only to the configured loopback host.

- [x] Add failing WSGI tests for page content, escaping, explicit labels, keyboard-visible structure, CSRF, request limits, successful saves, and textual validation errors.
- [x] Observe failures.
- [x] Implement the minimal server-rendered application with no client dependency.
- [x] Re-run focused tests and validate the WSGI callable with `wsgiref.validate`.

```python
# WSGI test defaults: https://docs.python.org/3.13/library/wsgiref.html
environ = {}
setup_testing_defaults(environ)
body = b"".join(app(environ, start_response))
```

Python calls `make_server` a server listening on a supplied host and port; this stage supplies `127.0.0.1` only ([Python `wsgiref`](https://docs.python.org/3.13/library/wsgiref.html)). W3C requires detected input errors to be “identified and described to the user in text” ([WCAG 2.2 error identification](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html)). A random token uses `secrets.token_urlsafe`, and equality uses a “constant-time compare” ([Python `secrets`](https://docs.python.org/3.13/library/secrets.html)).

### Task 4: Build frozen leakage-safe releases and reports

**Files:**
- Create: `src/financial_event_model/annotation/dataset.py`
- Modify: `src/financial_event_model/annotation/__init__.py`
- Modify: `tests/test_annotation.py`

**Interfaces:**
- `build_dataset_release(tasks, records, policy, ontology, evidence_kind, release_id)` resolves current records, computes dual-label agreement, and requires adjudication for disagreements.
- Company identifiers and related-event identifiers form connected components; each component is assigned wholly to train or evaluation by a seeded SHA-256 rank.
- The release contains task IDs only, an ontology/config digest, class distribution, rare-label counts, agreement measures, leakage findings, completeness gates, and `stage_acceptance_passed`.

- [x] Add failing tests for bridged related-event leakage, deterministic membership, rare labels, disagreement/adjudication, immutable release IDs, and fixture-vs-human acceptance.
- [x] Observe failures.
- [x] Implement the deterministic connected-component split and reports.
- [x] Re-run focused tests and assert zero train/evaluation entity and related-event intersections.

```python
# SHA-256 API: https://docs.python.org/3.13/library/hashlib.html
rank = hashlib.sha256(f"{seed}:{component}".encode()).hexdigest()
```

Python guarantees the `sha256()` constructor and documents `hexdigest()` as hexadecimal output safe for exchange, making release ranking and content identities reproducible ([Python `hashlib`](https://docs.python.org/3.13/library/hashlib.html)).

### Task 5: Record the proof boundary and verify the repository

**Files:**
- Create: `docs/STAGE_7_ANNOTATION.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: this plan

- [x] Document the localhost run/import/release workflows and exact human acceptance gates.
- [x] Run the focused tests, full suite, compilation, editable install, and diff checks.
- [x] Inspect rendered HTML behavior and verify no generated data/database was committed.
- [x] Review and commit the exact Stage 7 file set.

```powershell
# Editable installation: https://pip.pypa.io/en/stable/topics/local-project-installs/
python -m pip install -e ".[dev]"
python -m pytest
python -m compileall -q src tests
git diff --check
```

## Correctness traces

1. An annotator submits a material contract label; CSRF and size checks pass; form values parse; ontology validation confirms required shared/contract attributes; the append-only store inserts a new record; a later correction must point to that current record and never mutates it.
2. Two tasks share a company and a third task shares a related-event ID with the second. The union operation forms one connected component; the seeded component assignment sends all three to one split; both company and related-event train/evaluation intersections remain empty.
3. A deterministic 600-item fixture can pass structural gold gates but cannot set `stage_acceptance_passed`; only `evidence_kind='human'` plus complete size, double-label, adjudication, frozen-release, and leakage checks can do so.

## Proof boundary

This implementation can prove contract validation, durable history, local workflow behavior, deterministic split integrity, and report math. It cannot manufacture the required human labor or real gold data. Stage 7 remains operationally open until a real human-labelled release satisfies every frozen acceptance gate.
