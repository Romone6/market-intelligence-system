"""Sealed Stage 9 development-package construction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from financial_event_model.annotation import (
    AnnotationStore,
    leakage_report,
    split_event_ids,
    task_content_hash,
)
from financial_event_model.ontology import load_ontology


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(path)


def run_stage9_data_prep(
    *,
    database: str | Path,
    ontology_path: str | Path,
    config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, object]:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    expected = config["dataset"]
    store = AnnotationStore(database, load_ontology(ontology_path))
    release = store.get_release(expected["release_id"])
    if release is None:
        raise ValueError(f"unknown frozen release: {expected['release_id']}")
    checks = {
        "content_hash": release.content_hash == expected["content_hash"],
        "evidence_kind": release.evidence_kind == expected["evidence_kind"],
        "development_items": len(release.train_event_ids) == expected["development_items"],
        "sealed_evaluation_items": len(release.eval_event_ids)
        == expected["sealed_evaluation_items"],
        "evaluation_labels_sealed": not config["evaluation"]["labels_read_during_packaging"],
        "evaluation_tuning_forbidden": bool(config["evaluation"]["tuning_forbidden"]),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"Stage 9 data contract failed: {failed}")

    tasks = {}
    for event_id in release.train_event_ids:
        task = store.get_task(event_id)
        if task is None:
            raise ValueError(f"release task is missing: {event_id}")
        if task_content_hash(task) != release.task_hashes[event_id]:
            raise ValueError(f"release task hash drifted: {event_id}")
        tasks[event_id] = task

    split = config["development_split"]
    train_ids, validation_ids = split_event_ids(
        tasks,
        release.train_event_ids,
        evaluation_fraction=float(split["validation_fraction"]),
        split_seed=str(split["split_seed"]),
    )
    leakage = leakage_report(tasks, train_ids, validation_ids)
    if not leakage.passed:
        raise ValueError("Stage 9 internal split leaked an entity or related event")

    rows = {}
    for event_id in release.train_event_ids:
        annotation_id = release.annotation_ids[event_id]
        record = next(
            (
                item
                for item in store.current_annotations(event_id)
                if item.annotation_id == annotation_id
            ),
            None,
        )
        if record is None:
            raise ValueError(f"frozen annotation is not current: {annotation_id}")
        task = tasks[event_id]
        record.validate_against(store.ontology, task)
        rows[event_id] = {
            "schema_version": "stage9-development-example-v0.1",
            "event_id": event_id,
            "task_hash": release.task_hashes[event_id],
            "input": {
                "text": task.relevant_section,
                "filing_type": task.filing_type,
                "prior_company_disclosure": task.prior_company_disclosure,
                "source_published_at": task.source_published_at.isoformat(),
                "tradable_at": task.tradable_at.isoformat(),
            },
            "target": {
                "no_material_event": record.no_material_event,
                "labels": list(record.labels),
                "attributes": record.attributes,
                "evidence_spans": [
                    span.model_dump(mode="json") for span in record.evidence_spans
                ],
                "ambiguity_flag": record.ambiguity_flag,
            },
        }

    output = Path(output_dir)
    split_payloads = {}
    for name, event_ids in (("train", train_ids), ("validation", validation_ids)):
        payload = "".join(_canonical_json(rows[event_id]) + "\n" for event_id in event_ids)
        _atomic_write(output / f"{name}.jsonl", payload)
        split_payloads[name] = {"items": len(event_ids), "sha256": hashlib.sha256(payload.encode()).hexdigest()}

    manifest: dict[str, object] = {
        "schema_version": "stage9-development-package-v0.1",
        "release": {
            "release_id": release.release_id,
            "content_hash": release.content_hash,
            "evidence_kind": release.evidence_kind,
        },
        "development_split": {
            "split_seed": split["split_seed"],
            "validation_fraction": split["validation_fraction"],
            "train_event_ids": list(train_ids),
            "validation_event_ids": list(validation_ids),
            "files": split_payloads,
        },
        "sealed_evaluation": {
            "items": len(release.eval_event_ids),
            "membership_sha256": _hash(list(release.eval_event_ids)),
            "labels_read": False,
            "tuning_forbidden": True,
        },
        "leakage": leakage.model_dump(mode="json"),
    }
    manifest["package_hash"] = _hash(manifest)
    _atomic_write(output / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the sealed Stage 9 development package")
    parser.add_argument("--database", default="data/labels/annotations.sqlite")
    parser.add_argument("--ontology", default="configs/ontology.yaml")
    parser.add_argument("--config", default="configs/stage9_data.yaml")
    parser.add_argument("--output-dir", default="data/model/stage9-development-v0.1")
    args = parser.parse_args(argv)
    manifest = run_stage9_data_prep(
        database=args.database,
        ontology_path=args.ontology,
        config_path=args.config,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
