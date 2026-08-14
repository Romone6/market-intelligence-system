from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_stage_zero_directories_and_execution_gate_exist() -> None:
    expected_directories = {
        "data/raw",
        "data/normalized",
        "data/events",
        "data/labels",
        "data/market",
        "models/checkpoints",
        "models/calibration",
        "reports",
        "notebooks",
        "src/financial_event_model/ingestion",
        "src/financial_event_model/normalization",
        "src/financial_event_model/identifiers",
        "src/financial_event_model/ontology",
        "src/financial_event_model/annotation",
        "src/financial_event_model/labeling",
        "src/financial_event_model/training",
        "src/financial_event_model/evaluation",
        "src/financial_event_model/inference",
    }

    missing = sorted(path for path in expected_directories if not (ROOT / path).is_dir())
    assert missing == []

    training = yaml.safe_load((ROOT / "configs/training.yaml").read_text(encoding="utf-8"))
    assert training["execution"] == {
        "broker_enabled": False,
        "live_trading_enabled": False,
        "paper_only": True,
    }


def test_notebooks_cannot_be_the_only_home_of_business_logic() -> None:
    assert list((ROOT / "notebooks").glob("*.ipynb")) == []

