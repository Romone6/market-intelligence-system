"""Fail-closed preflight for the Stage 5 real-market acceptance run."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml


@dataclass(frozen=True)
class MarketAcceptancePreflight:
    """Non-secret summary of Stage 5 live-run prerequisites."""

    provider: str
    feed: str
    sample_size: int
    credentials_present: bool


def _load_config(path: str | Path) -> dict[str, object]:
    config_path = Path(path)

    if not config_path.is_file():
        raise ValueError(f"market config does not exist: {config_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("market config must contain a mapping")

    return payload


def run_preflight(
    config_path: str | Path = "configs/market.yaml",
    *,
    environ: Mapping[str, str] | None = None,
) -> MarketAcceptancePreflight:
    """Validate Stage 5 live prerequisites without performing network requests."""

    config = _load_config(config_path)
    environment = os.environ if environ is None else environ

    provider = str(config.get("provider", "")).strip().lower()
    feed = str(config.get("provider_feed", "")).strip().lower()

    if provider != "alpaca":
        raise ValueError(
            "Stage 5 acceptance currently supports only the Alpaca provider"
        )

    if feed != "sip":
        raise ValueError(
            "Stage 5 acceptance requires consolidated Alpaca SIP market data"
        )

    key_env = str(config.get("provider_key_env", "")).strip()
    secret_env = str(config.get("provider_secret_env", "")).strip()

    if not key_env or not secret_env:
        raise ValueError(
            "market config must define credential environment variable names"
        )

    api_key = environment.get(key_env, "").strip()
    api_secret = environment.get(secret_env, "").strip()

    if not api_key or not api_secret:
        raise ValueError(
            f"Alpaca credentials are missing; set {key_env} and {secret_env}"
        )

    try:
        sample_size = int(config.get("acceptance_sample_size", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("acceptance_sample_size must be an integer") from error

    if sample_size <= 0:
        raise ValueError("acceptance_sample_size must be positive")

    return MarketAcceptancePreflight(
        provider=provider,
        feed=feed,
        sample_size=sample_size,
        credentials_present=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Stage 5 market acceptance prerequisites."
    )
    parser.add_argument(
        "--config",
        default="configs/market.yaml",
        help="Path to the market configuration file.",
    )
    args = parser.parse_args(argv)

    try:
        result = run_preflight(args.config)
    except ValueError as error:
        print(f"STAGE 5 PREFLIGHT: FAIL — {error}", file=sys.stderr)
        return 2

    print("STAGE 5 PREFLIGHT: PASS")
    print(f"provider: {result.provider}")
    print(f"feed: {result.feed}")
    print(f"acceptance sample size: {result.sample_size}")
    print("credentials: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
