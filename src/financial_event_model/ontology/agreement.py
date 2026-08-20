"""Agreement audit for independently produced ontology decisions."""

from collections import defaultdict
from typing import Literal

from pydantic import Field

from financial_event_model.contracts import Contract

from .models import DisagreementCategory, OntologyDefinition


class AnnotationDecision(Contract):
    event_id: str = Field(min_length=1)
    annotator_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)


class DisagreementResolution(Contract):
    event_id: str = Field(min_length=1)
    category: DisagreementCategory


class AgreementReport(Contract):
    evidence_kind: Literal["fixture", "human"]
    item_count: int = Field(ge=0)
    leaf_agreement: float = Field(ge=0, le=1)
    family_agreement: float = Field(ge=0, le=1)
    disagreement_count: int = Field(ge=0)
    category_counts: dict[str, int]
    unexplained_event_ids: tuple[str, ...]
    contract_checks_passed: bool
    stage_acceptance_passed: bool


def audit_annotations(
    decisions: tuple[AnnotationDecision, ...],
    resolutions: tuple[DisagreementResolution, ...],
    ontology: OntologyDefinition,
    *,
    evidence_kind: Literal["fixture", "human"],
) -> AgreementReport:
    if evidence_kind not in {"fixture", "human"}:
        raise ValueError("evidence_kind must be fixture or human")

    grouped: dict[str, list[AnnotationDecision]] = defaultdict(list)
    for decision in decisions:
        ontology.label(decision.event_type)
        grouped[decision.event_id].append(decision)
    if not grouped:
        raise ValueError("at least one annotated event is required")

    resolution_by_event: dict[str, DisagreementResolution] = {}
    for resolution in resolutions:
        if resolution.event_id in resolution_by_event:
            raise ValueError(f"duplicate resolution for {resolution.event_id}")
        if resolution.event_id not in grouped:
            raise ValueError(f"resolution has no annotation pair: {resolution.event_id}")
        resolution_by_event[resolution.event_id] = resolution

    leaf_matches = 0
    family_matches = 0
    disagreements: list[str] = []
    category_counts = {category.value: 0 for category in DisagreementCategory}
    for event_id in sorted(grouped):
        pair = grouped[event_id]
        if len(pair) != 2:
            raise ValueError(f"{event_id} must have exactly two decisions")
        if pair[0].annotator_id == pair[1].annotator_id:
            raise ValueError(f"{event_id} must have two distinct annotators")
        if pair[0].event_type == pair[1].event_type:
            leaf_matches += 1
            family_matches += 1
            if event_id in resolution_by_event:
                raise ValueError(f"agreeing event has a resolution: {event_id}")
            continue
        disagreements.append(event_id)
        if ontology.family_for(pair[0].event_type) == ontology.family_for(
            pair[1].event_type
        ):
            family_matches += 1
        resolution = resolution_by_event.get(event_id)
        if resolution is not None:
            category_counts[resolution.category.value] += 1

    unexplained = tuple(
        event_id for event_id in disagreements if event_id not in resolution_by_event
    )
    item_count = len(grouped)
    family_agreement = family_matches / item_count
    contract_passed = (
        item_count >= ontology.acceptance.sample_size
        and family_agreement >= ontology.acceptance.minimum_family_agreement
        and not unexplained
    )
    return AgreementReport(
        evidence_kind=evidence_kind,
        item_count=item_count,
        leaf_agreement=leaf_matches / item_count,
        family_agreement=family_agreement,
        disagreement_count=len(disagreements),
        category_counts=category_counts,
        unexplained_event_ids=unexplained,
        contract_checks_passed=contract_passed,
        stage_acceptance_passed=(
            evidence_kind == "human"
            and contract_passed
            and family_agreement >= ontology.acceptance.minimum_family_agreement
        ),
    )
