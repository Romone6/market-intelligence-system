"""Deterministic daily event-outcome generation."""

from datetime import date, datetime, timezone
from math import prod, sqrt
from statistics import mean, stdev

import numpy as np

from .models import (
    ContaminationFlags,
    FactorModel,
    FactorObservation,
    FilingOutcomeInput,
    MarketBar,
    OutcomeLabel,
)


LABEL_VERSION = "daily-outcomes-v0.1"


def estimate_factor_model(
    observations: list[tuple[date, float, float, float, float, float]],
    *,
    event_start: date,
    minimum_observations: int,
) -> FactorModel:
    eligible = [item for item in observations if item[0] < event_start][-252:]
    if len(eligible) < minimum_observations:
        raise ValueError("insufficient pre-event factor observations")
    design = np.asarray(
        [[1.0, item[2], item[3], item[4]] for item in eligible],
        dtype=float,
    )
    excess_returns = np.asarray(
        [item[1] - item[5] for item in eligible],
        dtype=float,
    )
    coefficients, _, rank, _ = np.linalg.lstsq(design, excess_returns, rcond=None)
    if rank < design.shape[1]:
        raise ValueError("pre-event factor design is rank deficient")
    return FactorModel(
        alpha=float(coefficients[0]),
        market_beta=float(coefficients[1]),
        smb_beta=float(coefficients[2]),
        hml_beta=float(coefficients[3]),
        observations=len(eligible),
        estimation_end=max(item[0] for item in eligible),
    )


def generate_outcome_label(
    event: FilingOutcomeInput,
    *,
    stock_bars: tuple[MarketBar, ...],
    benchmark_bars: tuple[MarketBar, ...],
    sector_bars: tuple[MarketBar, ...],
    factors: tuple[FactorObservation, ...],
    minimum_factor_observations: int = 120,
    low_liquidity_threshold: float = 5_000_000,
    extreme_market_threshold: float = 0.03,
) -> OutcomeLabel:
    ordered_stock = tuple(sorted(stock_bars, key=lambda bar: bar.timestamp))
    outcome = tuple(bar for bar in ordered_stock if bar.timestamp >= event.tradable_at)
    prior = tuple(bar for bar in ordered_stock if bar.timestamp < event.tradable_at)
    if not outcome:
        return _empty_label(event)
    start = outcome[0]
    sessions = tuple(bar.session_date for bar in outcome[:20])
    raw = {horizon: _security_return(outcome, horizon) for horizon in (1, 5, 20)}
    benchmark = {
        horizon: _aligned_return(benchmark_bars, sessions, horizon)
        for horizon in (1, 5, 20)
    }
    sector_5d = _aligned_return(sector_bars, sessions, 5)
    daily_returns = _daily_event_returns(outcome[:20])
    factor_by_date = {item.session_date: item for item in factors}
    factor_model = _fit_pre_event_model(
        ordered_stock,
        factor_by_date,
        start.session_date,
        minimum_factor_observations,
    )
    factor_residual = _factor_residual_return(
        outcome[:20],
        factor_by_date,
        factor_model,
    )
    prior_liquidity = prior[-20:]
    average_dollar_volume = (
        mean(bar.adjusted_close * bar.volume for bar in prior_liquidity)
        if prior_liquidity
        else None
    )
    volume_abnormality = None
    if len(outcome) >= 5 and prior_liquidity:
        prior_volume = mean(bar.volume for bar in prior_liquidity)
        if prior_volume > 0:
            volume_abnormality = mean(bar.volume for bar in outcome[:5]) / prior_volume - 1
    missing = (
        len(outcome) < 20
        or any(benchmark[horizon] is None for horizon in (1, 5, 20))
        or sector_5d is None
    )
    return OutcomeLabel(
        event_id=event.event_id,
        entity_id=event.entity_id,
        security_id=event.security_id,
        tradable_at=event.tradable_at,
        start_session=start.session_date,
        start_price_timestamp=start.timestamp,
        raw_return_1d=raw[1],
        raw_return_5d=raw[5],
        raw_return_20d=raw[20],
        market_adjusted_return_1d=_difference(raw[1], benchmark[1]),
        market_adjusted_return_5d=_difference(raw[5], benchmark[5]),
        market_adjusted_return_20d=_difference(raw[20], benchmark[20]),
        sector_adjusted_return_5d=_difference(raw[5], sector_5d),
        factor_residual_return_20d=factor_residual,
        realized_volatility_20d=(
            stdev(daily_returns) * sqrt(252) if len(daily_returns) >= 2 else None
        ),
        maximum_adverse_excursion_20d=(
            min(_excursion_returns(outcome[:20], adverse=True)) if outcome else None
        ),
        maximum_favourable_excursion_20d=(
            max(_excursion_returns(outcome[:20], adverse=False)) if outcome else None
        ),
        volume_abnormality_5d=volume_abnormality,
        factor_model=factor_model,
        contamination=ContaminationFlags(
            earnings_overlap=event.earnings_overlap,
            multiple_same_day_filings=event.event_count_on_start_session > 1,
            macro_announcement_overlap=event.macro_announcement_overlap,
            trading_halt=_trading_halt(outcome[:20]),
            acquisition_overlap=event.acquisition_overlap,
            low_liquidity=(
                average_dollar_volume < low_liquidity_threshold
                if average_dollar_volume is not None
                else None
            ),
            extreme_market_move=(
                abs(benchmark[1]) >= extreme_market_threshold
                if benchmark[1] is not None
                else None
            ),
            missing_price_data=missing,
            delisting_return_missing=None,
        ),
        label_version=LABEL_VERSION,
        generated_at=datetime.now(timezone.utc),
    )


def _fit_pre_event_model(
    bars: tuple[MarketBar, ...],
    factors: dict[date, FactorObservation],
    event_start: date,
    minimum: int,
) -> FactorModel | None:
    observations = []
    for previous, current in zip(bars, bars[1:]):
        factor = factors.get(current.session_date)
        if current.session_date >= event_start or factor is None:
            continue
        observations.append(
            (
                current.session_date,
                current.adjusted_close / previous.adjusted_close - 1,
                factor.market_excess_return,
                factor.smb,
                factor.hml,
                factor.risk_free_rate,
            )
        )
    try:
        return estimate_factor_model(
            observations,
            event_start=event_start,
            minimum_observations=minimum,
        )
    except ValueError:
        return None


def _factor_residual_return(
    bars: tuple[MarketBar, ...],
    factors: dict[date, FactorObservation],
    model: FactorModel | None,
) -> float | None:
    if model is None or len(bars) < 20:
        return None
    daily = _daily_event_returns(bars[:20])
    residuals = []
    for bar, actual in zip(bars[:20], daily):
        factor = factors.get(bar.session_date)
        if factor is None:
            return None
        predicted_excess = (
            model.alpha
            + model.market_beta * factor.market_excess_return
            + model.smb_beta * factor.smb
            + model.hml_beta * factor.hml
        )
        residuals.append(actual - factor.risk_free_rate - predicted_excess)
    return prod(1 + residual for residual in residuals) - 1


def _security_return(bars: tuple[MarketBar, ...], horizon: int) -> float | None:
    if len(bars) < horizon:
        return None
    return bars[horizon - 1].adjusted_close / bars[0].adjusted_open - 1


def _aligned_return(
    bars: tuple[MarketBar, ...],
    sessions: tuple[date, ...],
    horizon: int,
) -> float | None:
    if len(sessions) < horizon:
        return None
    by_date = {bar.session_date: bar for bar in bars}
    selected = [by_date.get(session) for session in sessions[:horizon]]
    if any(bar is None for bar in selected):
        return None
    first = selected[0]
    last = selected[-1]
    assert first is not None and last is not None
    return last.adjusted_close / first.adjusted_open - 1


def _daily_event_returns(bars: tuple[MarketBar, ...]) -> list[float]:
    if not bars:
        return []
    returns = [bars[0].adjusted_close / bars[0].adjusted_open - 1]
    returns.extend(
        current.adjusted_close / previous.adjusted_close - 1
        for previous, current in zip(bars, bars[1:])
    )
    return returns


def _excursion_returns(
    bars: tuple[MarketBar, ...],
    *,
    adverse: bool,
) -> list[float]:
    if not bars:
        return []
    start = bars[0].adjusted_open
    return [
        (bar.adjusted_low if adverse else bar.adjusted_high) / start - 1
        for bar in bars
    ]


def _difference(left: float | None, right: float | None) -> float | None:
    return left - right if left is not None and right is not None else None


def _trading_halt(bars: tuple[MarketBar, ...]) -> bool | None:
    statuses = {bar.trading_status for bar in bars}
    if "halted" in statuses:
        return True
    if statuses == {"normal"}:
        return False
    return None


def _empty_label(event: FilingOutcomeInput) -> OutcomeLabel:
    return OutcomeLabel(
        event_id=event.event_id,
        entity_id=event.entity_id,
        security_id=event.security_id,
        tradable_at=event.tradable_at,
        start_session=None,
        start_price_timestamp=None,
        raw_return_1d=None,
        raw_return_5d=None,
        raw_return_20d=None,
        market_adjusted_return_1d=None,
        market_adjusted_return_5d=None,
        market_adjusted_return_20d=None,
        sector_adjusted_return_5d=None,
        factor_residual_return_20d=None,
        realized_volatility_20d=None,
        maximum_adverse_excursion_20d=None,
        maximum_favourable_excursion_20d=None,
        volume_abnormality_5d=None,
        factor_model=None,
        contamination=ContaminationFlags(
            earnings_overlap=event.earnings_overlap,
            multiple_same_day_filings=event.event_count_on_start_session > 1,
            macro_announcement_overlap=event.macro_announcement_overlap,
            trading_halt=None,
            acquisition_overlap=event.acquisition_overlap,
            low_liquidity=None,
            extreme_market_move=None,
            missing_price_data=True,
            delisting_return_missing=None,
        ),
        label_version=LABEL_VERSION,
        generated_at=datetime.now(timezone.utc),
    )
