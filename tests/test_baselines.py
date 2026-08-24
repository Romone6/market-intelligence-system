from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]
UTC = timezone.utc


def test_non_neural_baselines_and_metrics_have_a_deterministic_floor() -> None:
    from financial_event_model.baselines import (
        AttributeFrequencyBaseline,
        BaselineExample,
        FilingTypeFrequencyBaseline,
        GlobalFrequencyBaseline,
        LexicalNaiveBayesBaseline,
        Prediction,
        evaluate_attribute_baseline,
        evaluate_baselines,
        score_attributes,
        score_predictions,
    )

    buyback = ("capital_allocation.buyback",)
    train = (
        BaselineExample("n1", "administrative filing only", "8-K", ()),
        BaselineExample("n2", "routine administrative update", "8-K", ()),
        BaselineExample("n3", "no qualifying event", "10-Q", ()),
        BaselineExample("b1", "board authorized share repurchase", "EX-99.1", buyback),
        BaselineExample("b2", "new buyback repurchase program", "EX-99.1", buyback),
    )
    no_event = BaselineExample("q1", "administrative filing", "8-K", ())
    material = BaselineExample(
        "q2",
        "board authorized a new share repurchase program",
        "EX-99.1",
        buyback,
        candidate_spans=((0, 16),),
        evidence_spans=((0, 16),),
    )

    global_model = GlobalFrequencyBaseline.fit(train)
    filing_model = FilingTypeFrequencyBaseline.fit(train)
    lexical_model = LexicalNaiveBayesBaseline.fit(train, alpha=1.0)

    assert global_model.predict(material).labels == ()
    assert filing_model.predict(material).labels == buyback
    assert lexical_model.predict(material).labels == buyback
    assert lexical_model.predict(no_event).labels == ()

    metrics = score_predictions(
        (no_event, material),
        (
            Prediction(labels=(), material_probability=0.1, evidence_spans=()),
            Prediction(
                labels=buyback,
                material_probability=0.9,
                evidence_spans=((0, 16),),
            ),
        ),
    )
    assert metrics.exact_set_accuracy == 1.0
    assert metrics.micro_f1 == 1.0
    assert metrics.brier_score == pytest.approx(0.01)
    assert metrics.expected_calibration_error_5_bins == pytest.approx(0.1)
    assert metrics.character_overlap_f1 == 1.0

    report = evaluate_baselines(train, (no_event, material), alpha=1.0)
    assert set(report) == {
        "global_frequency",
        "filing_type_frequency",
        "lexical_naive_bayes",
    }
    assert report["global_frequency"]["exact_set_accuracy"] == 0.5
    assert report["filing_type_frequency"]["character_overlap_f1"] == 1.0

    attribute_train = (
        BaselineExample(
            "a1",
            "first buyback",
            "8-K",
            buyback,
            attributes={
                buyback[0]: {
                    "certainty": "confirmed",
                    "status": "announced",
                    "affected_financial_channels": ["cash", "shares_outstanding"],
                }
            },
        ),
        BaselineExample(
            "a2",
            "second buyback",
            "8-K",
            buyback,
            attributes={
                buyback[0]: {
                    "certainty": "confirmed",
                    "status": "announced",
                    "affected_financial_channels": ["cash", "shares_outstanding"],
                }
            },
        ),
        BaselineExample(
            "a3",
            "completed buyback",
            "10-Q",
            buyback,
            attributes={
                buyback[0]: {
                    "certainty": "confirmed",
                    "status": "completed",
                    "affected_financial_channels": ["cash"],
                }
            },
        ),
    )
    attribute_eval = BaselineExample(
        "a4",
        "another buyback",
        "8-K",
        buyback,
        attributes={
            buyback[0]: {
                "certainty": "confirmed",
                "status": "announced",
                "affected_financial_channels": ["cash", "shares_outstanding"],
            }
        },
    )
    attribute_model = AttributeFrequencyBaseline.fit(attribute_train)
    predicted_attributes = attribute_model.predict_for_labels(buyback)
    assert predicted_attributes == attribute_eval.attributes
    assert score_attributes((attribute_eval,), (predicted_attributes,)).attribute_cell_f1 == 1.0
    assert evaluate_attribute_baseline(attribute_train, (attribute_eval,)) == {
        "material_record_exact_accuracy": 1.0,
        "attribute_cell_precision": 1.0,
        "attribute_cell_recall": 1.0,
        "attribute_cell_f1": 1.0,
    }


def test_stage8_runner_freezes_config_and_writes_a_non_human_report(tmp_path: Path) -> None:
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
    from financial_event_model.baselines import run_stage8
    from financial_event_model.experiments import ExperimentStore
    from financial_event_model.ontology import load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    policy = load_annotation_policy(ROOT / "configs" / "annotation.yaml")
    store = AnnotationStore(tmp_path / "annotations.sqlite", ontology)
    tasks = []
    records = []
    for index in range(4):
        material = index >= 2
        section = (
            "The board authorized a new share repurchase program."
            if material
            else "The filing contains an administrative update only."
        )
        span = EvidenceSpan(start=0, end=len(section), text=section)
        task = AnnotationTask(
            event_id=f"event-{index}",
            company=f"Company {index}",
            entity_id=f"entity-{index}",
            related_event_group=f"group-{index}",
            source_published_at=datetime(2024, 1, index + 1, tzinfo=UTC),
            tradable_at=datetime(2024, 1, index + 1, tzinfo=UTC) + timedelta(minutes=1),
            filing_type="EX-99.1" if material else "8-K",
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
        release_id="fixture-ai-panel",
        evidence_kind="ai_panel",
    )
    store.freeze_release(release)

    config = yaml.safe_load((ROOT / "configs" / "stage8_baselines.yaml").read_text())
    config["dataset"].update(
        {
            "release_id": release.release_id,
            "content_hash": release.content_hash,
            "train_items": len(release.train_event_ids),
            "evaluation_items": len(release.eval_event_ids),
        }
    )
    config_path = tmp_path / "stage8.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    report_path = tmp_path / "report.json"
    experiment_path = tmp_path / "experiments.sqlite"

    report = run_stage8(
        database=store.path,
        ontology_path=ROOT / "configs" / "ontology.yaml",
        config_path=config_path,
        report_path=report_path,
        experiment_database=experiment_path,
        run_id="stage8-fixture",
    )

    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert report["schema_version"] == "stage8-baselines-v0.2"
    assert report["model_version"] == "stage8-baselines-v0.2"
    assert set(report["baselines"]) == {
        "global_frequency",
        "filing_type_frequency",
        "lexical_naive_bayes",
    }
    assert set(report["attributes"]) == {"label_conditional_frequency"}
    assert report["dataset"]["evidence_kind"] == "ai_panel"
    assert report["outcomes"]["status"] == "unavailable"
    assert report["evaluation_tuning_performed"] is False
    assert ExperimentStore(experiment_path).get("stage8-fixture") is not None
