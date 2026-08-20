"""Strict contracts for ontology v0.1 and its annotation guide."""

from __future__ import annotations

from datetime import date
from enum import StrEnum, unique
from math import isfinite
from typing import Literal, Self

from pydantic import Field, model_validator

from financial_event_model.contracts import Contract


EXPECTED_SHARED_ATTRIBUTES = {
    "certainty",
    "status",
    "effective_date",
    "economic_direction",
    "materiality",
    "novelty",
    "time_horizon",
    "affected_financial_channels",
    "conditions_remaining",
    "source_reliability",
}

EXPECTED_CONTRACT_ATTRIBUTES = {
    "counterparty",
    "value",
    "currency",
    "duration",
    "government_customer",
    "binding_status",
    "revenue_start",
    "renewal_option",
    "percentage_of_trailing_revenue",
}

EXPECTED_LEAF_LABELS = {
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


@unique
class DisagreementCategory(StrEnum):
    AMBIGUOUS_DOCUMENT = "ambiguous_document"
    MISSING_ONTOLOGY_CATEGORY = "missing_ontology_category"
    UNCLEAR_DEFINITION = "unclear_definition"
    ANNOTATION_ERROR = "annotation_error"
    MULTIPLE_VALID_EVENTS = "multiple_valid_events"


class AcceptancePolicy(Contract):
    sample_size: int = Field(ge=1)
    minimum_family_agreement: float = Field(ge=0, le=1)


class AttributeDefinition(Contract):
    kind: Literal["string", "number", "boolean", "date", "enum", "string_list"]
    description: str = Field(min_length=1)
    allowed_values: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_enum_values(self) -> Self:
        if self.kind == "enum" and not self.allowed_values:
            raise ValueError("enum attributes require allowed_values")
        if self.kind != "enum" and self.allowed_values:
            raise ValueError("only enum attributes may define allowed_values")
        if len(set(self.allowed_values)) != len(self.allowed_values):
            raise ValueError("attribute allowed_values must be unique")
        return self


class LabelDefinition(Contract):
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    valid_parent: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    definition: str = Field(min_length=1)
    inclusion_criteria: tuple[str, ...] = Field(min_length=1)
    exclusion_criteria: tuple[str, ...] = Field(min_length=1)
    positive_example: str = Field(min_length=1)
    difficult_counterexample: str = Field(min_length=1)
    required_attributes: tuple[str, ...] = Field(min_length=1)
    incompatible_labels: tuple[str, ...]


class ValidatedEvent(Contract):
    event_type: str
    attributes: dict[str, object]


class OntologyDefinition(Contract):
    version: Literal["0.1"]
    acceptance: AcceptancePolicy
    disagreement_categories: tuple[DisagreementCategory, ...]
    shared_attributes: dict[str, AttributeDefinition]
    family_attributes: dict[str, dict[str, AttributeDefinition]]
    labels: tuple[LabelDefinition, ...] = Field(min_length=15, max_length=25)

    @model_validator(mode="after")
    def validate_guide(self) -> Self:
        if set(self.shared_attributes) != EXPECTED_SHARED_ATTRIBUTES:
            raise ValueError("shared attributes do not match ontology v0.1")
        if set(self.family_attributes) != {"contracts"}:
            raise ValueError("only contracts may define v0.1 family attributes")
        if set(self.family_attributes["contracts"]) != EXPECTED_CONTRACT_ATTRIBUTES:
            raise ValueError("contract attributes do not match ontology v0.1")
        if set(self.disagreement_categories) != set(DisagreementCategory):
            raise ValueError("disagreement categories do not match ontology v0.1")

        by_type = {label.event_type: label for label in self.labels}
        if len(by_type) != len(self.labels):
            raise ValueError("event_type values must be unique")
        if set(by_type) != EXPECTED_LEAF_LABELS:
            raise ValueError("leaf labels do not match ontology v0.1")
        for label in self.labels:
            if label.event_type.split(".", 1)[0] != label.valid_parent:
                raise ValueError(f"invalid parent for {label.event_type}")
            allowed = set(self.shared_attributes) | set(
                self.family_attributes.get(label.valid_parent, {})
            )
            unknown_required = set(label.required_attributes) - allowed
            if unknown_required:
                raise ValueError(
                    f"unknown required attributes for {label.event_type}: "
                    f"{sorted(unknown_required)}"
                )
            unknown_incompatible = set(label.incompatible_labels) - set(by_type)
            if unknown_incompatible:
                raise ValueError(
                    f"unknown incompatible labels for {label.event_type}: "
                    f"{sorted(unknown_incompatible)}"
                )
            if label.event_type in label.incompatible_labels:
                raise ValueError(f"{label.event_type} cannot be incompatible with itself")
        return self

    def label(self, event_type: str) -> LabelDefinition:
        try:
            return next(label for label in self.labels if label.event_type == event_type)
        except StopIteration as error:
            raise ValueError(f"unknown ontology label: {event_type}") from error

    def family_for(self, event_type: str) -> str:
        return self.label(event_type).valid_parent

    def validate_event(
        self,
        event_type: str,
        attributes: dict[str, object],
    ) -> ValidatedEvent:
        label = self.label(event_type)
        allowed = self.shared_attributes | self.family_attributes.get(label.valid_parent, {})
        unknown = set(attributes) - set(allowed)
        if unknown:
            raise ValueError(f"unknown attributes for {event_type}: {sorted(unknown)}")
        missing = {
            name
            for name in label.required_attributes
            if name not in attributes or attributes[name] is None
        }
        if missing:
            raise ValueError(f"missing required attributes for {event_type}: {sorted(missing)}")
        for name, value in attributes.items():
            if value is not None:
                _validate_attribute(name, value, allowed[name])
        return ValidatedEvent(event_type=event_type, attributes=attributes)


def _validate_attribute(
    name: str,
    value: object,
    definition: AttributeDefinition,
) -> None:
    valid = False
    if definition.kind == "string":
        valid = isinstance(value, str) and bool(value.strip())
    elif definition.kind == "number":
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
        )
    elif definition.kind == "boolean":
        valid = isinstance(value, bool)
    elif definition.kind == "date":
        try:
            valid = type(value) is date or (
                isinstance(value, str) and date.fromisoformat(value) is not None
            )
        except ValueError:
            valid = False
    elif definition.kind == "enum":
        valid = isinstance(value, str) and value in definition.allowed_values
    elif definition.kind == "string_list":
        valid = (
            isinstance(value, (list, tuple))
            and all(isinstance(item, str) and item.strip() for item in value)
        )
    if not valid:
        raise ValueError(f"invalid {definition.kind} value for attribute {name}")
