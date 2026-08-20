from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_ontology_v01_has_complete_supplied_leaf_guide() -> None:
    from financial_event_model.ontology import load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")

    assert ontology.version == "0.1"
    assert len(ontology.labels) == 25
    assert {label.valid_parent for label in ontology.labels} == {
        "earnings",
        "guidance",
        "contracts",
        "capital_allocation",
        "management",
        "corporate_action",
    }
    assert all(label.definition for label in ontology.labels)
    assert all(label.inclusion_criteria for label in ontology.labels)
    assert all(label.exclusion_criteria for label in ontology.labels)
    assert all(label.positive_example for label in ontology.labels)
    assert all(label.difficult_counterexample for label in ontology.labels)
    assert all(label.required_attributes for label in ontology.labels)


def test_ontology_v01_contains_the_exact_supplied_labels() -> None:
    from financial_event_model.ontology import load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")

    assert {label.event_type for label in ontology.labels} == {
        "earnings.revenue_beat",
        "earnings.revenue_miss",
        "earnings.eps_beat",
        "earnings.eps_miss",
        "earnings.margin_change",
        "guidance.raised",
        "guidance.lowered",
        "guidance.initiated",
        "guidance.reaffirmed",
        "guidance.withdrawn",
        "contracts.awarded",
        "contracts.expanded",
        "contracts.lost",
        "contracts.cancelled",
        "capital_allocation.buyback",
        "capital_allocation.dividend_change",
        "capital_allocation.debt_issuance",
        "capital_allocation.equity_issuance",
        "management.ceo_departure",
        "management.ceo_appointment",
        "management.cfo_departure",
        "management.cfo_appointment",
        "corporate_action.acquisition",
        "corporate_action.divestiture",
        "corporate_action.restructuring",
    }


def test_event_attributes_are_validated_against_the_selected_leaf() -> None:
    from financial_event_model.ontology import load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    required = {
        "certainty": "confirmed",
        "status": "announced",
        "economic_direction": "positive",
        "source_reliability": "primary_filing",
        "counterparty": "Customer A",
        "binding_status": "binding",
    }

    event = ontology.validate_event(
        "contracts.awarded",
        required
        | {
            "effective_date": "2026-09-01",
            "value": 120_000_000,
            "government_customer": False,
            "conditions_remaining": ["regulatory approval"],
        },
    )

    assert event.event_type == "contracts.awarded"
    with pytest.raises(ValueError, match="unknown ontology label"):
        ontology.validate_event("contracts.proposed", required)
    with pytest.raises(ValueError, match="missing required attributes"):
        ontology.validate_event("contracts.awarded", {"certainty": "confirmed"})
    with pytest.raises(ValueError, match="unknown attributes"):
        ontology.validate_event("contracts.awarded", required | {"sentiment": "good"})
    with pytest.raises(ValueError, match="invalid enum"):
        ontology.validate_event(
            "contracts.awarded",
            required | {"certainty": "definite"},
        )
    with pytest.raises(ValueError, match="invalid date"):
        ontology.validate_event(
            "contracts.awarded",
            required | {"effective_date": "2026-02-30"},
        )
    with pytest.raises(ValueError, match="invalid date"):
        ontology.validate_event(
            "contracts.awarded",
            required
            | {"effective_date": datetime(2026, 9, 1, tzinfo=timezone.utc)},
        )


def test_event_attributes_reject_non_finite_financial_numbers() -> None:
    from financial_event_model.ontology import load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")

    with pytest.raises(ValueError, match="invalid number"):
        ontology.validate_event(
            "contracts.awarded",
            {
                "certainty": "confirmed",
                "status": "announced",
                "economic_direction": "positive",
                "source_reliability": "primary_filing",
                "counterparty": "Customer A",
                "binding_status": "binding",
                "value": float("nan"),
            },
        )


def test_ontology_rejects_broken_label_references() -> None:
    from financial_event_model.ontology import OntologyDefinition, load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    payload = ontology.model_dump(mode="json")
    payload["labels"][0]["incompatible_labels"] = ["earnings.not_a_label"]

    with pytest.raises(ValueError, match="unknown incompatible labels"):
        OntologyDefinition.model_validate(payload)


def test_ontology_contract_rejects_version_or_leaf_drift() -> None:
    from financial_event_model.ontology import OntologyDefinition, load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    wrong_version = ontology.model_dump(mode="json")
    wrong_version["version"] = "0.2"
    changed_leaf = ontology.model_dump(mode="json")
    margin = next(
        label
        for label in changed_leaf["labels"]
        if label["event_type"] == "earnings.margin_change"
    )
    margin["event_type"] = "earnings.margin_changed"

    with pytest.raises(ValueError, match="version"):
        OntologyDefinition.model_validate(wrong_version)
    with pytest.raises(ValueError, match="leaf labels"):
        OntologyDefinition.model_validate(changed_leaf)


def _agreement_fixture():
    from financial_event_model.ontology import (
        AnnotationDecision,
        DisagreementCategory,
        DisagreementResolution,
    )

    decisions = []
    resolutions = []
    categories = tuple(DisagreementCategory)
    for index in range(100):
        event_id = f"event_{index:03d}"
        first_type = "earnings.revenue_beat"
        if index < 90:
            second_type = first_type
        elif index < 95:
            second_type = "earnings.eps_beat"
        else:
            second_type = "guidance.raised"
        decisions.extend(
            [
                AnnotationDecision(
                    event_id=event_id,
                    annotator_id="annotator_a",
                    event_type=first_type,
                ),
                AnnotationDecision(
                    event_id=event_id,
                    annotator_id="annotator_b",
                    event_type=second_type,
                ),
            ]
        )
        if first_type != second_type:
            resolutions.append(
                DisagreementResolution(
                    event_id=event_id,
                    category=categories[index % len(categories)],
                )
            )
    return tuple(decisions), tuple(resolutions)


def test_one_hundred_item_fixture_audits_agreement_without_claiming_human_proof() -> None:
    from financial_event_model.ontology import audit_annotations, load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    decisions, resolutions = _agreement_fixture()

    report = audit_annotations(
        decisions,
        resolutions,
        ontology,
        evidence_kind="fixture",
    )

    assert report.item_count == 100
    assert report.leaf_agreement == pytest.approx(0.90)
    assert report.family_agreement == pytest.approx(0.95)
    assert report.disagreement_count == 10
    assert sum(report.category_counts.values()) == 10
    assert report.unexplained_event_ids == ()
    assert report.contract_checks_passed is True
    assert report.stage_acceptance_passed is False


def test_human_acceptance_requires_every_disagreement_to_be_categorized() -> None:
    from financial_event_model.ontology import audit_annotations, load_ontology

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    decisions, resolutions = _agreement_fixture()

    complete = audit_annotations(
        decisions,
        resolutions,
        ontology,
        evidence_kind="human",
    )
    incomplete = audit_annotations(
        decisions,
        resolutions[:-1],
        ontology,
        evidence_kind="human",
    )

    assert complete.stage_acceptance_passed is True
    assert incomplete.unexplained_event_ids == ("event_099",)
    assert incomplete.contract_checks_passed is False
    assert incomplete.stage_acceptance_passed is False


def test_agreement_audit_rejects_non_independent_pairs() -> None:
    from financial_event_model.ontology import (
        AnnotationDecision,
        audit_annotations,
        load_ontology,
    )

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    decisions = (
        AnnotationDecision(
            event_id="event_001",
            annotator_id="same_person",
            event_type="earnings.revenue_beat",
        ),
        AnnotationDecision(
            event_id="event_001",
            annotator_id="same_person",
            event_type="earnings.revenue_miss",
        ),
    )

    with pytest.raises(ValueError, match="distinct annotators"):
        audit_annotations(decisions, (), ontology, evidence_kind="fixture")


def test_fixture_contract_does_not_pass_below_the_family_threshold() -> None:
    from financial_event_model.ontology import (
        AnnotationDecision,
        DisagreementCategory,
        DisagreementResolution,
        audit_annotations,
        load_ontology,
    )

    ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
    decisions = []
    resolutions = []
    for index in range(100):
        event_id = f"event_{index:03d}"
        decisions.extend(
            [
                AnnotationDecision(
                    event_id=event_id,
                    annotator_id="annotator_a",
                    event_type="earnings.revenue_beat",
                ),
                AnnotationDecision(
                    event_id=event_id,
                    annotator_id="annotator_b",
                    event_type="guidance.raised",
                ),
            ]
        )
        resolutions.append(
            DisagreementResolution(
                event_id=event_id,
                category=DisagreementCategory.UNCLEAR_DEFINITION,
            )
        )

    report = audit_annotations(
        tuple(decisions),
        tuple(resolutions),
        ontology,
        evidence_kind="fixture",
    )

    assert report.family_agreement == 0
    assert report.contract_checks_passed is False
