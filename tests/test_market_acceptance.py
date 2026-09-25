from pathlib import Path

import pytest
import yaml


def _write_config(tmp_path: Path, **overrides) -> Path:
    config = {
        "version": "0.1",
        "provider": "alpaca",
        "provider_feed": "sip",
        "provider_key_env": "APCA_API_KEY_ID",
        "provider_secret_env": "APCA_API_SECRET_KEY",
        "acceptance_sample_size": 100,
    }
    config.update(overrides)

    path = tmp_path / "market.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_preflight_accepts_authenticated_sip_configuration(tmp_path) -> None:
    from financial_event_model.market.acceptance import run_preflight

    config_path = _write_config(tmp_path)

    result = run_preflight(
        config_path,
        environ={
            "APCA_API_KEY_ID": "test-key",
            "APCA_API_SECRET_KEY": "test-secret",
        },
    )

    assert result.provider == "alpaca"
    assert result.feed == "sip"
    assert result.sample_size == 100
    assert result.credentials_present is True


def test_preflight_rejects_iex_for_acceptance(tmp_path) -> None:
    from financial_event_model.market.acceptance import run_preflight

    config_path = _write_config(tmp_path, provider_feed="iex")

    with pytest.raises(ValueError, match="SIP"):
        run_preflight(
            config_path,
            environ={
                "APCA_API_KEY_ID": "test-key",
                "APCA_API_SECRET_KEY": "test-secret",
            },
        )


def test_preflight_rejects_missing_credentials(tmp_path) -> None:
    from financial_event_model.market.acceptance import run_preflight

    config_path = _write_config(tmp_path)

    with pytest.raises(ValueError, match="credentials"):
        run_preflight(config_path, environ={})


def test_preflight_does_not_expose_secret_values(tmp_path) -> None:
    from financial_event_model.market.acceptance import run_preflight

    config_path = _write_config(tmp_path)

    result = run_preflight(
        config_path,
        environ={
            "APCA_API_KEY_ID": "super-secret-key",
            "APCA_API_SECRET_KEY": "super-secret-value",
        },
    )

    rendered = repr(result)

    assert "super-secret-key" not in rendered
    assert "super-secret-value" not in rendered
