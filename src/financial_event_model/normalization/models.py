"""Versioned normalized-document contracts."""

from typing import Self

from pydantic import Field, model_validator

from financial_event_model.contracts import Contract


class NormalizedSection(Contract):
    section_id: str = Field(min_length=1)
    heading: str | None
    text: str = Field(min_length=1)
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    is_table: bool = False
    is_boilerplate: bool = False

    @model_validator(mode="after")
    def validate_source_range(self) -> Self:
        if self.source_end <= self.source_start:
            raise ValueError("source_end must be greater than source_start")
        return self


class NormalizedDocument(Contract):
    document_id: str = Field(min_length=1)
    source_document_id: int = Field(gt=0)
    accession_number: str = Field(min_length=1)
    source_content_hash: str = Field(min_length=64, max_length=64)
    parser_version: str = Field(min_length=1)
    document_type: str | None
    filename: str | None
    parent_document_id: int | None
    is_exhibit: bool
    language: str = Field(min_length=1)
    parsing_quality: float = Field(ge=0.0, le=1.0)
    warnings: tuple[str, ...]
    sections: tuple[NormalizedSection, ...]


class NormalizationRunResult(Contract):
    selected: int = Field(ge=0)
    completed: int = Field(ge=0)
    reused: int = Field(ge=0)
    failed: int = Field(ge=0)
    source_document_ids: tuple[int, ...]
    failed_document_ids: tuple[int, ...]
