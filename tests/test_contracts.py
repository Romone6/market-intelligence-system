from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_raw_document_requires_aware_provenance_timestamps() -> None:
    from financial_event_model.contracts import RawDocument

    common = {
        "document_id": "sec_0001",
        "source": "sec",
        "source_url": "https://www.sec.gov/example",
        "source_published_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
        "received_at": datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
        "content_hash": "a" * 64,
        "raw_content_path": "data/raw/sec_0001.html",
        "source_metadata": {"accession_number": "0001"},
    }

    with pytest.raises(ValidationError):
        RawDocument(
            **common,
            first_observed_at=datetime(2024, 1, 2, 11, 59),
        )

    document = RawDocument(
        **common,
        first_observed_at=datetime(2024, 1, 2, 11, 59, tzinfo=timezone.utc),
    )
    assert document.document_id == "sec_0001"


def test_financial_event_and_prediction_preserve_versioned_outputs() -> None:
    from financial_event_model.contracts import EventPrediction, FinancialEvent

    event = FinancialEvent(
        event_id="event_0001",
        document_id="sec_0001",
        issuer_id="entity_0001",
        event_type="contracts.awarded",
        attributes={"value": 10_000_000, "currency": "USD"},
        evidence_spans=[{"section_id": "section_001", "start": 12, "end": 48}],
        event_effective_at=None,
        first_observed_at=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
        tradable_at=datetime(2024, 1, 3, 14, 30, tzinfo=timezone.utc),
        ontology_version="0.1",
        label_confidence=0.9,
    )
    assert event.label_confidence == 0.9

    with pytest.raises(ValidationError):
        EventPrediction(
            event_id=event.event_id,
            model_version="",
            embedding=[],
            novelty=0.5,
            materiality=0.6,
            analogue_ids=[],
            outcome_distributions={},
            epistemic_uncertainty=0.2,
            aleatoric_uncertainty=0.3,
            ood_score=0.1,
            abstain=True,
        )

