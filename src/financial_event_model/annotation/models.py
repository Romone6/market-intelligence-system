"""Strict contracts for annotation tasks, records, and Stage 7 policy."""

from __future__ import annotations

from enum import StrEnum, unique
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import AwareDatetime, Field, model_validator

from financial_event_model.contracts import Contract
from financial_event_model.ontology import OntologyDefinition


@unique
class AnnotationRound(StrEnum):
    CALIBRATION = "calibration"
    GOLD = "gold"
    EXPANSION = "expansion"


@unique
class AdjudicationStatus(StrEnum):
    SUBMITTED = "submitted"
    NEEDS_ADJUDICATION = "needs_adjudication"
    ADJUDICATED = "adjudicated"
    EXCLUDED = "excluded"


class EvidenceSpan(Contract):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("evidence span end must be after start")
        return self


class AnnotationTask(Contract):
    event_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    related_event_group: str | None = None
    source_published_at: AwareDatetime
    tradable_at: AwareDatetime
    filing_type: str = Field(min_length=1)
    relevant_section: str = Field(min_length=1)
    candidate_evidence: tuple[EvidenceSpan, ...]
    prior_company_disclosure: str | None
    annotation_round: AnnotationRound
    candidate_labels: tuple[str, ...] = ()
    priority_reason: str | None = None

    @model_validator(mode="after")
    def validate_task(self) -> Self:
        if self.tradable_at < self.source_published_at:
            raise ValueError("tradable_at must not precede source_published_at")
        if len(set(self.candidate_labels)) != len(self.candidate_labels):
            raise ValueError("candidate labels must be unique")
        for span in self.candidate_evidence:
            if span.end > len(self.relevant_section):
                raise ValueError("candidate evidence exceeds relevant section")
            if self.relevant_section[span.start : span.end] != span.text:
                raise ValueError("candidate evidence text does not match relevant section")
        return self


class AnnotationRecord(Contract):
    annotation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    annotator_id: str = Field(min_length=1)
    ontology_version: str = Field(min_length=1)
    labels: tuple[str, ...]
    attributes: dict[str, dict[str, object]]
    evidence_spans: tuple[EvidenceSpan, ...]
    confidence: float = Field(ge=0, le=1)
    ambiguity_flag: bool
    no_material_event: bool
    created_at: AwareDatetime
    supersedes_annotation_id: str | None
    adjudication_status: AdjudicationStatus

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.supersedes_annotation_id == self.annotation_id:
            raise ValueError("an annotation cannot supersede itself")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("annotation labels must be unique")
        if self.no_material_event:
            if self.labels or self.attributes or self.evidence_spans:
                raise ValueError(
                    "no material event annotations cannot include labels, attributes, or evidence"
                )
        elif not self.labels or not self.evidence_spans:
            raise ValueError("material annotation requires labels and evidence spans")
        if set(self.attributes) != set(self.labels):
            raise ValueError("annotation attributes must be keyed by every selected label")
        return self

    def validate_against(
        self,
        ontology: OntologyDefinition,
        task: AnnotationTask,
    ) -> None:
        if self.event_id != task.event_id:
            raise ValueError("annotation event_id does not match task")
        if self.ontology_version != ontology.version:
            raise ValueError("annotation ontology_version does not match ontology")
        selected = set(self.labels)
        for label_name in self.labels:
            label = ontology.label(label_name)
            conflicts = selected.intersection(label.incompatible_labels)
            if conflicts:
                raise ValueError(
                    f"incompatible labels selected for {label_name}: {sorted(conflicts)}"
                )
            ontology.validate_event(label_name, self.attributes[label_name])
        for span in self.evidence_spans:
            if span.end > len(task.relevant_section):
                raise ValueError("annotation evidence exceeds relevant section")
            if task.relevant_section[span.start : span.end] != span.text:
                raise ValueError("annotation evidence text does not match relevant section")


class AnnotationRoundPolicy(Contract):
    calibration_documents: int = Field(ge=1)
    gold_minimum_events: int = Field(ge=1)
    gold_maximum_events: int = Field(ge=1)
    minimum_double_label_fraction: float = Field(ge=0, le=1)
    target_double_label_fraction: float = Field(ge=0, le=1)
    expansion_minimum_events: int = Field(ge=1)
    expansion_maximum_events: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.gold_minimum_events > self.gold_maximum_events:
            raise ValueError("gold event range is inverted")
        if self.minimum_double_label_fraction > self.target_double_label_fraction:
            raise ValueError("double-label fractions are inverted")
        if self.expansion_minimum_events > self.expansion_maximum_events:
            raise ValueError("expansion event range is inverted")
        return self


class AnnotationPolicy(Contract):
    version: Literal["0.1"]
    host: Literal["127.0.0.1"]
    port: int = Field(ge=1024, le=65535)
    max_request_bytes: int = Field(ge=1024)
    evaluation_fraction: float = Field(gt=0, lt=1)
    split_seed: str = Field(min_length=1)
    rare_label_threshold: int = Field(ge=1)
    rounds: AnnotationRoundPolicy


def load_annotation_policy(path: str | Path) -> AnnotationPolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("annotation policy YAML must contain a mapping")
    return AnnotationPolicy.model_validate(payload)
