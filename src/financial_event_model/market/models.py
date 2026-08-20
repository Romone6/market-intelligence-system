"""Contracts for point-in-time market observations and outcome labels."""

from datetime import date
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from financial_event_model.contracts import Contract


class MarketBar(Contract):
    security_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    session_date: date
    timestamp: AwareDatetime
    source_timestamp: AwareDatetime | None = None
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)
    adjusted_open: float = Field(gt=0)
    adjusted_high: float = Field(gt=0)
    adjusted_low: float = Field(gt=0)
    adjusted_close: float = Field(gt=0)
    adjustment_factor: float = Field(gt=0)
    trading_status: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_received_at: AwareDatetime
    source_content_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high must not be below open, low, or close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low must not exceed open, high, or close")
        if self.adjusted_high < max(
            self.adjusted_open,
            self.adjusted_low,
            self.adjusted_close,
        ):
            raise ValueError("adjusted_high is inconsistent")
        if self.adjusted_low > min(
            self.adjusted_open,
            self.adjusted_high,
            self.adjusted_close,
        ):
            raise ValueError("adjusted_low is inconsistent")
        return self


class FactorObservation(Contract):
    session_date: date
    market_excess_return: float
    smb: float
    hml: float
    risk_free_rate: float
    source: str = Field(min_length=1)
    received_at: AwareDatetime
    source_content_hash: str | None = None


class CorporateAction(Contract):
    action_id: str = Field(min_length=1)
    security_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    effective_date: date
    announced_at: AwareDatetime | None
    first_observed_at: AwareDatetime
    source: str = Field(min_length=1)
    source_content_hash: str = Field(min_length=64, max_length=64)
    source_payload: dict[str, object]


class FactorModel(Contract):
    alpha: float
    market_beta: float
    smb_beta: float
    hml_beta: float
    observations: int = Field(gt=0)
    estimation_end: date


class FilingOutcomeInput(Contract):
    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    security_id: str = Field(min_length=1)
    tradable_at: AwareDatetime
    event_count_on_start_session: int = Field(default=1, ge=1)
    earnings_overlap: bool | None = None
    macro_announcement_overlap: bool | None = None
    acquisition_overlap: bool | None = None


class ContaminationFlags(Contract):
    earnings_overlap: bool | None
    multiple_same_day_filings: bool
    macro_announcement_overlap: bool | None
    trading_halt: bool | None
    acquisition_overlap: bool | None
    low_liquidity: bool | None
    extreme_market_move: bool | None
    missing_price_data: bool
    delisting_return_missing: bool | None


class OutcomeLabel(Contract):
    event_id: str
    entity_id: str
    security_id: str
    tradable_at: AwareDatetime
    start_session: date | None
    start_price_timestamp: AwareDatetime | None
    raw_return_1d: float | None
    raw_return_5d: float | None
    raw_return_20d: float | None
    market_adjusted_return_1d: float | None
    market_adjusted_return_5d: float | None
    market_adjusted_return_20d: float | None
    sector_adjusted_return_5d: float | None
    factor_residual_return_20d: float | None
    realized_volatility_20d: float | None
    maximum_adverse_excursion_20d: float | None
    maximum_favourable_excursion_20d: float | None
    volume_abnormality_5d: float | None
    factor_model: FactorModel | None
    contamination: ContaminationFlags
    label_version: str = Field(min_length=1)
    generated_at: AwareDatetime
