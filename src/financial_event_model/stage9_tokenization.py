"""Fail-closed character-to-token evidence alignment for Stage 9."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def format_primary_input(input_payload: dict[str, Any]) -> tuple[str, int]:
    """Return the primary tokenizer sequence and raw-text character offset."""
    filing_type = input_payload.get("filing_type") or "unknown"
    prefix = f"Filing type: {filing_type}\n\n"
    return prefix + str(input_payload["text"]), len(prefix)


def character_span_to_token_span(
    *,
    primary: str,
    offsets: Sequence[tuple[int, int] | list[int]],
    sequence_ids: Sequence[int | None],
    char_start: int,
    char_end: int,
    evidence_text: str,
) -> tuple[int, int]:
    """Map an exact primary-sequence character span to [start, end) tokens."""
    if char_start < 0 or char_end <= char_start or char_end > len(primary):
        raise ValueError("evidence character bounds are invalid")
    if primary[char_start:char_end] != evidence_text:
        raise ValueError("evidence text does not match its character bounds")

    overlapping = [
        index
        for index, ((token_start, token_end), sequence_id) in enumerate(
            zip(offsets, sequence_ids, strict=True)
        )
        if sequence_id == 0
        and token_end > token_start
        and token_end > char_start
        and token_start < char_end
    ]
    if not overlapping:
        raise ValueError("evidence is not exactly represented by tokenizer offsets")

    token_start = overlapping[0]
    token_end = overlapping[-1] + 1
    covered_start = int(offsets[token_start][0])
    covered_end = int(offsets[token_end - 1][1])
    if covered_start > char_start or covered_end < char_end:
        raise ValueError("evidence is not exactly represented by tokenizer offsets")
    if primary[covered_start:char_start].strip() or primary[char_end:covered_end].strip():
        raise ValueError("evidence is not exactly represented by tokenizer offsets")
    return token_start, token_end


def tokenize_stage9_row(
    row: dict[str, Any],
    tokenizer: Any,
    *,
    max_length: int,
) -> dict[str, Any]:
    """Tokenize one development row and attach exact token evidence spans."""
    primary, text_offset = format_primary_input(row["input"])
    prior = row["input"].get("prior_company_disclosure") or None
    encoding = tokenizer(
        primary,
        text_pair=prior,
        max_length=max_length,
        truncation=True,
        return_offsets_mapping=True,
    )
    offsets = encoding["offset_mapping"]
    sequence_ids = encoding.sequence_ids()
    token_spans = []
    for span in row["target"]["evidence_spans"]:
        token_start, token_end = character_span_to_token_span(
            primary=primary,
            offsets=offsets,
            sequence_ids=sequence_ids,
            char_start=text_offset + int(span["start"]),
            char_end=text_offset + int(span["end"]),
            evidence_text=str(span["text"]),
        )
        token_spans.append(
            {
                **span,
                "token_start": token_start,
                "token_end": token_end,
                "sequence_id": 0,
                "token_char_start": int(offsets[token_start][0]) - text_offset,
                "token_char_end": int(offsets[token_end - 1][1]) - text_offset,
                "token_left_trim": text_offset
                + int(span["start"])
                - int(offsets[token_start][0]),
                "token_right_trim": int(offsets[token_end - 1][1])
                - text_offset
                - int(span["end"]),
            }
        )
    return {
        "event_id": row["event_id"],
        "input_ids": list(encoding["input_ids"]),
        "attention_mask": list(encoding["attention_mask"]),
        "evidence_spans": token_spans,
    }
