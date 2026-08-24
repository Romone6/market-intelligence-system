from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from financial_event_model.annotation import (
    AdjudicationStatus,
    AnnotationRecord,
    AnnotationStore,
    build_calibration_tasks,
    calibration_agreement,
    load_annotation_policy,
    prepare_calibration,
)
from financial_event_model.annotation.app import main as annotation_main
from financial_event_model.annotation import panel_synthesis
from financial_event_model.annotation.panel_synthesis import (
    _near_task_id,
    _resolve_value,
    align_quote,
    write_jsonl,
)
from financial_event_model.ontology import load_ontology


ROOT = Path(__file__).parents[1]
UTC = timezone.utc


def test_panel_synthesis_repairs_source_offsets_and_records_tiebreaks(
    tmp_path: Path,
) -> None:
    section = "The board approved\n\na new $500 million buyback — effective today."
    span = align_quote(
        section,
        "The board approved a new $500 million buyback - effective today.",
    )
    assert span is not None
    assert section[span.start : span.end] == span.text
    assert span.text == section

    value, models, rule = _resolve_value(
        {"A": "neutral", "B": "positive", "D": "positive", "E": "neutral"}
    )
    assert value == "neutral"
    assert models == ["A", "E"]
    assert rule == "model_priority_tiebreak"
    assert _near_task_id("calibration-abc", "calibration-abcd") is True
    assert _near_task_id("calibration-abc", "calixration-abd") is True
    assert _near_task_id("calibration-abc", "unrelated-task") is False

    output = tmp_path / "panel.jsonl"
    digest = write_jsonl(({"text": "source–aligned"},), output)
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()


def test_ai_panel_import_is_idempotent_and_never_claims_human_gold(
    tmp_path: Path,
    ontology,
) -> None:
    sec_path, normalized_path, knowledge_path = _build_sources(tmp_path)
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    prepare_calibration(
        store,
        sec_manifest_path=sec_path,
        normalization_manifest_path=normalized_path,
        knowledge_store_path=knowledge_path,
        expected_documents=2,
    )
    first_task, second_task = store.list_tasks()
    span = first_task.candidate_evidence[0]
    canonical = tmp_path / "panel.jsonl"
    rows = (
        {
            "task_number": 1,
            "task_id": first_task.event_id,
            "labels": ["corporate_action.restructuring"],
            "attributes": {
                "corporate_action.restructuring": {
                    "certainty": "confirmed",
                    "status": "announced",
                    "economic_direction": "neutral",
                    "source_reliability": "primary_filing",
                }
            },
            "evidence_spans": [span.model_dump(mode="json")],
            "confidence": 0.9,
            "ambiguity_flag": False,
            "no_material_event": False,
            "decision_source": "strict_majority_exact_label_set",
            "provenance": "ai_panel_consensus",
            "gold_status": "not_human_gold",
        },
        {
            "task_number": 2,
            "task_id": second_task.event_id,
            "labels": [],
            "attributes": {},
            "evidence_spans": [],
            "confidence": 0.95,
            "ambiguity_flag": False,
            "no_material_event": True,
            "decision_source": "strict_majority_exact_label_set",
            "provenance": "ai_panel_consensus",
            "gold_status": "not_human_gold",
        },
    )
    panel_synthesis.write_jsonl(rows, canonical)
    policy = load_annotation_policy(ROOT / "configs" / "annotation.yaml")

    first = panel_synthesis.import_panel_release(
        store,
        canonical,
        policy,
        release_id="stage7-ai-panel-test",
    )
    second = panel_synthesis.import_panel_release(
        store,
        canonical,
        policy,
        release_id="stage7-ai-panel-test",
    )

    assert first == second
    assert first.evidence_kind == "ai_panel"
    assert first.stage_acceptance_passed is False
    assert sum(len(store.current_annotations(task.event_id)) for task in store.list_tasks()) == 2
    assert store.get_release("stage7-ai-panel-test") == first


@pytest.fixture(scope="module")
def ontology():
    return load_ontology(ROOT / "configs" / "ontology.yaml")


def _build_sources(tmp_path: Path, *, document_count: int = 2) -> tuple[Path, Path, Path]:
    sec_path = tmp_path / "sec.sqlite3"
    normalized_path = tmp_path / "normalized.sqlite3"
    knowledge_path = tmp_path / "knowledge.sqlite3"
    submissions_path = tmp_path / "submissions.json"
    submissions_path.write_text(json.dumps({"cik": "0000000001", "name": "Acme Corp"}))

    with sqlite3.connect(sec_path) as connection:
        connection.executescript(
            """
            CREATE TABLE sec_requests (
                request_id INTEGER PRIMARY KEY,
                request_url TEXT NOT NULL,
                local_path TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO sec_requests VALUES (1, ?, ?)",
            ("https://data.sec.gov/submissions/CIK0000000001.json", str(submissions_path)),
        )

    with sqlite3.connect(normalized_path) as connection:
        connection.executescript(
            """
            CREATE TABLE normalized_documents (
                normalization_id INTEGER PRIMARY KEY,
                source_document_id INTEGER NOT NULL,
                parser_version TEXT NOT NULL,
                local_path TEXT,
                success INTEGER NOT NULL
            );
            """
        )
        for index in range(1, document_count + 1):
            output_path = tmp_path / f"normalized-{index}.json"
            output_path.write_text(
                json.dumps(
                    {
                        "accession_number": f"0000000001-24-{index:06d}",
                        "document_id": f"sec_{index}_sec-html-v0.1",
                        "document_type": "8-K",
                        "filename": f"acme-{index}.htm",
                        "is_exhibit": False,
                        "language": "en",
                        "parent_document_id": None,
                        "parser_version": "sec-html-v0.1",
                        "parsing_quality": 1.0,
                        "sections": [
                            {
                                "heading": "Item 8.01 Other Events",
                                "is_boilerplate": False,
                                "is_table": False,
                                "section_id": "section_001",
                                "source_start": 0,
                                "source_end": 100,
                                "text": f"Acme announced material development {index}. Further detail follows.",
                            }
                        ],
                        "source_content_hash": "a" * 64,
                        "source_document_id": index,
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            connection.execute(
                "INSERT INTO normalized_documents VALUES (?, ?, 'sec-html-v0.1', ?, 1)",
                (index, index, str(output_path)),
            )

    with sqlite3.connect(knowledge_path) as connection:
        connection.executescript(
            """
            CREATE TABLE knowledge_records (
                record_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_published_at TEXT NOT NULL,
                tradable_at TEXT NOT NULL
            );
            """
        )
        for index in range(1, document_count + 1):
            published = f"2024-01-{index:02d}T21:00:00+00:00"
            payload = {
                "accession_number": f"0000000001-24-{index:06d}",
                "cik": "0000000001",
                "document_type": "8-K",
                "filename": f"acme-{index}.htm",
                "form": "8-K",
                "is_amendment": False,
                "normalization_id": index,
                "parser_version": "sec-html-v0.1",
                "source_document_id": index,
            }
            connection.execute(
                "INSERT INTO knowledge_records VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"knowledge-{index}",
                    "sec-cik:0000000001",
                    f"sec-normalized:{index}",
                    json.dumps(payload),
                    published,
                    f"2024-01-{index + 1:02d}T14:45:00+00:00",
                ),
            )
    return sec_path, normalized_path, knowledge_path


def test_build_calibration_tasks_is_deterministic_provenanced_and_unbiased(
    tmp_path: Path,
) -> None:
    sec_path, normalized_path, knowledge_path = _build_sources(tmp_path)
    first = build_calibration_tasks(
        sec_manifest_path=sec_path,
        normalization_manifest_path=normalized_path,
        knowledge_store_path=knowledge_path,
        expected_documents=2,
    )
    second = build_calibration_tasks(
        sec_manifest_path=sec_path,
        normalization_manifest_path=normalized_path,
        knowledge_store_path=knowledge_path,
        expected_documents=2,
    )

    assert first == second
    assert len(first) == 2
    assert all(task.company == "Acme Corp" for task in first)
    assert all(task.candidate_labels == () for task in first)
    assert all(task.source_published_at.tzinfo is not None for task in first)
    assert all(task.tradable_at >= task.source_published_at for task in first)
    for task in first:
        for span in task.candidate_evidence:
            assert task.relevant_section[span.start : span.end] == span.text
    assert first[0].prior_company_disclosure is None
    assert "development 1" in (first[1].prior_company_disclosure or "")


def test_build_calibration_tasks_requires_the_frozen_corpus_size(tmp_path: Path) -> None:
    sec_path, normalized_path, knowledge_path = _build_sources(tmp_path)
    with pytest.raises(ValueError, match="expected 100 calibration documents; found 2"):
        build_calibration_tasks(
            sec_manifest_path=sec_path,
            normalization_manifest_path=normalized_path,
            knowledge_store_path=knowledge_path,
            expected_documents=100,
        )


def test_prepare_calibration_is_idempotent(tmp_path: Path, ontology) -> None:
    sec_path, normalized_path, knowledge_path = _build_sources(tmp_path)
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    first = prepare_calibration(
        store,
        sec_manifest_path=sec_path,
        normalization_manifest_path=normalized_path,
        knowledge_store_path=knowledge_path,
        expected_documents=2,
    )
    second = prepare_calibration(
        store,
        sec_manifest_path=sec_path,
        normalization_manifest_path=normalized_path,
        knowledge_store_path=knowledge_path,
        expected_documents=2,
    )
    assert first.task_count == second.task_count == 2
    assert first.queue_hash == second.queue_hash
    assert len(store.list_tasks()) == 2


def test_prepare_and_status_commands_are_operational(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sec_path, normalized_path, knowledge_path = _build_sources(tmp_path)
    database = tmp_path / "annotations.sqlite"
    common = [
        "--database",
        str(database),
        "--ontology",
        str(ROOT / "configs" / "ontology.yaml"),
        "--policy",
        str(ROOT / "configs" / "annotation.yaml"),
    ]
    annotation_main(
        [
            "prepare-calibration",
            *common,
            "--sec-manifest",
            str(sec_path),
            "--normalization-manifest",
            str(normalized_path),
            "--knowledge-store",
            str(knowledge_path),
            "--expected-documents",
            "2",
        ]
    )
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["task_count"] == 2

    annotation_main(["status", *common, "--annotator-id", "human-a"])
    status = json.loads(capsys.readouterr().out)
    assert status == {
        "annotator_id": "human-a",
        "total": 2,
        "completed": 0,
        "remaining": 2,
    }


def _no_event_record(
    event_id: str,
    annotator_id: str,
    *,
    annotation_id: str,
    status: AdjudicationStatus = AdjudicationStatus.SUBMITTED,
) -> AnnotationRecord:
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id=event_id,
        annotator_id=annotator_id,
        ontology_version="0.1",
        labels=(),
        attributes={},
        evidence_spans=(),
        confidence=0.9,
        ambiguity_flag=False,
        no_material_event=True,
        created_at=datetime(2024, 2, 1, 12, 0, tzinfo=UTC),
        supersedes_annotation_id=None,
        adjudication_status=status,
    )


def test_calibration_agreement_reports_incomplete_pairs_and_unresolved_disagreement(
    tmp_path: Path, ontology
) -> None:
    sec_path, normalized_path, knowledge_path = _build_sources(tmp_path)
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    prepare_calibration(
        store,
        sec_manifest_path=sec_path,
        normalization_manifest_path=normalized_path,
        knowledge_store_path=knowledge_path,
        expected_documents=2,
    )
    event_one, event_two = (task.event_id for task in store.list_tasks())
    store.save_annotation(_no_event_record(event_one, "human-a", annotation_id="ann-a-1"))
    store.save_annotation(_no_event_record(event_one, "human-b", annotation_id="ann-b-1"))
    store.save_annotation(_no_event_record(event_two, "human-a", annotation_id="ann-a-2"))

    incomplete = calibration_agreement(store, "human-a", "human-b")
    assert incomplete.paired_count == 1
    assert incomplete.agreement_count == 1
    assert incomplete.incomplete_event_ids == (event_two,)
    assert incomplete.calibration_complete is False

    task = store.get_task(event_two)
    assert task is not None
    span = task.candidate_evidence[0]
    material = AnnotationRecord(
        annotation_id="ann-b-2",
        event_id=event_two,
        annotator_id="human-b",
        ontology_version="0.1",
        labels=("contracts.awarded",),
        attributes={
            "contracts.awarded": {
                "certainty": "confirmed",
                "status": "announced",
                "economic_direction": "positive",
                "source_reliability": "primary_filing",
                "counterparty": "Example customer",
                "binding_status": "binding",
            }
        },
        evidence_spans=(span,),
        confidence=0.8,
        ambiguity_flag=False,
        no_material_event=False,
        created_at=datetime(2024, 2, 1, 12, 1, tzinfo=UTC),
        supersedes_annotation_id=None,
        adjudication_status=AdjudicationStatus.SUBMITTED,
    )
    store.save_annotation(material)
    disagreement = calibration_agreement(store, "human-a", "human-b")
    assert disagreement.disagreement_event_ids == (event_two,)
    assert disagreement.unresolved_event_ids == (event_two,)
    assert disagreement.exact_agreement == pytest.approx(0.5)

    with pytest.raises(ValueError, match="distinct annotator IDs"):
        calibration_agreement(store, "human-a", "human-a")
