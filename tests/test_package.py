from importlib.util import find_spec


def test_financial_event_model_package_is_importable() -> None:
    assert find_spec("financial_event_model") is not None

