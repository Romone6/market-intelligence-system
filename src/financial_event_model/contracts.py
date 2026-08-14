"""Versioned data contracts shared by every pipeline stage."""

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RawDocument(Contract):
    document_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    source_published_at: AwareDatetime | None
    first_observed_at: AwareDatetime
    received_at: AwareDatetime
    content_hash: str = Field(min_length=1)
    raw_content_path: str = Field(min_length=1)
    source_metadata: dict[str, Any]


class FinancialEvent(Contract):
    event_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    issuer_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    attributes: dict[str, Any]
    evidence_spans: list[dict[str, Any]]
    event_effective_at: AwareDatetime | None
    first_observed_at: AwareDatetime
    tradable_at: AwareDatetime
    ontology_version: str = Field(min_length=1)
    label_confidence: float = Field(ge=0.0, le=1.0)


class EventPrediction(Contract):
    event_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    embedding: list[float]
    novelty: float
    materiality: float
    analogue_ids: list[str]
    outcome_distributions: dict[str, Any]
    epistemic_uncertainty: float
    aleatoric_uncertainty: float
    ood_score: float
    abstain: bool

