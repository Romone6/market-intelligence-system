# Stage 7: Annotation Application and Gold-Set Controls

## Demonstrated boundary

Stage 7 now has a local annotation workflow, append-only records, deterministic dataset releases, measured label agreement, class and rare-label reports, and a split algorithm that keeps connected companies and related events entirely within training or evaluation. The real 100-document calibration queue is prepared from the accepted Stage 3 corpus and its matching Stage 4 knowledge records.

The engine and the AI-panel development calibration are verified. The panel output is explicitly `ai_panel`, not human evidence: it does not claim that 500–1,000 real events have been labelled by people, that two independent human passes occurred, or that a human-gold evaluation set is complete. On 2026-08-21 the user froze those human-data gates until pre-finalization, with an earlier unfreeze if the embedding model underperforms.

## Components

- [`configs/annotation.yaml`](../configs/annotation.yaml) freezes local-server, round-size, double-label, rare-label, and split policy.
- `AnnotationTask` carries company, entity and related-event identities, publication and tradable timestamps, filing type, relevant section, exact candidate evidence spans, prior disclosure, round, candidate labels, and prioritization context.
- `AnnotationRecord` preserves the supplied record fields plus explicit ambiguity and no-material-event decisions. Material labels are checked against ontology v0.1.
- `AnnotationStore` applies a reversible SQLite migration. Corrections append a record whose `supersedes_annotation_id` must identify the same annotator's current record; prior rows are never updated.
- `AnnotationApp` is a server-rendered WSGI form bound to `127.0.0.1`. It escapes document content, limits request size, requires a process-local CSRF token, emits restrictive browser headers, and reports validation failures in text.
- `build_dataset_release` freezes exact task hashes and annotation IDs. Its manifest also contains ontology/policy hashes, train/evaluation membership, agreement, class counts, rare counts, leakage findings, and acceptance gates.

`wsgiref` is intentionally used only for a local research utility. It is not a production application server and must not be exposed to a network.

## Prepare the real calibration queue

The operational command joins accepted normalized documents to knowledge records by immutable normalization ID, resolves registrant names from cached SEC submissions, validates exact evidence spans, enforces the configured corpus size, and imports tasks idempotently:

```powershell
python -m financial_event_model.annotation prepare-calibration
```

The accepted local run produced:

```text
task_count: 100
entity_count: 44
queue_hash: 5cc1ff2c0e0b182cc5d568d2469300d69c27dfba1010726153de69d6f6f0736f
```

All 100 tasks are Round 1 calibration tasks. The import contains zero candidate labels so the queue cannot leak generated label suggestions into the independent pass. Candidate evidence highlights are deterministic review aids, not truth. Task IDs are immutable; re-importing identical content is idempotent, and reusing an event ID with different content fails.

## Frozen AI-panel development release

Five model passes, deterministic exact-label voting, and nine user adjudications were canonicalized into 100 ontology-valid records. Every material record has exact evidence offsets into the immutable task text. The import uses annotator identity `ai-panel-v1`; the frozen release uses `evidence_kind="ai_panel"`, which can never satisfy the human-gold acceptance flag.

```python
from financial_event_model.annotation import AnnotationStore, load_annotation_policy
from financial_event_model.annotation.panel_synthesis import import_panel_release
from financial_event_model.ontology import load_ontology

ontology = load_ontology("configs/ontology.yaml")
policy = load_annotation_policy("configs/annotation.yaml")
store = AnnotationStore("data/labels/annotations.sqlite", ontology)
release = import_panel_release(
    store,
    "data/labels/panel_canonical_annotations_001_100.jsonl",
    policy,
    release_id="stage7-ai-panel-v0.1",
)
```

The accepted release contains 100 records: 30 material-event records and 70 `no_material_event` records. Its connected-component split contains 78 training and 22 evaluation records with zero company or related-event leakage. Release content hash:

```text
6cd6233f32b761dfdf047f58530e9f53d59c621985d624f0459642ffbed114db
```

## Run the local application

After editable installation:

```powershell
python -m financial_event_model.annotation serve
```

Open `http://127.0.0.1:8765/?annotator_id=YOUR_STABLE_ID`. Stopping the process rotates the CSRF token. The form exposes:

- company, filing type, publication time, and conservative tradable time;
- relevant section with escaped highlighted candidate evidence;
- prior company disclosure;
- all 25 ontology labels and ontology-defined attribute fields;
- evidence-span selection, confidence, ambiguity, and no-material-event controls;
- adjudication status and explicit supersession for corrections;
- per-annotator progress and a genuine completion page after document 100.

Candidate labels are hints, not accepted annotations. Stage 7 stores candidate metadata for Round 3, but it does not generate model-assisted suggestions before a model exists.

Inspect progress without opening the browser:

```powershell
python -m financial_event_model.annotation status --annotator-id YOUR_STABLE_ID
```

After two independent passes, produce the pair report:

```powershell
python -m financial_event_model.annotation agreement --annotator-a ANNOTATOR_A_ID --annotator-b ANNOTATOR_B_ID
```

The report lists incomplete, disagreement, and unresolved event IDs. It never silently selects one annotator's decision.

## Freeze a dataset release

```python
from financial_event_model.annotation import (
    AnnotationStore,
    build_dataset_release,
    load_annotation_policy,
)
from financial_event_model.ontology import load_ontology

ontology = load_ontology("configs/ontology.yaml")
policy = load_annotation_policy("configs/annotation.yaml")
store = AnnotationStore("data/labels/annotations.sqlite", ontology)
tasks = store.list_tasks()
records = tuple(
    record
    for task in tasks
    for record in store.current_annotations(task.event_id)
)
release = build_dataset_release(
    tasks,
    records,
    ontology,
    policy,
    release_id="gold-v1",
    evidence_kind="human",
)
store.freeze_release(release)
```

The release resolves current records before freezing exact annotation IDs. Disagreeing independent records require a current `adjudicated` record for that event. The release builder rejects unresolved disagreements instead of silently choosing a label.

## Leakage control

The split unit is a connected component, not an individual event. Events are joined when they share either:

- `entity_id`; or
- `related_event_group`.

These joins are transitive. If event A shares a company with B and B shares a related-event group with C, all three remain in one split. Components receive deterministic SHA-256 ranks from the frozen split seed. The release reports the company and related-event intersections, both of which must be empty.

## Annotation rounds and acceptance

The configured human workflow remains preserved but frozen:

1. Calibration: 100 documents, all double-labelled, every disagreement resolved, ontology definitions revised through a new version when necessary.
2. Gold: 500–1,000 events, at least 20% double-labelled with a 30% target, all disagreements adjudicated.
3. Expansion: 2,000–5,000 reviewed events, with later model-assisted candidates prioritizing unusual or uncertain cases.

A Stage 7 release passes only when:

- its evidence kind is honestly recorded as `human`;
- 500–1,000 resolved Round 2 gold events are present;
- double-label coverage is at least 20%;
- all observed label disagreements are adjudicated;
- both training and evaluation are non-empty;
- company and related-event leakage are zero.

The `evidence_kind` field is an explicit provenance assertion, not biometric proof of who labelled data. Operating records must substantiate that assertion.

The AI-panel release intentionally has `contract_checks_passed=false` and `stage_acceptance_passed=false`. It is authorized for development experiments, not final human-gold claims or final model promotion.

## Current evidence

Twenty-five focused annotation test cases cover contract rejection, ontology validation, exact evidence offsets, reversible migration, immutable supersession, queue advancement, progress/completion, accessible form structure and explicit control labels, output escaping, CSRF and request-shape limits, no-event and typed material submissions, WSGI conformance, real-source calibration construction, exact corpus enforcement, idempotent preparation, pair status/disagreement reporting, AI-panel synthesis/import provenance, transitive leakage grouping, deterministic releases, rare and absent labels, immutable release IDs, unresolved disagreement blocking, and the configured human gate.

The current full repository suite passes with 107 tests. SQLite contains 100 immutable tasks, 100 current `ai-panel-v1` annotations, and frozen release `stage7-ai-panel-v0.1`. The release has zero split leakage and remains explicitly non-human. A live loopback request returned status 200 with the restrictive Content Security Policy and the source-document workflow.

## Development closure and frozen human gate

**Stage 7 is complete for development on the frozen AI-panel release.** The human workflow, queue, ontology and acceptance checks remain intact. Before model finalization—or earlier if embedding performance is inadequate—the project must unfreeze the two-human calibration pass and 500–1,000-event human-gold checklist in `docs/CODEX_PROGRESSION_CHECKLIST.md`. Until then, no artifact may be described as human gold and no final model promotion may claim the human acceptance gate passed.
