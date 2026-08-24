"""Deterministic preparation and audit of the real Stage 7 calibration round."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pydantic import Field

from financial_event_model.contracts import Contract

from .models import (
    AdjudicationStatus,
    AnnotationRecord,
    AnnotationRound,
    AnnotationTask,
    EvidenceSpan,
)
from .store import AnnotationStore


_CIK_PATTERN = re.compile(r"/submissions/CIK(?P<cik>\d{10})\.json$")
_EVENT_TERMS = (
    "acquisition",
    "agreement",
    "approval",
    "award",
    "backlog",
    "buyback",
    "chief executive",
    "chief financial",
    "contract",
    "credit facility",
    "customer",
    "debt",
    "dividend",
    "earnings",
    "guidance",
    "impairment",
    "investigation",
    "launch",
    "layoff",
    "litigation",
    "merger",
    "offering",
    "order",
    "regulatory",
    "repurchase",
    "restructuring",
    "results",
    "revenue",
    "split",
)


class CalibrationPreparationResult(Contract):
    task_count: int = Field(ge=1)
    entity_count: int = Field(ge=1)
    queue_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CalibrationAgreementReport(Contract):
    annotator_a: str = Field(min_length=1)
    annotator_b: str = Field(min_length=1)
    task_count: int = Field(ge=0)
    annotator_a_completed: int = Field(ge=0)
    annotator_b_completed: int = Field(ge=0)
    paired_count: int = Field(ge=0)
    agreement_count: int = Field(ge=0)
    exact_agreement: float | None = Field(default=None, ge=0, le=1)
    incomplete_event_ids: tuple[str, ...]
    disagreement_event_ids: tuple[str, ...]
    unresolved_event_ids: tuple[str, ...]
    calibration_complete: bool


def build_calibration_tasks(
    *,
    sec_manifest_path: str | Path,
    normalization_manifest_path: str | Path,
    knowledge_store_path: str | Path,
    expected_documents: int,
) -> tuple[AnnotationTask, ...]:
    if expected_documents <= 0:
        raise ValueError("expected_documents must be positive")
    sec_path = Path(sec_manifest_path)
    normalized_path = Path(normalization_manifest_path)
    knowledge_path = Path(knowledge_store_path)
    companies = _company_names(sec_path)
    normalized = _normalized_documents(normalized_path)
    knowledge = _knowledge_records(knowledge_path)

    normalization_ids = set(normalized)
    knowledge_ids = set(knowledge)
    if normalization_ids != knowledge_ids:
        missing_knowledge = sorted(normalization_ids - knowledge_ids)
        missing_normalized = sorted(knowledge_ids - normalization_ids)
        raise ValueError(
            "normalization/knowledge provenance mismatch: "
            f"missing knowledge={missing_knowledge}, missing normalized={missing_normalized}"
        )
    if len(normalized) != expected_documents:
        raise ValueError(
            f"expected {expected_documents} calibration documents; found {len(normalized)}"
        )

    staged: list[AnnotationTask] = []
    prior_by_entity: dict[str, list[AnnotationTask]] = defaultdict(list)
    ordered = sorted(
        knowledge.values(),
        key=lambda item: (
            item["source_published_at"],
            item["normalization_id"],
            item["record_id"],
        ),
    )
    for record in ordered:
        normalization_id = record["normalization_id"]
        document = normalized[normalization_id]
        payload = record["payload"]
        cik = str(payload["cik"])
        entity_id = str(record["entity_id"])
        relevant_section, evidence = _review_text(document)
        priors = [
            task
            for task in prior_by_entity[entity_id]
            if task.source_published_at < record["source_published_at"]
        ]
        prior = priors[-1].relevant_section[:1200] if priors else None
        task = AnnotationTask(
            event_id=f"calibration-{record['record_id']}",
            company=companies.get(cik, f"SEC registrant CIK {cik}"),
            entity_id=entity_id,
            related_event_group=str(payload["accession_number"]),
            source_published_at=record["source_published_at"],
            tradable_at=record["tradable_at"],
            filing_type=str(payload["document_type"]),
            relevant_section=relevant_section,
            candidate_evidence=evidence,
            prior_company_disclosure=prior,
            annotation_round=AnnotationRound.CALIBRATION,
            candidate_labels=(),
            priority_reason="Accepted Stage 3 document with Stage 4 tradability provenance.",
        )
        staged.append(task)
        prior_by_entity[entity_id].append(task)
    return tuple(sorted(staged, key=lambda task: task.event_id))


def prepare_calibration(
    store: AnnotationStore,
    *,
    sec_manifest_path: str | Path,
    normalization_manifest_path: str | Path,
    knowledge_store_path: str | Path,
    expected_documents: int,
) -> CalibrationPreparationResult:
    tasks = build_calibration_tasks(
        sec_manifest_path=sec_manifest_path,
        normalization_manifest_path=normalization_manifest_path,
        knowledge_store_path=knowledge_store_path,
        expected_documents=expected_documents,
    )
    store.add_tasks(tasks)
    canonical = json.dumps(
        [task.model_dump(mode="json") for task in tasks],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return CalibrationPreparationResult(
        task_count=len(tasks),
        entity_count=len({task.entity_id for task in tasks}),
        queue_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def calibration_agreement(
    store: AnnotationStore,
    annotator_a: str,
    annotator_b: str,
) -> CalibrationAgreementReport:
    annotator_a = annotator_a.strip()
    annotator_b = annotator_b.strip()
    if not annotator_a or not annotator_b or annotator_a == annotator_b:
        raise ValueError("calibration requires two distinct annotator IDs")
    tasks = tuple(
        task
        for task in store.list_tasks()
        if task.annotation_round is AnnotationRound.CALIBRATION
    )
    incomplete: list[str] = []
    disagreements: list[str] = []
    unresolved: list[str] = []
    completed_a = completed_b = agreements = paired = 0
    for task in tasks:
        by_annotator = {
            record.annotator_id: record
            for record in store.current_annotations(task.event_id)
            if record.annotator_id in {annotator_a, annotator_b}
        }
        first = by_annotator.get(annotator_a)
        second = by_annotator.get(annotator_b)
        completed_a += first is not None
        completed_b += second is not None
        if first is None or second is None:
            incomplete.append(task.event_id)
            continue
        paired += 1
        if _decision_signature(first) == _decision_signature(second):
            agreements += 1
            continue
        disagreements.append(task.event_id)
        if not any(
            record.adjudication_status is AdjudicationStatus.ADJUDICATED
            for record in (first, second)
        ):
            unresolved.append(task.event_id)
    return CalibrationAgreementReport(
        annotator_a=annotator_a,
        annotator_b=annotator_b,
        task_count=len(tasks),
        annotator_a_completed=completed_a,
        annotator_b_completed=completed_b,
        paired_count=paired,
        agreement_count=agreements,
        exact_agreement=(agreements / paired if paired else None),
        incomplete_event_ids=tuple(incomplete),
        disagreement_event_ids=tuple(disagreements),
        unresolved_event_ids=tuple(unresolved),
        calibration_complete=(
            bool(tasks) and paired == len(tasks) and not unresolved
        ),
    )


def _decision_signature(record: AnnotationRecord) -> tuple[bool, tuple[str, ...]]:
    return record.no_material_event, tuple(sorted(record.labels))


def _company_names(sec_manifest_path: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with sqlite3.connect(sec_manifest_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT request_url, local_path FROM sec_requests WHERE local_path IS NOT NULL"
        ).fetchall()
    for row in rows:
        match = _CIK_PATTERN.search(str(row["request_url"]))
        if match is None:
            continue
        path = _resolve_path(str(row["local_path"]), sec_manifest_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        name = str(payload.get("name", "")).strip()
        if name:
            names[match.group("cik")] = name
    return names


def _normalized_documents(manifest_path: Path) -> dict[int, dict[str, object]]:
    with sqlite3.connect(manifest_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT normalization_id, local_path
            FROM normalized_documents
            WHERE success = 1 AND local_path IS NOT NULL
            ORDER BY normalization_id
            """
        ).fetchall()
    documents: dict[int, dict[str, object]] = {}
    for row in rows:
        path = _resolve_path(str(row["local_path"]), manifest_path)
        documents[int(row["normalization_id"])] = json.loads(
            path.read_text(encoding="utf-8")
        )
    return documents


def _knowledge_records(path: Path) -> dict[int, dict[str, object]]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT record_id, entity_id, payload_json,
                   source_published_at, tradable_at
            FROM knowledge_records
            WHERE source_id LIKE 'sec-normalized:%'
            ORDER BY record_id
            """
        ).fetchall()
    records: dict[int, dict[str, object]] = {}
    for row in rows:
        payload = json.loads(row["payload_json"])
        normalization_id = int(payload["normalization_id"])
        if normalization_id in records:
            raise ValueError(f"duplicate knowledge record for normalization {normalization_id}")
        records[normalization_id] = {
            "record_id": str(row["record_id"]),
            "entity_id": str(row["entity_id"]),
            "payload": payload,
            "normalization_id": normalization_id,
            "source_published_at": datetime.fromisoformat(row["source_published_at"]),
            "tradable_at": datetime.fromisoformat(row["tradable_at"]),
        }
    return records


def _review_text(document: dict[str, object]) -> tuple[str, tuple[EvidenceSpan, ...]]:
    raw_sections = document.get("sections")
    if not isinstance(raw_sections, list):
        raise ValueError("normalized document sections must be a list")
    sections = [
        section
        for section in raw_sections
        if isinstance(section, dict)
        and not section.get("is_table")
        and str(section.get("text", "")).strip()
    ]
    preferred = [section for section in sections if not section.get("is_boilerplate")]
    candidates = preferred or sections
    if not candidates:
        raise ValueError("normalized document has no reviewable text")
    ranked = sorted(
        enumerate(candidates),
        key=lambda pair: (-_section_score(pair[1]), pair[0]),
    )
    selected = [section for _, section in ranked[:6]]
    parts: list[str] = []
    span_ranges: list[tuple[int, int, str]] = []
    cursor = 0
    for section in selected:
        if cursor >= 12_000:
            break
        heading = str(section.get("heading", "")).strip()
        text = str(section["text"]).strip()
        block = f"{heading}\n\n{text}" if heading else text
        if parts:
            separator = "\n\n---\n\n"
            parts.append(separator)
            cursor += len(separator)
        available = 12_000 - cursor
        block = block[:available].rstrip()
        if not block:
            continue
        parts.append(block)
        text_start = cursor + (len(heading) + 2 if heading else 0)
        evidence_text = _first_paragraph(text)[:600].rstrip()
        if evidence_text and text_start + len(evidence_text) <= cursor + len(block):
            span_ranges.append(
                (text_start, text_start + len(evidence_text), evidence_text)
            )
        cursor += len(block)
    relevant = "".join(parts)
    evidence = tuple(
        EvidenceSpan(start=start, end=end, text=text)
        for start, end, text in span_ranges[:4]
    )
    if not relevant or not evidence:
        raise ValueError("normalized document did not produce exact review evidence")
    return relevant, evidence


def _section_score(section: dict[str, object]) -> int:
    content = (
        f"{section.get('heading', '')} {str(section.get('text', ''))[:2000]}"
    ).casefold()
    return sum(content.count(term) for term in _EVENT_TERMS)


def _first_paragraph(text: str) -> str:
    return next(
        (paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()),
        "",
    )


def _resolve_path(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return manifest_path.parent / path
