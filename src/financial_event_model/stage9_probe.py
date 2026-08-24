"""Frozen-encoder Stage 9 multilabel linear probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression

from financial_event_model.ontology import load_ontology
from financial_event_model.stage9_tokenization import format_primary_input


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def fit_linear_probe(
    train_x: np.ndarray,
    train_y: np.ndarray,
    validation_x: np.ndarray,
    validation_y: np.ndarray,
    *,
    label_names: tuple[str, ...],
    c: float,
    class_weight: str | None,
    threshold: float,
    random_seed: int,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Fit independent deterministic binary heads and score validation once."""
    if train_x.ndim != 2 or validation_x.ndim != 2:
        raise ValueError("probe features must be rank-two matrices")
    if train_y.ndim != 2 or validation_y.ndim != 2:
        raise ValueError("probe targets must be rank-two matrices")
    if train_y.shape[1] != len(label_names) or validation_y.shape[1] != len(label_names):
        raise ValueError("target label width does not match label names")
    if train_x.shape[1] != validation_x.shape[1]:
        raise ValueError("fit and validation feature widths differ")

    probabilities = np.zeros(validation_y.shape, dtype=np.float64)
    heads: dict[str, Any] = {}
    for index, label in enumerate(label_names):
        target = train_y[:, index]
        classes = np.unique(target)
        if len(classes) == 1:
            probability = float(classes[0])
            probabilities[:, index] = probability
            heads[label] = {"kind": "constant", "probability": probability}
            continue
        classifier = LogisticRegression(
            C=c,
            penalty="l2",
            solver="liblinear",
            class_weight=class_weight,
            random_state=random_seed,
            max_iter=1000,
        )
        classifier.fit(train_x, target)
        probabilities[:, index] = classifier.predict_proba(validation_x)[:, 1]
        heads[label] = {
            "kind": "logistic",
            "classes": classifier.classes_.astype(int).tolist(),
            "coefficient": classifier.coef_[0].astype(float).tolist(),
            "intercept": float(classifier.intercept_[0]),
        }

    predicted = (probabilities >= threshold).astype(np.int64)
    true_positive = int(np.logical_and(predicted == 1, validation_y == 1).sum())
    false_positive = int(np.logical_and(predicted == 1, validation_y == 0).sum())
    false_negative = int(np.logical_and(predicted == 0, validation_y == 1).sum())
    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    metrics = {
        "exact_set_accuracy": float(np.all(predicted == validation_y, axis=1).mean()),
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": _safe_divide(2 * true_positive, 2 * true_positive + false_positive + false_negative),
        "label_cell_brier": float(np.mean((probabilities - validation_y) ** 2)),
        "validation_positive_cells": int(validation_y.sum()),
        "predicted_positive_cells": int(predicted.sum()),
        "true_positive_cells": true_positive,
        "false_positive_cells": false_positive,
        "false_negative_cells": false_negative,
        "maximum_probability": float(probabilities.max(initial=0.0)),
        "maximum_positive_target_probability": float(
            probabilities[validation_y == 1].max(initial=0.0)
        ),
    }
    artifact = {
        "schema_version": "stage9-linear-probe-v0.2",
        "feature_width": int(train_x.shape[1]),
        "labels": list(label_names),
        "c": c,
        "class_weight": class_weight,
        "threshold": threshold,
        "random_seed": random_seed,
        "heads": heads,
    }
    return artifact, metrics


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _embed_rows(
    rows: list[dict[str, Any]],
    *,
    model_dir: Path,
    max_length: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    import torch
    from transformers import AutoModel, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("Stage 9 probe requires a CUDA-enabled PyTorch build")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, use_fast=True)
    model = AutoModel.from_pretrained(model_dir, local_files_only=True).eval().cuda()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    torch.cuda.reset_peak_memory_stats()
    vectors = []
    token_lengths = []
    started = time.perf_counter()
    with torch.inference_mode():
        for row in rows:
            primary, _ = format_primary_input(row["input"])
            encoded = tokenizer(
                primary,
                text_pair=row["input"].get("prior_company_disclosure") or None,
                max_length=max_length,
                truncation=True,
                return_tensors="pt",
            )
            token_lengths.append(int(encoded["input_ids"].shape[1]))
            encoded = {name: value.cuda() for name, value in encoded.items()}
            output = model(**encoded)
            vectors.append(output.last_hidden_state[0, 0].float().cpu().numpy())
    stats = {
        "device": torch.cuda.get_device_name(0),
        "records": len(rows),
        "maximum_tokens": max(token_lengths, default=0),
        "peak_allocated_vram_mib": round(torch.cuda.max_memory_allocated() / 1024 / 1024, 2),
        "seconds": round(time.perf_counter() - started, 2),
    }
    return np.asarray(vectors, dtype=np.float32), stats


def run_stage9_probe(
    *,
    config_path: str | Path,
    ontology_path: str | Path,
    data_dir: str | Path,
    model_dir: str | Path,
    artifact_path: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    data_root = Path(data_dir)
    manifest = json.loads((data_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["package_hash"] != config["data"]["package_hash"]:
        raise ValueError("Stage 9 package hash does not match the model config")
    weights = config["base_encoder"]["weights"]["model.safetensors"]
    weight_path = Path(model_dir) / "model.safetensors"
    if weight_path.stat().st_size != weights["bytes"] or _sha256(weight_path) != weights["sha256"]:
        raise ValueError("frozen ModernBERT weight file failed provenance validation")

    train_rows = _load_jsonl(data_root / "train.jsonl")
    validation_rows = _load_jsonl(data_root / "validation.jsonl")
    if len(train_rows) != config["data"]["fit_items"] or len(validation_rows) != config["data"]["validation_items"]:
        raise ValueError("Stage 9 development split counts drifted")
    labels = tuple(sorted(item.event_type for item in load_ontology(ontology_path).labels))
    label_index = {label: index for index, label in enumerate(labels)}

    all_rows = train_rows + validation_rows
    features, embedding_stats = _embed_rows(
        all_rows,
        model_dir=Path(model_dir),
        max_length=int(config["tokenizer"]["max_length"]),
    )
    targets = np.zeros((len(all_rows), len(labels)), dtype=np.int64)
    for row_index, row in enumerate(all_rows):
        for label in row["target"]["labels"]:
            targets[row_index, label_index[label]] = 1
    split_at = len(train_rows)
    probe = config["linear_probe"]
    artifact, metrics = fit_linear_probe(
        features[:split_at],
        targets[:split_at],
        features[split_at:],
        targets[split_at:],
        label_names=labels,
        c=float(probe["c"]),
        class_weight=probe.get("class_weight"),
        threshold=float(probe["threshold"]),
        random_seed=int(probe["random_seed"]),
    )
    artifact.update(
        {
            "data_package_hash": manifest["package_hash"],
            "encoder_revision": config["base_encoder"]["revision"],
            "weights_sha256": weights["sha256"],
        }
    )
    artifact_target = Path(artifact_path)
    artifact_target.parent.mkdir(parents=True, exist_ok=True)
    artifact_target.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "schema_version": "stage9-linear-probe-report-v0.2",
        "development_only": True,
        "release_evaluation_labels_read": False,
        "fit_items": len(train_rows),
        "validation_items": len(validation_rows),
        "metrics": metrics,
        "embedding": embedding_stats,
        "artifact_sha256": _sha256(artifact_target),
    }
    report_target = Path(report_path)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the frozen Stage 9 linear probe")
    parser.add_argument("--config", default="configs/stage9_model.yaml")
    parser.add_argument("--ontology", default="configs/ontology.yaml")
    parser.add_argument("--data-dir", default="data/model/stage9-development-v0.1")
    parser.add_argument("--model-dir", default="models/provenance/modernbert-base-8949b909ec90")
    parser.add_argument("--artifact", default="models/checkpoints/stage9-linear-probe-v0.2.json")
    parser.add_argument("--report", default="reports/stage9_linear_probe_v0.2.json")
    args = parser.parse_args(argv)
    report = run_stage9_probe(
        config_path=args.config,
        ontology_path=args.ontology,
        data_dir=args.data_dir,
        model_dir=args.model_dir,
        artifact_path=args.artifact,
        report_path=args.report,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
