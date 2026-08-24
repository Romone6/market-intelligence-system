from __future__ import annotations

import numpy as np


def test_linear_probe_handles_observed_and_constant_labels() -> None:
    from financial_event_model.stage9_probe import fit_linear_probe

    train_x = np.asarray(
        [[-3.0, 0.0], [-2.0, 0.0], [-1.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
        dtype=np.float32,
    )
    train_y = np.asarray(
        [[0, 0], [0, 0], [0, 0], [1, 0], [1, 0], [1, 0]],
        dtype=np.int64,
    )
    validation_x = np.asarray([[-2.5, 0.0], [2.5, 0.0]], dtype=np.float32)
    validation_y = np.asarray([[0, 0], [1, 0]], dtype=np.int64)

    artifact, metrics = fit_linear_probe(
        train_x,
        train_y,
        validation_x,
        validation_y,
        label_names=("material", "never_seen"),
        c=1.0,
        class_weight=None,
        threshold=0.5,
        random_seed=17,
    )

    assert artifact["heads"]["never_seen"]["kind"] == "constant"
    assert artifact["heads"]["never_seen"]["probability"] == 0.0
    assert artifact["heads"]["material"]["kind"] == "logistic"
    assert artifact["class_weight"] is None
    assert metrics["micro_f1"] == 1.0
    assert metrics["exact_set_accuracy"] == 1.0
    assert metrics["validation_positive_cells"] == 1
    assert metrics["predicted_positive_cells"] == 1


def test_linear_probe_rejects_mismatched_label_width() -> None:
    from financial_event_model.stage9_probe import fit_linear_probe

    train_x = np.zeros((2, 3), dtype=np.float32)
    train_y = np.zeros((2, 2), dtype=np.int64)
    validation_x = np.zeros((1, 3), dtype=np.float32)
    validation_y = np.zeros((1, 2), dtype=np.int64)

    try:
        fit_linear_probe(
            train_x,
            train_y,
            validation_x,
            validation_y,
            label_names=("only_one",),
            c=1.0,
            class_weight=None,
            threshold=0.5,
            random_seed=17,
        )
    except ValueError as exc:
        assert "label width" in str(exc)
    else:
        raise AssertionError("mismatched label width must fail")
