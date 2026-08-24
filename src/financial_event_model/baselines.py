"""Deterministic Stage 8 non-neural baselines and shared metrics."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from financial_event_model.annotation import AnnotationStore
from financial_event_model.experiments import ExperimentStore
from financial_event_model.ontology import load_ontology


_TOKEN = re.compile(r"[a-z0-9]+")
_NO_EVENT = "no_material_event"


@dataclass(frozen=True)
class BaselineExample:
    event_id: str
    text: str
    filing_type: str
    labels: tuple[str, ...]
    candidate_spans: tuple[tuple[int, int], ...] = ()
    evidence_spans: tuple[tuple[int, int], ...] = ()
    attributes: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class Prediction:
    labels: tuple[str, ...]
    material_probability: float
    evidence_spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class BaselineMetrics:
    exact_set_accuracy: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    brier_score: float
    expected_calibration_error_5_bins: float
    character_overlap_precision: float
    character_overlap_recall: float
    character_overlap_f1: float


@dataclass(frozen=True)
class AttributeMetrics:
    material_record_exact_accuracy: float
    attribute_cell_precision: float
    attribute_cell_recall: float
    attribute_cell_f1: float


def _most_frequent(examples: tuple[BaselineExample, ...]) -> tuple[str, ...]:
    counts = Counter(example.labels for example in examples)
    if not counts:
        raise ValueError("at least one training example is required")
    return min(counts, key=lambda labels: (-counts[labels], labels))


@dataclass(frozen=True)
class GlobalFrequencyBaseline:
    labels: tuple[str, ...]
    material_probability: float

    @classmethod
    def fit(cls, examples: tuple[BaselineExample, ...]) -> GlobalFrequencyBaseline:
        labels = _most_frequent(examples)
        probability = sum(bool(example.labels) for example in examples) / len(examples)
        return cls(labels=labels, material_probability=probability)

    def predict(self, example: BaselineExample) -> Prediction:
        del example
        return Prediction(labels=self.labels, material_probability=self.material_probability)


@dataclass(frozen=True)
class FilingTypeFrequencyBaseline:
    global_model: GlobalFrequencyBaseline
    by_filing_type: dict[str, GlobalFrequencyBaseline]

    @classmethod
    def fit(cls, examples: tuple[BaselineExample, ...]) -> FilingTypeFrequencyBaseline:
        global_model = GlobalFrequencyBaseline.fit(examples)
        grouped: dict[str, list[BaselineExample]] = defaultdict(list)
        for example in examples:
            grouped[example.filing_type].append(example)
        return cls(
            global_model=global_model,
            by_filing_type={
                filing_type: GlobalFrequencyBaseline.fit(tuple(group))
                for filing_type, group in grouped.items()
            },
        )

    def predict(self, example: BaselineExample) -> Prediction:
        return self.by_filing_type.get(example.filing_type, self.global_model).predict(example)


@dataclass(frozen=True)
class AttributeFrequencyBaseline:
    by_label: dict[str, dict[str, object]]

    @classmethod
    def fit(cls, examples: tuple[BaselineExample, ...]) -> AttributeFrequencyBaseline:
        counts: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        for example in examples:
            for label, attributes in example.attributes.items():
                for name, value in attributes.items():
                    counts[label][name][_attribute_value(value)] += 1
        return cls(
            by_label={
                label: {
                    name: json.loads(min(values, key=lambda value: (-values[value], value)))
                    for name, values in sorted(fields.items())
                }
                for label, fields in sorted(counts.items())
            }
        )

    def predict_for_labels(self, labels: tuple[str, ...]) -> dict[str, dict[str, object]]:
        return {
            label: dict(self.by_label.get(label, {}))
            for label in labels
        }


@dataclass(frozen=True)
class LexicalNaiveBayesBaseline:
    classes: tuple[tuple[str, ...], ...]
    class_counts: dict[tuple[str, ...], int]
    token_counts: dict[tuple[str, ...], Counter[str]]
    token_totals: dict[tuple[str, ...], int]
    vocabulary: frozenset[str]
    training_items: int
    alpha: float

    @classmethod
    def fit(
        cls,
        examples: tuple[BaselineExample, ...],
        *,
        alpha: float,
    ) -> LexicalNaiveBayesBaseline:
        if not examples:
            raise ValueError("at least one training example is required")
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        class_counts = Counter(example.labels for example in examples)
        token_counts: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        vocabulary: set[str] = set()
        for example in examples:
            tokens = _tokens(example.text)
            token_counts[example.labels].update(tokens)
            vocabulary.update(tokens)
        classes = tuple(sorted(class_counts))
        return cls(
            classes=classes,
            class_counts=dict(class_counts),
            token_counts={label_set: token_counts[label_set] for label_set in classes},
            token_totals={label_set: sum(token_counts[label_set].values()) for label_set in classes},
            vocabulary=frozenset(vocabulary),
            training_items=len(examples),
            alpha=alpha,
        )

    def predict(self, example: BaselineExample) -> Prediction:
        tokens = Counter(token for token in _tokens(example.text) if token in self.vocabulary)
        vocabulary_size = max(1, len(self.vocabulary))
        scores: dict[tuple[str, ...], float] = {}
        for label_set in self.classes:
            score = math.log(self.class_counts[label_set] / self.training_items)
            denominator = self.token_totals[label_set] + self.alpha * vocabulary_size
            for token, count in tokens.items():
                probability = (
                    self.token_counts[label_set][token] + self.alpha
                ) / denominator
                score += count * math.log(probability)
            scores[label_set] = score
        maximum = max(scores.values())
        weights = {label_set: math.exp(score - maximum) for label_set, score in scores.items()}
        total = sum(weights.values())
        probabilities = {label_set: weight / total for label_set, weight in weights.items()}
        predicted = min(self.classes, key=lambda label_set: (-probabilities[label_set], label_set))
        material_probability = sum(
            probability for label_set, probability in probabilities.items() if label_set
        )
        return Prediction(labels=predicted, material_probability=material_probability)


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN.findall(text.lower()) if len(token) >= 2)


def _metric_labels(labels: tuple[str, ...]) -> set[str]:
    return set(labels or (_NO_EVENT,))


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _attribute_value(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _attribute_cells(
    attributes: dict[str, dict[str, object]],
) -> set[tuple[str, str, str]]:
    return {
        (label, name, _attribute_value(value))
        for label, fields in attributes.items()
        for name, value in fields.items()
    }


def score_attributes(
    examples: tuple[BaselineExample, ...],
    predictions: tuple[dict[str, dict[str, object]], ...],
) -> AttributeMetrics:
    if not examples or len(examples) != len(predictions):
        raise ValueError("examples and predictions must have the same non-zero length")
    material_items = 0
    exact = 0
    truth_cells: set[tuple[int, str, str, str]] = set()
    predicted_cells: set[tuple[int, str, str, str]] = set()
    for index, (example, predicted) in enumerate(zip(examples, predictions, strict=True)):
        if example.labels:
            material_items += 1
            exact += _attribute_cells(example.attributes) == _attribute_cells(predicted)
        truth_cells.update((index, *cell) for cell in _attribute_cells(example.attributes))
        predicted_cells.update((index, *cell) for cell in _attribute_cells(predicted))
    overlap = len(truth_cells & predicted_cells)
    return AttributeMetrics(
        material_record_exact_accuracy=_ratio(exact, material_items),
        attribute_cell_precision=_ratio(overlap, len(predicted_cells)),
        attribute_cell_recall=_ratio(overlap, len(truth_cells)),
        attribute_cell_f1=_ratio(2 * overlap, len(predicted_cells) + len(truth_cells)),
    )


def evaluate_attribute_baseline(
    train: tuple[BaselineExample, ...],
    evaluation: tuple[BaselineExample, ...],
) -> dict[str, float]:
    model = AttributeFrequencyBaseline.fit(train)
    predictions = tuple(
        model.predict_for_labels(example.labels) for example in evaluation
    )
    return asdict(score_attributes(evaluation, predictions))


def score_predictions(
    examples: tuple[BaselineExample, ...],
    predictions: tuple[Prediction, ...],
) -> BaselineMetrics:
    if not examples or len(examples) != len(predictions):
        raise ValueError("examples and predictions must have the same non-zero length")
    exact = true_positive = false_positive = false_negative = 0
    brier = 0.0
    bins: list[list[tuple[float, float]]] = [[] for _ in range(5)]
    predicted_characters: set[tuple[int, int]] = set()
    true_characters: set[tuple[int, int]] = set()
    for index, (example, prediction) in enumerate(zip(examples, predictions, strict=True)):
        exact += prediction.labels == example.labels
        truth = _metric_labels(example.labels)
        predicted = _metric_labels(prediction.labels)
        true_positive += len(truth & predicted)
        false_positive += len(predicted - truth)
        false_negative += len(truth - predicted)
        actual_material = float(bool(example.labels))
        brier += (prediction.material_probability - actual_material) ** 2
        bin_index = min(int(prediction.material_probability * 5), 4)
        bins[bin_index].append((prediction.material_probability, actual_material))
        for start, end in prediction.evidence_spans:
            predicted_characters.update((index, position) for position in range(start, end))
        for start, end in example.evidence_spans:
            true_characters.update((index, position) for position in range(start, end))
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    micro_f1 = _ratio(2 * true_positive, 2 * true_positive + false_positive + false_negative)
    ece = sum(
        len(bucket)
        / len(examples)
        * abs(
            sum(probability for probability, _ in bucket) / len(bucket)
            - sum(actual for _, actual in bucket) / len(bucket)
        )
        for bucket in bins
        if bucket
    )
    overlap = len(predicted_characters & true_characters)
    evidence_precision = _ratio(overlap, len(predicted_characters))
    evidence_recall = _ratio(overlap, len(true_characters))
    evidence_f1 = _ratio(
        2 * overlap,
        len(predicted_characters) + len(true_characters),
    )
    return BaselineMetrics(
        exact_set_accuracy=exact / len(examples),
        micro_precision=precision,
        micro_recall=recall,
        micro_f1=micro_f1,
        brier_score=brier / len(examples),
        expected_calibration_error_5_bins=ece,
        character_overlap_precision=evidence_precision,
        character_overlap_recall=evidence_recall,
        character_overlap_f1=evidence_f1,
    )


def evaluate_baselines(
    train: tuple[BaselineExample, ...],
    evaluation: tuple[BaselineExample, ...],
    *,
    alpha: float,
) -> dict[str, dict[str, float]]:
    models = {
        "global_frequency": GlobalFrequencyBaseline.fit(train),
        "filing_type_frequency": FilingTypeFrequencyBaseline.fit(train),
        "lexical_naive_bayes": LexicalNaiveBayesBaseline.fit(train, alpha=alpha),
    }
    report: dict[str, dict[str, float]] = {}
    for name, model in models.items():
        predictions = []
        for example in evaluation:
            prediction = model.predict(example)
            predictions.append(
                Prediction(
                    labels=prediction.labels,
                    material_probability=prediction.material_probability,
                    evidence_spans=(example.candidate_spans if prediction.labels else ()),
                )
            )
        report[name] = asdict(score_predictions(evaluation, tuple(predictions)))
    return report


def run_stage8(
    *,
    database: str | Path,
    ontology_path: str | Path,
    config_path: str | Path,
    report_path: str | Path,
    experiment_database: str | Path,
    run_id: str,
) -> dict[str, object]:
    config_file = Path(config_path)
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    expected = config["dataset"]
    store = AnnotationStore(database, load_ontology(ontology_path))
    release = store.get_release(expected["release_id"])
    if release is None:
        raise ValueError(f"unknown frozen release: {expected['release_id']}")
    checks = {
        "content_hash": release.content_hash == expected["content_hash"],
        "evidence_kind": release.evidence_kind == expected["evidence_kind"],
        "ontology_version": release.ontology_version == expected["ontology_version"],
        "policy_version": release.policy_version == expected["policy_version"],
        "train_items": len(release.train_event_ids) == expected["train_items"],
        "evaluation_items": len(release.eval_event_ids) == expected["evaluation_items"],
        "entity_leakage": not release.leakage.entity_intersection,
        "related_event_leakage": not release.leakage.related_event_intersection,
        "evaluation_tuning_forbidden": bool(expected["evaluation_tuning_forbidden"]),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"Stage 8 frozen contract failed: {failed}")

    tasks = {task.event_id: task for task in store.list_tasks()}
    records = {
        record.annotation_id: record
        for event_id in release.annotation_ids
        for record in store.current_annotations(event_id)
    }
    examples: dict[str, BaselineExample] = {}
    for event_id, annotation_id in release.annotation_ids.items():
        task = tasks[event_id]
        try:
            record = records[annotation_id]
        except KeyError as error:
            raise ValueError(f"frozen annotation is not current: {annotation_id}") from error
        record.validate_against(store.ontology, task)
        examples[event_id] = BaselineExample(
            event_id=event_id,
            text=task.relevant_section,
            filing_type=task.filing_type,
            labels=tuple(sorted(record.labels)),
            candidate_spans=tuple((span.start, span.end) for span in task.candidate_evidence),
            evidence_spans=tuple((span.start, span.end) for span in record.evidence_spans),
            attributes=record.attributes,
        )
    train = tuple(examples[event_id] for event_id in release.train_event_ids)
    evaluation = tuple(examples[event_id] for event_id in release.eval_event_ids)
    metrics = evaluate_baselines(
        train,
        evaluation,
        alpha=float(config["baselines"]["lexical_naive_bayes"]["laplace_alpha"]),
    )
    attribute_metrics = evaluate_attribute_baseline(train, evaluation)

    experiment_store = ExperimentStore(experiment_database)
    experiment = experiment_store.get(run_id)
    expected_snapshot = {config_file.stem: config}
    if experiment is None:
        experiment = experiment_store.record(
            (config_file,),
            model_version="stage8-baselines-v0.2",
            run_id=run_id,
        )
    elif experiment.config != expected_snapshot:
        raise ValueError(f"experiment run {run_id} already has a different config")

    report: dict[str, object] = {
        "schema_version": "stage8-baselines-v0.2",
        "run_id": run_id,
        "model_version": experiment.model_version,
        "config_hash": experiment.config_hash,
        "dataset": {
            "release_id": release.release_id,
            "content_hash": release.content_hash,
            "evidence_kind": release.evidence_kind,
            "ontology_version": release.ontology_version,
            "policy_version": release.policy_version,
            "train_event_ids": list(release.train_event_ids),
            "evaluation_event_ids": list(release.eval_event_ids),
            "leakage_passed": release.leakage.passed,
        },
        "baselines": metrics,
        "attributes": {"label_conditional_frequency": attribute_metrics},
        "outcomes": config["metrics"]["outcomes"],
        "promotion": config["promotion"],
        "evaluation_tuning_performed": False,
        "human_gold_status": "frozen_pre_finalization",
    }
    output = Path(report_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(output)
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run frozen Stage 8 non-neural baselines")
    parser.add_argument("--database", default="data/labels/annotations.sqlite")
    parser.add_argument("--ontology", default="configs/ontology.yaml")
    parser.add_argument("--config", default="configs/stage8_baselines.yaml")
    parser.add_argument("--report", default="reports/stage8_baselines_v0.2.json")
    parser.add_argument("--experiment-database", default="data/experiments/experiments.sqlite3")
    parser.add_argument("--run-id", default="stage8-baselines-v0.2")
    args = parser.parse_args(argv)
    report = run_stage8(
        database=args.database,
        ontology_path=args.ontology,
        config_path=args.config,
        report_path=args.report,
        experiment_database=args.experiment_database,
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "release_id": report["dataset"]["release_id"],
                "baselines": report["baselines"],
                "report": args.report,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
