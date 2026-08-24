from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
import pytest


ROOT = Path(__file__).parents[1]
UTC = timezone.utc


def test_character_evidence_span_maps_to_exact_primary_sequence_tokens() -> None:
    from financial_event_model.stage9_tokenization import character_span_to_token_span

    primary = "Filing type: 8-K\n\nThe board authorized a buyback."
    evidence = "The board authorized a buyback."
    start = primary.index(evidence)
    offsets = [(0, 0), (0, 6), (7, 11), (13, 16), (18, 21), (22, 27), (28, 38), (39, 40), (41, 48), (48, 49), (0, 0)]
    sequence_ids = [None, 0, 0, 0, 0, 0, 0, 0, 0, 0, None]

    token_start, token_end = character_span_to_token_span(
        primary=primary,
        offsets=offsets,
        sequence_ids=sequence_ids,
        char_start=start,
        char_end=start + len(evidence),
        evidence_text=evidence,
    )

    assert (token_start, token_end) == (4, 10)


def test_character_evidence_span_fails_closed_when_truncated() -> None:
    from financial_event_model.stage9_tokenization import character_span_to_token_span

    primary = "prefix exact evidence"
    with pytest.raises(ValueError, match="not exactly represented"):
        character_span_to_token_span(
            primary=primary,
            offsets=[(0, 0), (0, 6), (0, 0)],
            sequence_ids=[None, 0, None],
            char_start=7,
            char_end=len(primary),
            evidence_text="exact evidence",
        )


def test_character_evidence_span_allows_tokenizer_owned_leading_whitespace() -> None:
    from financial_event_model.stage9_tokenization import character_span_to_token_span

    primary = "prefix exact evidence"
    token_start, token_end = character_span_to_token_span(
        primary=primary,
        offsets=[(0, 0), (0, 6), (6, 12), (13, 21), (0, 0)],
        sequence_ids=[None, 0, 0, 0, None],
        char_start=7,
        char_end=len(primary),
        evidence_text="exact evidence",
    )

    assert (token_start, token_end) == (2, 4)


def test_stage9_package_uses_only_release_train_records_and_preserves_groups(
    tmp_path: Path,
) -> None:
    from financial_event_model.annotation import (
        AdjudicationStatus,
        AnnotationRecord,
        AnnotationRound,
        AnnotationStore,
        AnnotationTask,
        EvidenceSpan,
        build_dataset_release,
        load_annotation_policy,
    )
    from financial_event_model.ontology import load_ontology
    from financial_event_model.stage9_data import run_stage9_data_prep

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    policy = load_annotation_policy(ROOT / "configs" / "annotation.yaml")
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    tasks = []
    records = []
    for index in range(8):
        material = index % 2 == 0
        section = (
            "The board authorized a new share repurchase program."
            if material
            else "The filing contains an administrative update only."
        )
        section += " The company’s disclosure is included."
        span = EvidenceSpan(start=0, end=len(section), text=section)
        entity_id = "shared-entity" if index in {0, 1} else f"entity-{index}"
        related_group = "shared-event" if index in {2, 3} else f"group-{index}"
        task = AnnotationTask(
            event_id=f"event-{index}",
            company=f"Company {index}",
            entity_id=entity_id,
            related_event_group=related_group,
            source_published_at=datetime(2024, 1, index + 1, tzinfo=UTC),
            tradable_at=datetime(2024, 1, index + 1, tzinfo=UTC) + timedelta(minutes=1),
            filing_type="8-K",
            relevant_section=section,
            candidate_evidence=(span,),
            prior_company_disclosure=None,
            annotation_round=AnnotationRound.CALIBRATION,
        )
        labels = ("capital_allocation.buyback",) if material else ()
        record = AnnotationRecord(
            annotation_id=f"annotation-{index}",
            event_id=task.event_id,
            annotator_id="ai-panel-v1",
            ontology_version="0.1",
            labels=labels,
            attributes=(
                {
                    labels[0]: {
                        "certainty": "confirmed",
                        "status": "announced",
                        "economic_direction": "neutral",
                        "source_reliability": "primary_filing",
                    }
                }
                if material
                else {}
            ),
            evidence_spans=(span,) if material else (),
            confidence=0.9,
            ambiguity_flag=False,
            no_material_event=not material,
            created_at=datetime(2024, 2, 1, 12, index, tzinfo=UTC),
            supersedes_annotation_id=None,
            adjudication_status=AdjudicationStatus.SUBMITTED,
        )
        tasks.append(task)
        records.append(record)
    store.add_tasks(tuple(tasks))
    for record in records:
        store.save_annotation(record)
    release = build_dataset_release(
        tuple(tasks),
        tuple(records),
        ontology,
        policy,
        release_id="stage9-fixture",
        evidence_kind="ai_panel",
    )
    store.freeze_release(release)

    config = yaml.safe_load((ROOT / "configs" / "stage9_data.yaml").read_text())
    config["dataset"].update(
        {
            "release_id": release.release_id,
            "content_hash": release.content_hash,
            "development_items": len(release.train_event_ids),
            "sealed_evaluation_items": len(release.eval_event_ids),
        }
    )
    config_path = tmp_path / "stage9.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    output_dir = tmp_path / "package"

    manifest = run_stage9_data_prep(
        database=store.path,
        ontology_path=ROOT / "configs" / "ontology.yaml",
        config_path=config_path,
        output_dir=output_dir,
    )

    fit_rows = [json.loads(line) for line in (output_dir / "train.jsonl").read_text().splitlines()]
    validation_rows = [
        json.loads(line) for line in (output_dir / "validation.jsonl").read_text().splitlines()
    ]
    packaged_ids = {row["event_id"] for row in fit_rows + validation_rows}
    assert packaged_ids == set(release.train_event_ids)
    assert packaged_ids.isdisjoint(release.eval_event_ids)
    assert manifest["sealed_evaluation"]["items"] == len(release.eval_event_ids)
    assert manifest["sealed_evaluation"]["labels_read"] is False
    assert manifest["leakage"]["passed"] is True
    assert all("company" not in row["input"] for row in fit_rows + validation_rows)
    assert all("entity_id" not in row["input"] for row in fit_rows + validation_rows)
    assert json.loads((output_dir / "manifest.json").read_text()) == manifest
