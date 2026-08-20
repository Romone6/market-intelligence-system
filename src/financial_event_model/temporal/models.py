"""Versioned point-in-time knowledge contracts."""

from datetime import datetime, timezone
from typing import Any, Self

from pydantic import AwareDatetime, Field, model_validator

from financial_event_model.contracts import Contract


class KnowledgeRecord(Contract):
    record_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    knowledge_type: str = Field(min_length=1)
    knowledge_key: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    payload: dict[str, Any]
    event_effective_at: AwareDatetime | None
    source_published_at: AwareDatetime
    first_observed_at: AwareDatetime
    downloaded_at: AwareDatetime
    processed_at: AwareDatetime
    tradable_at: AwareDatetime
    policy_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> Self:
        if self.downloaded_at < self.first_observed_at:
            raise ValueError("downloaded_at must not precede first_observed_at")
        if self.processed_at < self.downloaded_at:
            raise ValueError("processed_at must not precede downloaded_at")
        if self.tradable_at < self.source_published_at:
            raise ValueError("tradable_at must not precede source_published_at")
        return self

    def as_utc(self) -> Self:
        updates = {
            name: value.astimezone(timezone.utc)
            for name in (
                "event_effective_at",
                "source_published_at",
                "first_observed_at",
                "downloaded_at",
                "processed_at",
                "tradable_at",
            )
            if (value := getattr(self, name)) is not None
        }
        return self.model_copy(update=updates)


class MaterializationResult(Contract):
    selected: int
    materialized: int
    skipped: int
    skipped_source_document_ids: tuple[int, ...]
