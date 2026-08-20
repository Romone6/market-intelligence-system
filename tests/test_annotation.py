from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

import pytest
from pydantic import ValidationError
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

from financial_event_model.annotation import (
    AdjudicationStatus,
    AnnotationApp,
    AnnotationPolicy,
    AnnotationRecord,
    AnnotationRound,
    AnnotationStore,
    AnnotationTask,
    EvidenceSpan,
    build_dataset_release,
    load_annotation_policy,
)
from financial_event_model.ontology import load_ontology


ROOT = Path(__file__).parents[1]
UTC = timezone.utc


@pytest.fixture(scope="module")
def ontology():
    return load_ontology(ROOT / "configs" / "ontology.yaml")


@pytest.fixture(scope="module")
def policy() -> AnnotationPolicy:
    return load_annotation_policy(ROOT / "configs" / "annotation.yaml")


def make_task(
    event_id: str = "evt-1",
    *,
    company: str = "Example Corp",
    entity_id: str = "cik-1",
    related_event_group: str | None = "offering-1",
    round_: AnnotationRound = AnnotationRound.CALIBRATION,
) -> AnnotationTask:
    published = datetime(2024, 1, 2, 13, 0, tzinfo=UTC)
    section = "The company awarded a binding five-year supply contract to Customer A."
    evidence = "awarded a binding five-year supply contract"
    start = section.index(evidence)
    return AnnotationTask(
        event_id=event_id,
        company=company,
        entity_id=entity_id,
        related_event_group=related_event_group,
        source_published_at=published,
        tradable_at=published + timedelta(minutes=1),
        filing_type="8-K",
        relevant_section=section,
        candidate_evidence=(
            EvidenceSpan(start=start, end=start + len(evidence), text=evidence),
        ),
        prior_company_disclosure="Prior filing disclosed no comparable contract.",
        annotation_round=round_,
        candidate_labels=("contracts.awarded",),
        priority_reason=None,
    )


def contract_attributes() -> dict[str, object]:
    return {
        "certainty": "confirmed",
        "status": "announced",
        "economic_direction": "positive",
        "time_horizon": "medium_term",
        "source_reliability": "primary_filing",
        "counterparty": "Customer A",
        "binding_status": "binding",
    }


def make_record(
    annotation_id: str = "ann-1",
    *,
    event_id: str = "evt-1",
    annotator_id: str = "human-a",
    label: str = "contracts.awarded",
    status: AdjudicationStatus = AdjudicationStatus.SUBMITTED,
    supersedes: str | None = None,
    no_material_event: bool = False,
    created_offset: int = 0,
) -> AnnotationRecord:
    task = make_task(event_id)
    if no_material_event:
        labels: tuple[str, ...] = ()
        attributes: dict[str, dict[str, object]] = {}
        spans: tuple[EvidenceSpan, ...] = ()
    else:
        labels = (label,)
        attributes = {label: contract_attributes()}
        spans = task.candidate_evidence
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id=event_id,
        annotator_id=annotator_id,
        ontology_version="0.1",
        labels=labels,
        attributes=attributes,
        evidence_spans=spans,
        confidence=0.9,
        ambiguity_flag=False,
        no_material_event=no_material_event,
        created_at=datetime(2024, 1, 2, 14, created_offset, tzinfo=UTC),
        supersedes_annotation_id=supersedes,
        adjudication_status=status,
    )


def test_policy_matches_supplied_rounds_and_local_only(policy: AnnotationPolicy) -> None:
    assert policy.host == "127.0.0.1"
    assert policy.rounds.calibration_documents == 100
    assert policy.rounds.gold_minimum_events == 500
    assert policy.rounds.gold_maximum_events == 1000
    assert policy.rounds.minimum_double_label_fraction == pytest.approx(0.2)
    assert policy.rounds.target_double_label_fraction == pytest.approx(0.3)
    assert policy.rounds.expansion_minimum_events == 2000
    assert policy.rounds.expansion_maximum_events == 5000


def test_task_and_annotation_contracts_validate_against_ontology(ontology) -> None:
    task = make_task()
    record = make_record()
    record.validate_against(ontology, task)

    no_event = make_record("ann-none", no_material_event=True)
    no_event.validate_against(ontology, task)


def test_task_rejects_bad_timestamps_and_evidence() -> None:
    task = make_task()
    with pytest.raises(ValidationError, match="tradable_at"):
        AnnotationTask.model_validate(
            task.model_dump() | {"tradable_at": task.source_published_at - timedelta(seconds=1)}
        )
    with pytest.raises(ValidationError, match="candidate evidence"):
        AnnotationTask.model_validate(
            task.model_dump()
            | {"candidate_evidence": [{"start": 0, "end": 3, "text": "wrong"}]}
        )


def test_annotation_rejects_invalid_material_and_no_event_shapes(ontology) -> None:
    task = make_task()
    material = make_record()
    with pytest.raises(ValidationError, match="material annotation"):
        AnnotationRecord.model_validate(material.model_dump() | {"labels": ()})
    with pytest.raises(ValidationError, match="no material event"):
        AnnotationRecord.model_validate(
            material.model_dump() | {"no_material_event": True}
        )
    broken = material.model_copy(
        update={"attributes": {"contracts.awarded": {"certainty": "confirmed"}}}
    )
    with pytest.raises(ValueError, match="missing required attributes"):
        broken.validate_against(ontology, task)


def test_store_is_append_only_and_supersession_is_current(tmp_path: Path, ontology) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    task = make_task()
    store.add_tasks((task,))
    first = make_record()
    store.save_annotation(first)

    replacement = make_record(
        "ann-2", supersedes="ann-1", created_offset=1
    )
    store.save_annotation(replacement)
    assert store.current_annotations("evt-1") == (replacement,)
    assert store.annotation_history("evt-1", "human-a") == (first, replacement)

    with pytest.raises(ValueError, match="current annotation"):
        store.save_annotation(make_record("ann-3", created_offset=2))
    with pytest.raises(ValueError, match="does not reference the current annotation"):
        store.save_annotation(
            make_record("ann-4", supersedes="ann-1", created_offset=3)
        )
    with pytest.raises(ValueError, match="created_at must be later"):
        store.save_annotation(
            make_record("ann-5", supersedes="ann-2", created_offset=0)
        )


def test_down_migration_is_reversible(tmp_path: Path, ontology) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    store.add_tasks((make_task(),))
    store.apply_down_migration()
    assert store.schema_objects() == ()


def invoke_app(
    app: AnnotationApp,
    *,
    method: str = "GET",
    path: str = "/",
    query: str = "",
    form: dict[str, str | list[str]] | None = None,
    declared_length: int | None = None,
) -> tuple[str, dict[str, str], str]:
    payload = urlencode(form or {}, doseq=True).encode()
    environ: dict[str, object] = {}
    setup_testing_defaults(environ)
    environ.update(
        {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(declared_length if declared_length is not None else len(payload)),
            "wsgi.input": BytesIO(payload),
        }
    )
    captured: dict[str, object] = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = dict(headers)

    response = app(environ, start_response)
    try:
        body = b"".join(response).decode()
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()
    return str(captured["status"]), dict(captured["headers"]), body


class FormAccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.control_ids: set[str] = set()
        self.label_targets: set[str] = set()
        self.legend_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"input", "select", "textarea"} and values.get("type") != "hidden":
            if values.get("id"):
                self.control_ids.add(str(values["id"]))
        if tag == "label" and values.get("for"):
            self.label_targets.add(str(values["for"]))
        if tag == "legend":
            self.legend_count += 1


def test_annotation_page_is_complete_escaped_and_accessible(
    tmp_path: Path, ontology, policy: AnnotationPolicy
) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    task = make_task(company='<script>alert("x")</script>')
    store.add_tasks((task,))
    app = AnnotationApp(store, ontology, policy, csrf_token="test-token")
    status, headers, body = invoke_app(app)

    assert status == "200 OK"
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert "<main" in body and "<form" in body and "<fieldset" in body
    assert "<mark>awarded a binding five-year supply contract</mark>" in body
    assert "&lt;script&gt;" in body and '<script>alert("x")</script>' not in body
    for control in (
        "annotator_id",
        "label-contracts-awarded",
        "confidence",
        "ambiguity_flag",
        "no_material_event",
    ):
        assert f'id="{control}"' in body
    assert '<label for="confidence">' in body
    assert "Publication" in body and "Tradable" in body
    assert "Prior company disclosure" in body
    parser = FormAccessibilityParser()
    parser.feed(body)
    assert parser.control_ids <= parser.label_targets
    assert parser.legend_count == 4


def test_post_rejects_csrf_oversize_and_textually_reports_errors(
    tmp_path: Path, ontology, policy: AnnotationPolicy
) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    store.add_tasks((make_task(),))
    app = AnnotationApp(store, ontology, policy, csrf_token="test-token")

    status, _, body = invoke_app(
        app,
        method="POST",
        path="/annotations",
        form={"csrf_token": "wrong", "event_id": "evt-1"},
    )
    assert status == "403 Forbidden"
    assert "Security token" in body

    status, _, body = invoke_app(
        app,
        method="POST",
        path="/annotations",
        declared_length=policy.max_request_bytes + 1,
    )
    assert status == "413 Payload Too Large"

    excessive_fields = {f"field-{index}": "x" for index in range(501)}
    excessive_fields["csrf_token"] = "test-token"
    status, _, body = invoke_app(
        app,
        method="POST",
        path="/annotations",
        form=excessive_fields,
    )
    assert status == "400 Bad Request"
    assert "too many fields" in body.casefold()

    status, _, body = invoke_app(
        app,
        method="POST",
        path="/annotations",
        form={
            "csrf_token": "test-token",
            "event_id": "evt-1",
            "annotator_id": "human-a",
            "confidence": "0.9",
            "labels": "contracts.awarded",
        },
    )
    assert status == "400 Bad Request"
    assert 'role="alert"' in body
    assert "Please correct" in body


def test_post_saves_no_material_annotation_and_wsgi_conforms(
    tmp_path: Path, ontology, policy: AnnotationPolicy
) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    store.add_tasks((make_task(),))
    app = AnnotationApp(store, ontology, policy, csrf_token="test-token")
    status, headers, _ = invoke_app(
        validator(app),
        method="POST",
        path="/annotations",
        form={
            "csrf_token": "test-token",
            "event_id": "evt-1",
            "annotator_id": "human-a",
            "confidence": "0.85",
            "no_material_event": "on",
            "adjudication_status": "submitted",
        },
    )
    assert status == "303 See Other"
    assert headers["Location"].startswith("/?event_id=evt-1&saved=")
    assert store.current_annotations("evt-1")[0].no_material_event is True


def test_post_saves_material_annotation_with_typed_attributes(
    tmp_path: Path, ontology, policy: AnnotationPolicy
) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    task = make_task()
    store.add_tasks((task,))
    app = AnnotationApp(store, ontology, policy, csrf_token="test-token")
    span = task.candidate_evidence[0]
    status, _, _ = invoke_app(
        app,
        method="POST",
        path="/annotations",
        form={
            "csrf_token": "test-token",
            "event_id": "evt-1",
            "annotator_id": "human-a",
            "confidence": "0.92",
            "labels": "contracts.awarded",
            "evidence_span": f"{span.start}:{span.end}",
            "attribute__certainty": "confirmed",
            "attribute__status": "announced",
            "attribute__economic_direction": "positive",
            "attribute__source_reliability": "primary_filing",
            "attribute__counterparty": "Customer A",
            "attribute__binding_status": "binding",
            "attribute__government_customer": "false",
            "adjudication_status": "submitted",
        },
    )
    assert status == "303 See Other"
    saved = store.current_annotations("evt-1")[0]
    assert saved.labels == ("contracts.awarded",)
    assert saved.attributes["contracts.awarded"]["government_customer"] is False


def test_successful_post_advances_to_next_unannotated_task(
    tmp_path: Path, ontology, policy: AnnotationPolicy
) -> None:
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    store.add_tasks((make_task("evt-1"), make_task("evt-2")))
    app = AnnotationApp(store, ontology, policy, csrf_token="test-token")
    status, headers, _ = invoke_app(
        app,
        method="POST",
        path="/annotations",
        form={
            "csrf_token": "test-token",
            "event_id": "evt-1",
            "annotator_id": "human-a",
            "confidence": "0.85",
            "no_material_event": "on",
            "adjudication_status": "submitted",
        },
    )
    assert status == "303 See Other"
    assert headers["Location"].startswith("/?event_id=evt-2&saved=")


def make_release_records(
    tasks: tuple[AnnotationTask, ...], *, double_label_count: int
) -> tuple[AnnotationRecord, ...]:
    records: list[AnnotationRecord] = []
    for index, task in enumerate(tasks):
        records.append(
            make_record(
                f"ann-a-{index}",
                event_id=task.event_id,
                annotator_id="human-a",
                created_offset=index % 60,
            )
        )
        if index < double_label_count:
            records.append(
                make_record(
                    f"ann-b-{index}",
                    event_id=task.event_id,
                    annotator_id="human-b",
                    created_offset=index % 60,
                )
            )
    return tuple(records)


def test_release_split_blocks_company_and_related_event_leakage(
    ontology, policy: AnnotationPolicy
) -> None:
    tasks = (
        make_task("evt-1", entity_id="cik-a", related_event_group="group-1"),
        make_task("evt-2", entity_id="cik-a", related_event_group="group-2"),
        make_task("evt-3", entity_id="cik-b", related_event_group="group-2"),
        make_task("evt-4", entity_id="cik-c", related_event_group="group-3"),
        make_task("evt-5", entity_id="cik-d", related_event_group="group-4"),
    )
    records = make_release_records(tasks, double_label_count=2)
    release = build_dataset_release(
        tasks,
        records,
        ontology,
        policy,
        release_id="fixture-release",
        evidence_kind="fixture",
    )
    assignment = {
        event_id: split
        for split, ids in (("train", release.train_event_ids), ("eval", release.eval_event_ids))
        for event_id in ids
    }
    assert assignment["evt-1"] == assignment["evt-2"] == assignment["evt-3"]
    assert release.leakage.entity_intersection == ()
    assert release.leakage.related_event_intersection == ()
    assert release.stage_acceptance_passed is False


def test_release_is_deterministic_reports_rare_labels_and_freezes_once(
    tmp_path: Path, ontology, policy: AnnotationPolicy
) -> None:
    tasks = tuple(
        make_task(
            f"evt-{index}",
            entity_id=f"cik-{index}",
            related_event_group=f"group-{index}",
            round_=AnnotationRound.GOLD,
        )
        for index in range(10)
    )
    records = make_release_records(tasks, double_label_count=3)
    first = build_dataset_release(
        tasks,
        records,
        ontology,
        policy,
        release_id="r1",
        evidence_kind="fixture",
    )
    second = build_dataset_release(
        tuple(reversed(tasks)),
        tuple(reversed(records)),
        ontology,
        policy,
        release_id="r1",
        evidence_kind="fixture",
    )
    assert first.train_event_ids == second.train_event_ids
    assert first.eval_event_ids == second.eval_event_ids
    assert first.content_hash == second.content_hash
    assert first.class_distribution == {"contracts.awarded": 10}
    assert first.rare_labels["contracts.awarded"] == 10
    assert first.rare_labels["guidance.raised"] == 0
    assert first.agreement.double_label_fraction == pytest.approx(0.3)

    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    store.freeze_release(first)
    assert store.get_release("r1") == first
    with pytest.raises(ValueError, match="already frozen"):
        store.freeze_release(first.model_copy(update={"content_hash": "f" * 64}))


def test_unadjudicated_disagreement_blocks_release(ontology, policy) -> None:
    tasks = (make_task(),)
    first = make_record()
    second = make_record(
        "ann-2",
        annotator_id="human-b",
        label="contracts.cancelled",
    ).model_copy(
        update={
            "attributes": {
                "contracts.cancelled": contract_attributes()
                | {"status": "cancelled", "economic_direction": "negative"}
            }
        }
    )
    with pytest.raises(ValueError, match="requires adjudication"):
        build_dataset_release(
            tasks,
            (first, second),
            ontology,
            policy,
            release_id="blocked",
            evidence_kind="fixture",
        )


def test_release_rejects_cross_annotator_supersession(ontology, policy) -> None:
    tasks = (make_task(),)
    first = make_record()
    invalid = make_record(
        "ann-2",
        annotator_id="human-b",
        supersedes="ann-1",
        created_offset=1,
    )
    with pytest.raises(ValueError, match="same event and annotator"):
        build_dataset_release(
            tasks,
            (first, invalid),
            ontology,
            policy,
            release_id="invalid-history",
            evidence_kind="fixture",
        )


def test_human_gold_gate_requires_real_size_and_double_label_coverage(
    ontology, policy
) -> None:
    tasks = tuple(
        make_task(
            f"gold-{index}",
            entity_id=f"cik-{index}",
            related_event_group=f"group-{index}",
            round_=AnnotationRound.GOLD,
        )
        for index in range(500)
    )
    records = make_release_records(tasks, double_label_count=100)
    release = build_dataset_release(
        tasks,
        records,
        ontology,
        policy,
        release_id="human-gold-v1",
        evidence_kind="human",
    )
    assert release.contract_checks_passed is True
    assert release.stage_acceptance_passed is True
    assert len(release.train_event_ids) + len(release.eval_event_ids) == 500
    assert set(release.train_event_ids).isdisjoint(release.eval_event_ids)
    assert json.loads(release.model_dump_json())["evidence_kind"] == "human"
