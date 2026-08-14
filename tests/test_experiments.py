import hashlib
import json

import pytest


def test_experiment_store_persists_exact_configuration_snapshot(tmp_path) -> None:
    from financial_event_model.experiments import ExperimentStore

    universe = tmp_path / "universe.yaml"
    universe.write_text("version: '0.1'\nfrequency: daily\n", encoding="utf-8")
    training = tmp_path / "training.yaml"
    training.write_text("seed: 42\nmode: research\n", encoding="utf-8")

    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    recorded = store.record(
        [universe, training],
        model_version="baseline-v0.1",
        run_id="run_0001",
    )
    loaded = store.get("run_0001")

    expected_config = {
        "training": {"mode": "research", "seed": 42},
        "universe": {"frequency": "daily", "version": "0.1"},
    }
    expected_json = json.dumps(expected_config, sort_keys=True, separators=(",", ":"))

    assert loaded == recorded
    assert loaded is not None
    assert loaded.config == expected_config
    assert loaded.config_hash == hashlib.sha256(expected_json.encode()).hexdigest()
    assert loaded.model_version == "baseline-v0.1"


def test_experiment_store_rejects_a_run_without_configuration(tmp_path) -> None:
    from financial_event_model.experiments import ExperimentStore

    store = ExperimentStore(tmp_path / "experiments.sqlite3")

    with pytest.raises(ValueError, match="at least one configuration"):
        store.record([], model_version="baseline-v0.1")
