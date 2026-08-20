"""Daily market ingestion and reproducible outcome labels."""

from .alpaca import AlpacaDailyBarCollector
from .factors import (
    FRENCH_DAILY_URL,
    FrenchFactorCollector,
    parse_french_daily_factors,
    parse_french_factor_archive,
)
from .models import (
    ContaminationFlags,
    CorporateAction,
    FactorModel,
    FactorObservation,
    FilingOutcomeInput,
    MarketBar,
    OutcomeLabel,
)
from .outcomes import estimate_factor_model, generate_outcome_label
from .store import MarketStore

__all__ = [
    "AlpacaDailyBarCollector",
    "ContaminationFlags",
    "CorporateAction",
    "FRENCH_DAILY_URL",
    "FactorModel",
    "FactorObservation",
    "FilingOutcomeInput",
    "FrenchFactorCollector",
    "MarketBar",
    "MarketStore",
    "OutcomeLabel",
    "estimate_factor_model",
    "generate_outcome_label",
    "parse_french_daily_factors",
    "parse_french_factor_archive",
]
