"""Build auditable canonical candidates from the calibration AI panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from financial_event_model.ontology import OntologyDefinition, load_ontology

from .models import (
    AdjudicationStatus,
    AnnotationPolicy,
    AnnotationRecord,
    AnnotationTask,
    EvidenceSpan,
)
from .dataset import DatasetRelease, build_dataset_release
from .store import AnnotationStore


MODEL_ORDER = ("A", "B", "C", "D", "E")
MODEL_FILES = {
    "A": ("model_a_001_010.jsonl", "model_a_011_100.jsonl"),
    "B": ("model_b_001_010.jsonl", "model_b_011_100.jsonl"),
    "C": ("model_c_001_010.jsonl",),
    "D": ("model_d_001_010.jsonl", "model_d_011_053.jsonl"),
    "E": ("model_e_001_010.jsonl", "model_e_011_100.jsonl"),
}
_PUNCTUATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-"}
)
_VALIDATION_TIME = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_models(labels_dir: Path) -> dict[str, dict[int, dict[str, object]]]:
    return {
        model: {
            int(row["task_number"]): row
            for filename in filenames
            for row in _read_jsonl(labels_dir / filename)
        }
        for model, filenames in MODEL_FILES.items()
    }


def _load_tasks(database: Path) -> dict[str, AnnotationTask]:
    with sqlite3.connect(database) as connection:
        return {
            event_id: AnnotationTask.model_validate(json.loads(payload))
            for event_id, payload in connection.execute(
                "SELECT event_id, payload_json FROM annotation_tasks"
            )
        }


def _normalise_value(value: object) -> object:
    return sorted(value) if isinstance(value, list) else value


def _near_task_id(left: str, right: str, *, limit: int = 2) -> bool:
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, 1):
        current = [left_index]
        for right_index, right_character in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        if min(current) > limit:
            return False
        previous = current
    return previous[-1] <= limit


def _resolve_value(values: dict[str, object]) -> tuple[object, list[str], str]:
    votes: dict[str, list[str]] = defaultdict(list)
    decoded: dict[str, object] = {}
    for model, raw_value in values.items():
        value = _normalise_value(raw_value)
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        votes[key].append(model)
        decoded[key] = value
    winner = min(
        votes,
        key=lambda key: (
            -len(votes[key]),
            min(MODEL_ORDER.index(model) for model in votes[key]),
            key,
        ),
    )
    supporters = sorted(votes[winner], key=MODEL_ORDER.index)
    if len(votes) == 1:
        rule = "unanimous"
    elif len(supporters) > len(values) / 2:
        rule = "strict_majority"
    else:
        rule = "model_priority_tiebreak"
    return decoded[winner], supporters, rule


def _indexed_normalise(text: str) -> tuple[str, list[int]]:
    rendered: list[str] = []
    indexes: list[int] = []
    in_space = False
    for index, character in enumerate(text):
        for output in unicodedata.normalize("NFKC", character).translate(_PUNCTUATION):
            if output.isspace():
                if rendered and not in_space:
                    rendered.append(" ")
                    indexes.append(index)
                in_space = True
            else:
                rendered.append(output)
                indexes.append(index)
                in_space = False
    if rendered and rendered[-1] == " ":
        rendered.pop()
        indexes.pop()
    return "".join(rendered), indexes


def align_quote(section: str, quote: str) -> EvidenceSpan | None:
    """Return exact source offsets after harmless whitespace/punctuation repair."""
    haystack, indexes = _indexed_normalise(section)
    needle, _ = _indexed_normalise(quote)
    candidates = [needle]
    stripped = needle.lstrip("�•*- ")
    if stripped and stripped != needle:
        candidates.append(stripped)
    if needle and needle[-1] in ".;:":
        candidates.append(needle[:-1])
    for candidate in candidates:
        position = haystack.find(candidate)
        if position >= 0:
            start = indexes[position]
            end = indexes[position + len(candidate) - 1] + 1
            return EvidenceSpan(start=start, end=end, text=section[start:end])
    return None


def _evidence_for_label(
    *,
    label: str,
    task_number: int,
    task: AnnotationTask,
    source_models: list[str],
    model_rows: dict[str, dict[int, dict[str, object]]],
) -> tuple[EvidenceSpan, list[str], str]:
    def candidates(models: list[str]) -> dict[tuple[int, int, str], set[str]]:
        found: dict[tuple[int, int, str], set[str]] = defaultdict(set)
        for model in models:
            quotes = model_rows[model][task_number].get("evidence_quotes", {}).get(label, [])
            for quote in quotes:
                span = align_quote(task.relevant_section, quote)
                if span is not None:
                    found[(span.start, span.end, span.text)].add(model)
        return found

    found = candidates(source_models)
    rule = "selected_model_evidence"
    if not found:
        fallback_models = [
            model
            for model in MODEL_ORDER
            if task_number in model_rows[model]
            and label in model_rows[model][task_number].get("labels", [])
        ]
        found = candidates(fallback_models)
        rule = "source_repair_from_label_supporter"
    if not found:
        raise ValueError(f"task {task_number} label {label} has no source-aligned evidence")
    key = min(
        found,
        key=lambda item: (-len(found[item]), item[1] - item[0], item[0], item[1]),
    )
    span = EvidenceSpan(start=key[0], end=key[1], text=key[2])
    return span, sorted(found[key], key=MODEL_ORDER.index), rule


def synthesize_panel(
    *,
    labels_dir: str | Path,
    database: str | Path,
    ontology_path: str | Path,
) -> tuple[dict[str, object], ...]:
    labels_path = Path(labels_dir)
    ontology = load_ontology(ontology_path)
    decisions = _read_jsonl(labels_path / "panel_label_decisions_001_100.jsonl")
    model_rows = _load_models(labels_path)
    tasks = _load_tasks(Path(database))
    results: list[dict[str, object]] = []

    for decision in decisions:
        task_number = int(decision["task_number"])
        event_id = str(decision["task_id"])
        labels = sorted(decision["final_labels"])
        task = tasks[event_id]
        adjudicated = decision["decision_source"] == "user_adjudication_aligned_with_model_a"
        source_models = ["A"] if adjudicated else list(decision["supporting_models"])
        if not source_models:
            raise ValueError(f"task {task_number} has no supporting model")
        task_id_repairs: dict[str, str] = {}
        for model in source_models:
            row = model_rows[model][task_number]
            if sorted(row["labels"]) != labels:
                raise ValueError(f"task {task_number} source model {model} does not match decision")
            if row["task_id"] != event_id:
                if not _near_task_id(str(row["task_id"]), event_id):
                    raise ValueError(
                        f"task {task_number} source model {model} has an unrelated task_id"
                    )
                task_id_repairs[model] = str(row["task_id"])

        attributes: dict[str, dict[str, object]] = {}
        attribute_sources: dict[str, dict[str, dict[str, object]]] = {}
        evidence_by_label: dict[str, dict[str, object]] = {}
        chosen_spans: dict[tuple[int, int, str], EvidenceSpan] = {}
        for label in labels:
            if adjudicated:
                selected = dict(model_rows["A"][task_number]["attributes"][label])
                ontology.validate_event(label, selected)
                sources = {
                    field: {"models": ["A"], "selection_rule": "model_a_adjudication"}
                    for field in selected
                }
            else:
                source_attributes = {
                    model: model_rows[model][task_number]["attributes"][label]
                    for model in source_models
                }
                for model, values in source_attributes.items():
                    ontology.validate_event(label, values)
                selected = {}
                sources = {}
                for field in sorted({key for values in source_attributes.values() for key in values}):
                    value, models, rule = _resolve_value(
                        {model: values[field] for model, values in source_attributes.items() if field in values}
                    )
                    selected[field] = value
                    sources[field] = {"models": models, "selection_rule": rule}
                ontology.validate_event(label, selected)
            attributes[label] = selected
            attribute_sources[label] = sources
            span, evidence_models, evidence_rule = _evidence_for_label(
                label=label,
                task_number=task_number,
                task=task,
                source_models=source_models,
                model_rows=model_rows,
            )
            chosen_spans[(span.start, span.end, span.text)] = span
            evidence_by_label[label] = {
                "span": span.model_dump(mode="json"),
                "models": evidence_models,
                "selection_rule": evidence_rule,
            }

        confidence = float(median(float(model_rows[m][task_number]["confidence"]) for m in source_models))
        ambiguity_value, ambiguity_models, ambiguity_rule = _resolve_value(
            {model: bool(model_rows[model][task_number]["ambiguity_flag"]) for model in source_models}
        )
        ambiguity_flag = bool(ambiguity_value)
        ambiguity_reason = ""
        if ambiguity_flag:
            ambiguity_reason = next(
                (
                    str(model_rows[model][task_number].get("ambiguity_reason", ""))
                    for model in ambiguity_models
                    if model_rows[model][task_number].get("ambiguity_reason")
                ),
                "Panel source marked the record ambiguous.",
            )
        evidence_spans = sorted(chosen_spans.values(), key=lambda span: (span.start, span.end))
        no_material_event = not labels

        validation_record = AnnotationRecord(
            annotation_id=f"panel-canonical-{task_number:03d}",
            event_id=event_id,
            annotator_id="ai-panel-v1",
            ontology_version=ontology.version,
            labels=tuple(labels),
            attributes=attributes,
            evidence_spans=tuple(evidence_spans),
            confidence=confidence,
            ambiguity_flag=ambiguity_flag,
            no_material_event=no_material_event,
            created_at=_VALIDATION_TIME,
            supersedes_annotation_id=None,
            adjudication_status=(
                AdjudicationStatus.ADJUDICATED
                if adjudicated
                else AdjudicationStatus.SUBMITTED
            ),
        )
        validation_record.validate_against(ontology, task)
        results.append(
            {
                "schema_version": "panel-canonical-v0.1",
                "task_number": task_number,
                "task_id": event_id,
                "no_material_event": no_material_event,
                "labels": labels,
                "attributes": attributes,
                "evidence_spans": [span.model_dump(mode="json") for span in evidence_spans],
                "confidence": confidence,
                "ambiguity_flag": ambiguity_flag,
                "ambiguity_reason": ambiguity_reason,
                "decision_source": decision["decision_source"],
                "provenance": decision["provenance"],
                "gold_status": "not_human_gold",
                "source_models": source_models,
                "synthesis": {
                    "attribute_sources": attribute_sources,
                    "evidence_by_label": evidence_by_label,
                    "ambiguity_sources": {
                        "models": ambiguity_models,
                        "selection_rule": ambiguity_rule,
                    },
                    "source_task_id_repairs": task_id_repairs,
                },
            }
        )

    if [row["task_number"] for row in results] != list(range(1, 101)):
        raise ValueError("panel decisions must contain tasks 1 through 100 in order")
    return tuple(results)


def write_jsonl(records: tuple[dict[str, object], ...], output: str | Path) -> str:
    path = Path(output)
    content = "".join(
        json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
        for record in records
    )
    payload = content.encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return hashlib.sha256(payload).hexdigest()


def import_panel_release(
    store: AnnotationStore,
    canonical_path: str | Path,
    policy: AnnotationPolicy,
    *,
    release_id: str,
) -> DatasetRelease:
    rows = _read_jsonl(Path(canonical_path))
    tasks = {task.event_id: task for task in store.list_tasks()}
    if {str(row["task_id"]) for row in rows} != set(tasks):
        raise ValueError("canonical panel task IDs do not match the annotation queue")
    records: list[AnnotationRecord] = []
    for row in rows:
        if row.get("gold_status") != "not_human_gold":
            raise ValueError("AI-panel records must remain marked not_human_gold")
        event_id = str(row["task_id"])
        payload_hash = hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        record = AnnotationRecord(
            annotation_id=f"ai-panel-v1-{payload_hash[:24]}",
            event_id=event_id,
            annotator_id="ai-panel-v1",
            ontology_version=store.ontology.version,
            labels=tuple(row["labels"]),
            attributes=row["attributes"],
            evidence_spans=tuple(
                EvidenceSpan.model_validate(span) for span in row["evidence_spans"]
            ),
            confidence=float(row["confidence"]),
            ambiguity_flag=bool(row["ambiguity_flag"]),
            no_material_event=bool(row["no_material_event"]),
            created_at=_VALIDATION_TIME,
            supersedes_annotation_id=None,
            adjudication_status=(
                AdjudicationStatus.ADJUDICATED
                if row["decision_source"] == "user_adjudication_aligned_with_model_a"
                else AdjudicationStatus.SUBMITTED
            ),
        )
        record.validate_against(store.ontology, tasks[event_id])
        existing = next(
            (
                current
                for current in store.current_annotations(event_id)
                if current.annotator_id == record.annotator_id
            ),
            None,
        )
        if existing is None:
            store.save_annotation(record)
        elif existing != record:
            raise ValueError(f"AI-panel annotation already differs for {event_id}")
        records.append(record)
    release = build_dataset_release(
        tuple(tasks.values()),
        tuple(records),
        store.ontology,
        policy,
        release_id=release_id,
        evidence_kind="ai_panel",
    )
    store.freeze_release(release)
    return release


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", default="data/labels")
    parser.add_argument("--database", default="data/labels/annotations.sqlite")
    parser.add_argument("--ontology", default="configs/ontology.yaml")
    parser.add_argument(
        "--output", default="data/labels/panel_canonical_annotations_001_100.jsonl"
    )
    args = parser.parse_args(argv)
    records = synthesize_panel(
        labels_dir=args.labels_dir,
        database=args.database,
        ontology_path=args.ontology,
    )
    digest = write_jsonl(records, args.output)
    print(
        json.dumps(
            {
                "records": len(records),
                "material": sum(not row["no_material_event"] for row in records),
                "no_material_event": sum(row["no_material_event"] for row in records),
                "output": args.output,
                "sha256": digest,
                "database_imported": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
