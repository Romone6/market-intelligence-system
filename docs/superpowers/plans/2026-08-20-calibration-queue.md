# Stage 7 Calibration Queue Implementation Plan

> **Execution rule:** preserve the accepted Stage 3 and Stage 4 artifacts as immutable inputs. The generated annotation database is an operational artifact under `data/labels`, not source evidence.

**Goal:** Turn the local annotation application into a deterministic, real 100-document calibration task that two independent annotators can start immediately and audit to completion.

**Architecture:** Join the 100 successful normalization-manifest rows to the 100 timestamp-disciplined knowledge records by normalization ID. Load each normalized JSON document by its manifest path, resolve SEC registrant names from cached submissions metadata, select a bounded event-relevant review section without proposing labels, and insert immutable calibration tasks idempotently. Add store-level progress and pair-agreement reporting, plus an explicit application completion page.

**Tech stack:** Python 3.13, Pydantic, SQLite, standard-library WSGI, pytest.

---

### Task 1: Freeze calibration preparation contracts

**Files:**
- Create: `tests/test_annotation_calibration.py`
- Create: `src/financial_event_model/annotation/calibration.py`
- Modify: `src/financial_event_model/annotation/__init__.py`

1. Write a failing test that creates miniature SEC, normalization, and knowledge stores and expects deterministic `AnnotationTask` objects.
2. Assert exact provenance joins, timezone-aware timestamps, exact evidence offsets, empty candidate labels, and strictly prior same-company disclosure context.
3. Assert the builder refuses a corpus whose count differs from the configured 100-document calibration size.
4. Implement only enough source loading and validation to pass.

### Task 2: Prepare and import the immutable queue

**Files:**
- Modify: `tests/test_annotation_calibration.py`
- Modify: `src/financial_event_model/annotation/calibration.py`
- Modify: `src/financial_event_model/annotation/app.py`

1. Write a failing idempotency test for preparing the same queue twice.
2. Add a `prepare-calibration` command with explicit source paths and safe defaults for the repository artifacts.
3. Preserve the existing no-argument serve behavior and add explicit `serve`, `status`, and `agreement` commands.
4. Import the real 100 tasks into `data/labels/annotations.sqlite` and rerun preparation to prove idempotency.

### Task 3: Make progress and completion observable

**Files:**
- Modify: `tests/test_annotation.py`
- Modify: `src/financial_event_model/annotation/store.py`
- Modify: `src/financial_event_model/annotation/app.py`

1. Write failing tests for annotator progress and the completed-queue page.
2. Add a store query returning total, completed, and remaining counts for one annotator.
3. Route a finished annotator to a completion URL instead of reopening the last task.
4. Show progress on each form and completion status after the final submission.

### Task 4: Make double-label agreement actionable

**Files:**
- Modify: `tests/test_annotation_calibration.py`
- Modify: `src/financial_event_model/annotation/calibration.py`

1. Write failing tests for incomplete pairs, exact label/no-event agreement, disagreements, and adjudication state.
2. Report both annotator completion counts, exact agreement, disagreement IDs, and unresolved disagreement IDs.
3. Reject agreement reporting when the two annotator IDs are identical.
4. Keep disagreement resolution explicit; never silently pick one annotation.

### Task 5: Operational verification and handoff

**Files:**
- Modify: `docs/STAGE_7_ANNOTATION.md`
- Modify: `docs/USER_MANUAL_INPUT_CHECKLIST.md`
- Modify: `docs/CODEX_PROGRESSION_CHECKLIST.md`

1. Run focused calibration and annotation tests.
2. Run the full test suite.
3. Verify the real database contains exactly 100 immutable calibration tasks, zero annotations, and no candidate labels.
4. Start the local WSGI server, request the first task, verify status/headers/progress text, then stop it.
5. Document the exact commands for the two annotators and the agreement report.
