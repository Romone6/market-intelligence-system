"""Deterministic, leakage-safe Stage 7 dataset release construction."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Literal

from pydantic import AwareDatetime, Field

from financial_event_model.contracts import Contract
from financial_event_model.ontology import OntologyDefinition

from .models import (
    AdjudicationStatus,
    AnnotationPolicy,
    AnnotationRecord,
    AnnotationRound,
    AnnotationTask,
)


class AgreementMetrics(Contract):
    double_labeled_items: int = Field(ge=0)
    double_label_fraction: float = Field(ge=0, le=1)
    exact_label_agreement: float = Field(ge=0, le=1)
    family_agreement: float = Field(ge=0, le=1)
    adjudicated_disagreements: int = Field(ge=0)


class LeakageReport(Contract):
    entity_intersection: tuple[str, ...]
    related_event_intersection: tuple[str, ...]
    passed: bool


class DatasetRelease(Contract):
    release_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_kind: Literal["fixture", "human"]
    ontology_version: str = Field(min_length=1)
    ontology_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: AwareDatetime
    train_event_ids: tuple[str, ...]
    eval_event_ids: tuple[str, ...]
    annotation_ids: dict[str, str]
    task_hashes: dict[str, str]
    agreement: AgreementMetrics
    class_distribution: dict[str, int]
    rare_labels: dict[str, int]
    leakage: LeakageReport
    gold_size_passed: bool
    double_label_coverage_passed: bool
    adjudication_passed: bool
    contract_checks_passed: bool
    stage_acceptance_passed: bool

    def expected_content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        payload["created_at"] = self.created_at.isoformat()
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _signature(record: AnnotationRecord) -> tuple[str, ...]:
    return ("no_material_event",) if record.no_material_event else tuple(sorted(record.labels))


def _families(signature: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                "no_material_event"
                if label == "no_material_event"
                else label.split(".", 1)[0]
                for label in signature
            }
        )
    )


def _current_records(records: tuple[AnnotationRecord, ...]) -> tuple[AnnotationRecord, ...]:
    by_id: dict[str, AnnotationRecord] = {}
    for record in records:
        if record.annotation_id in by_id:
            raise ValueError(f"duplicate annotation_id: {record.annotation_id}")
        by_id[record.annotation_id] = record
    superseded: set[str] = set()
    for record in records:
        if record.supersedes_annotation_id is not None:
            target_id = record.supersedes_annotation_id
            target = by_id.get(target_id)
            if target is None:
                raise ValueError(f"superseded annotation is missing: {target_id}")
            if target_id in superseded:
                raise ValueError(f"annotation is superseded more than once: {target_id}")
            if (target.event_id, target.annotator_id) != (
                record.event_id,
                record.annotator_id,
            ):
                raise ValueError("supersession must preserve the same event and annotator")
            if record.created_at <= target.created_at:
                raise ValueError("replacement created_at must be later than superseded record")
            superseded.add(target_id)
    return tuple(
        sorted(
            (record for record in records if record.annotation_id not in superseded),
            key=lambda item: (item.event_id, item.annotator_id, item.annotation_id),
        )
    )


def _resolve_records(
    tasks: dict[str, AnnotationTask],
    records: tuple[AnnotationRecord, ...],
    ontology: OntologyDefinition,
) -> tuple[dict[str, AnnotationRecord], AgreementMetrics]:
    grouped: dict[str, list[AnnotationRecord]] = defaultdict(list)
    for record in _current_records(records):
        task = tasks.get(record.event_id)
        if task is None:
            raise ValueError(f"annotation has no task: {record.event_id}")
        record.validate_against(ontology, task)
        if record.adjudication_status != AdjudicationStatus.EXCLUDED:
            grouped[record.event_id].append(record)

    resolved: dict[str, AnnotationRecord] = {}
    double_count = exact_matches = family_matches = adjudicated_count = 0
    for event_id in sorted(grouped):
        event_records = grouped[event_id]
        adjudicated = [
            record
            for record in event_records
            if record.adjudication_status == AdjudicationStatus.ADJUDICATED
        ]
        independent = [
            record
            for record in event_records
            if record.adjudication_status
            in {AdjudicationStatus.SUBMITTED, AdjudicationStatus.NEEDS_ADJUDICATION}
        ]
        if len(adjudicated) > 1:
            raise ValueError(f"{event_id} has multiple current adjudications")
        if len(independent) > 2:
            raise ValueError(f"{event_id} has more than two independent annotations")
        if not independent and not adjudicated:
            continue
        if len(independent) == 2:
            if independent[0].annotator_id == independent[1].annotator_id:
                raise ValueError(f"{event_id} double labels must use distinct annotators")
            double_count += 1
            left, right = _signature(independent[0]), _signature(independent[1])
            if left == right:
                exact_matches += 1
            if _families(left) == _families(right):
                family_matches += 1
            if left != right:
                if not adjudicated:
                    raise ValueError(f"{event_id} disagreement requires adjudication")
                adjudicated_count += 1
        resolved[event_id] = adjudicated[0] if adjudicated else independent[0]

    item_count = len(resolved)
    return resolved, AgreementMetrics(
        double_labeled_items=double_count,
        double_label_fraction=(double_count / item_count if item_count else 0),
        exact_label_agreement=(exact_matches / double_count if double_count else 0),
        family_agreement=(family_matches / double_count if double_count else 0),
        adjudicated_disagreements=adjudicated_count,
    )


class _Components:
    def __init__(self, event_ids: tuple[str, ...]) -> None:
        self.parent = {event_id: event_id for event_id in event_ids}

    def find(self, event_id: str) -> str:
        parent = self.parent[event_id]
        if parent != event_id:
            self.parent[event_id] = self.find(parent)
        return self.parent[event_id]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        self.parent[high] = low


def _split_events(
    tasks: dict[str, AnnotationTask],
    event_ids: tuple[str, ...],
    policy: AnnotationPolicy,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    components = _Components(event_ids)
    by_entity: dict[str, str] = {}
    by_related: dict[str, str] = {}
    for event_id in event_ids:
        task = tasks[event_id]
        prior_entity = by_entity.setdefault(task.entity_id, event_id)
        components.union(prior_entity, event_id)
        if task.related_event_group is not None:
            prior_related = by_related.setdefault(task.related_event_group, event_id)
            components.union(prior_related, event_id)

    grouped: dict[str, list[str]] = defaultdict(list)
    for event_id in event_ids:
        grouped[components.find(event_id)].append(event_id)
    ranked = sorted(
        (tuple(sorted(ids)) for ids in grouped.values()),
        key=lambda ids: hashlib.sha256(
            f"{policy.split_seed}:{'|'.join(ids)}".encode()
        ).hexdigest(),
    )
    target = max(1, round(len(event_ids) * policy.evaluation_fraction))
    evaluation: list[str] = []
    for group in ranked:
        if len(evaluation) >= target:
            break
        evaluation.extend(group)
    eval_ids = tuple(sorted(evaluation))
    eval_set = set(eval_ids)
    train_ids = tuple(event_id for event_id in event_ids if event_id not in eval_set)
    return train_ids, eval_ids


def _leakage_report(
    tasks: dict[str, AnnotationTask],
    train_ids: tuple[str, ...],
    eval_ids: tuple[str, ...],
) -> LeakageReport:
    train_entities = {tasks[event_id].entity_id for event_id in train_ids}
    eval_entities = {tasks[event_id].entity_id for event_id in eval_ids}
    train_related = {
        tasks[event_id].related_event_group
        for event_id in train_ids
        if tasks[event_id].related_event_group is not None
    }
    eval_related = {
        tasks[event_id].related_event_group
        for event_id in eval_ids
        if tasks[event_id].related_event_group is not None
    }
    entity_intersection = tuple(sorted(train_entities & eval_entities))
    related_intersection = tuple(sorted(train_related & eval_related))
    return LeakageReport(
        entity_intersection=entity_intersection,
        related_event_intersection=related_intersection,
        passed=not entity_intersection and not related_intersection,
    )


def build_dataset_release(
    tasks: tuple[AnnotationTask, ...],
    records: tuple[AnnotationRecord, ...],
    ontology: OntologyDefinition,
    policy: AnnotationPolicy,
    *,
    release_id: str,
    evidence_kind: Literal["fixture", "human"],
) -> DatasetRelease:
    if evidence_kind not in {"fixture", "human"}:
        raise ValueError("evidence_kind must be fixture or human")
    task_by_id = {task.event_id: task for task in tasks}
    if len(task_by_id) != len(tasks):
        raise ValueError("annotation task event IDs must be unique")
    resolved, agreement = _resolve_records(task_by_id, records, ontology)
    if not resolved:
        raise ValueError("at least one resolved annotation is required")
    event_ids = tuple(sorted(resolved))
    train_ids, eval_ids = _split_events(task_by_id, event_ids, policy)
    leakage = _leakage_report(task_by_id, train_ids, eval_ids)

    counts: Counter[str] = Counter()
    for record in resolved.values():
        counts.update(_signature(record))
    distribution = dict(sorted(counts.items()))
    reportable_labels = {label.event_type for label in ontology.labels}
    if "no_material_event" in distribution:
        reportable_labels.add("no_material_event")
    rare = {
        label: distribution.get(label, 0)
        for label in sorted(reportable_labels)
        if distribution.get(label, 0) < policy.rare_label_threshold
    }
    total = len(event_ids)
    all_gold = all(
        task_by_id[event_id].annotation_round == AnnotationRound.GOLD
        for event_id in event_ids
    )
    gold_size_passed = (
        policy.rounds.gold_minimum_events
        <= total
        <= policy.rounds.gold_maximum_events
        and all_gold
    )
    double_passed = (
        agreement.double_label_fraction
        >= policy.rounds.minimum_double_label_fraction
    )
    adjudication_passed = True
    contract_passed = (
        gold_size_passed
        and double_passed
        and adjudication_passed
        and leakage.passed
        and bool(train_ids)
        and bool(eval_ids)
    )
    created_at = max(record.created_at for record in records)
    annotation_ids = {
        event_id: resolved[event_id].annotation_id for event_id in event_ids
    }
    task_hashes = {
        event_id: hashlib.sha256(
            json.dumps(
                task_by_id[event_id].model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        for event_id in event_ids
    }
    ontology_hash = hashlib.sha256(
        json.dumps(
            ontology.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    policy_hash = hashlib.sha256(
        json.dumps(
            policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    payload = {
        "release_id": release_id,
        "evidence_kind": evidence_kind,
        "ontology_version": ontology.version,
        "ontology_hash": ontology_hash,
        "policy_version": policy.version,
        "policy_hash": policy_hash,
        "created_at": created_at.isoformat(),
        "train_event_ids": list(train_ids),
        "eval_event_ids": list(eval_ids),
        "annotation_ids": annotation_ids,
        "task_hashes": task_hashes,
        "agreement": agreement.model_dump(mode="json"),
        "class_distribution": distribution,
        "rare_labels": rare,
        "leakage": leakage.model_dump(mode="json"),
        "gold_size_passed": gold_size_passed,
        "double_label_coverage_passed": double_passed,
        "adjudication_passed": adjudication_passed,
        "contract_checks_passed": contract_passed,
        "stage_acceptance_passed": evidence_kind == "human" and contract_passed,
    }
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    release = DatasetRelease.model_validate(payload | {"content_hash": content_hash})
    if release.expected_content_hash() != content_hash:
        raise AssertionError("dataset release content hash is not reproducible")
    return release
