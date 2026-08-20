import io
import json
import sqlite3
import zipfile
from datetime import date, datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError


UTC = timezone.utc


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode()
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeOpener:
    def __init__(self, *payloads: dict) -> None:
        self.responses = [FakeResponse(payload) for payload in payloads]
        self.requests = []

    def __call__(self, request, timeout: float):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


def _bar(
    session: date,
    close: float,
    *,
    security_id: str = "security_stock",
    open_price: float | None = None,
    volume: int = 1_000,
):
    from financial_event_model.market import MarketBar

    opening = close if open_price is None else open_price
    timestamp = datetime.combine(session, datetime.min.time(), UTC) + timedelta(
        hours=14, minutes=30
    )
    return MarketBar(
        security_id=security_id,
        symbol=security_id.removeprefix("security_").upper(),
        session_date=session,
        timestamp=timestamp,
        open=opening,
        high=max(opening, close) * 1.01,
        low=min(opening, close) * 0.99,
        close=close,
        volume=volume,
        adjusted_open=opening,
        adjusted_high=max(opening, close) * 1.01,
        adjusted_low=min(opening, close) * 0.99,
        adjusted_close=close,
        adjustment_factor=1.0,
        trading_status="normal",
        source="fixture",
        source_received_at=datetime(2026, 8, 20, tzinfo=UTC),
        source_content_hash="f" * 64,
    )


def test_market_bar_rejects_inconsistent_ohlc_ranges() -> None:
    from financial_event_model.market import MarketBar

    with pytest.raises(ValidationError, match="high"):
        MarketBar(
            security_id="security_stock",
            symbol="STOCK",
            session_date=date(2024, 1, 2),
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
            open=10.0,
            high=9.0,
            low=8.0,
            close=9.5,
            volume=100,
            adjusted_open=10.0,
            adjusted_high=10.1,
            adjusted_low=8.0,
            adjusted_close=9.5,
            adjustment_factor=1.0,
            trading_status="normal",
            source="fixture",
            source_received_at=datetime(2026, 8, 20, tzinfo=UTC),
            source_content_hash="f" * 64,
        )


def test_market_bar_requires_source_content_provenance() -> None:
    from financial_event_model.market import MarketBar

    with pytest.raises(ValidationError, match="source_content_hash"):
        MarketBar(
            security_id="security_stock",
            symbol="STOCK",
            session_date=date(2024, 1, 2),
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
            open=10.0,
            high=11.0,
            low=9.0,
            close=10.0,
            volume=100,
            adjusted_open=10.0,
            adjusted_high=11.0,
            adjusted_low=9.0,
            adjusted_close=10.0,
            adjustment_factor=1.0,
            trading_status="normal",
            source="fixture",
            source_received_at=datetime(2026, 8, 20, tzinfo=UTC),
        )


def test_market_store_is_idempotent_queryable_and_reversible(tmp_path) -> None:
    from financial_event_model.market import MarketStore

    database = tmp_path / "market.sqlite3"
    store = MarketStore(database)
    bars = (
        _bar(date(2024, 1, 3), 101.0),
        _bar(date(2024, 1, 2), 100.0),
    )

    store.put_bars(bars)
    store.put_bars(bars)

    assert [bar.session_date for bar in store.bars("security_stock")] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
    ]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0] == 2
    down = (
        Path(__file__).parents[1]
        / "src"
        / "financial_event_model"
        / "market"
        / "migrations"
        / "0001_market_data.down.sql"
    ).read_text(encoding="utf-8")
    with store._connect() as connection:
        connection.executescript(down)
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_bars'"
        ).fetchone()
    assert table is None


def test_corporate_action_history_is_filtered_by_observation_time(tmp_path) -> None:
    from financial_event_model.market import CorporateAction, MarketStore

    store = MarketStore(tmp_path / "market.sqlite3")
    action = CorporateAction(
        action_id="split_1",
        security_id="security_stock",
        symbol="STOCK",
        action_type="forward_split",
        effective_date=date(2024, 6, 10),
        announced_at=None,
        first_observed_at=datetime(2024, 5, 1, 12, 0, tzinfo=UTC),
        source="fixture",
        source_content_hash="a" * 64,
        source_payload={"ratio": "4:1"},
    )
    store.put_corporate_actions((action,))

    assert store.corporate_actions(
        "security_stock", as_of=datetime(2024, 4, 30, 23, 59, tzinfo=UTC)
    ) == ()
    assert store.corporate_actions(
        "security_stock", as_of=datetime(2024, 5, 1, 12, 0, tzinfo=UTC)
    ) == (action,)


def test_alpaca_collector_authenticates_paginates_and_pairs_adjustments(tmp_path) -> None:
    from financial_event_model.market import AlpacaDailyBarCollector, MarketStore

    raw_one = {
        "bars": {
            "AAPL": [
                {"t": "2024-01-02T05:00:00Z", "o": 100, "h": 110, "l": 95, "c": 108, "v": 1_000}
            ]
        },
        "next_page_token": "raw-next",
    }
    raw_two = {
        "bars": {
            "AAPL": [
                {"t": "2024-01-03T05:00:00Z", "o": 108, "h": 112, "l": 107, "c": 110, "v": 1_200}
            ]
        },
        "next_page_token": None,
    }
    adjusted_one = {
        "bars": {
            "AAPL": [
                {"t": "2024-01-02T05:00:00Z", "o": 50, "h": 55, "l": 47.5, "c": 54, "v": 2_000}
            ]
        },
        "next_page_token": "adjusted-next",
    }
    adjusted_two = {
        "bars": {
            "AAPL": [
                {"t": "2024-01-03T05:00:00Z", "o": 54, "h": 56, "l": 53.5, "c": 55, "v": 2_400}
            ]
        },
        "next_page_token": None,
    }
    opener = FakeOpener(raw_one, raw_two, adjusted_one, adjusted_two)
    store = MarketStore(tmp_path / "market.sqlite3")
    collector = AlpacaDailyBarCollector(
        api_key="key-id",
        api_secret="secret",
        raw_root=tmp_path / "raw",
        store=store,
        open_url=opener,
    )

    bars = collector.collect(
        symbols={"AAPL": "security_apple"},
        start=date(2024, 1, 1),
        end=date(2024, 1, 4),
        feed="sip",
    )

    assert len(bars) == 2
    assert bars[0].open == 100
    assert bars[0].adjusted_close == 54
    assert bars[0].adjustment_factor == pytest.approx(0.5)
    assert bars[0].session_date == date(2024, 1, 2)
    assert all(request.get_header("Apca-api-key-id") == "key-id" for request, _ in opener.requests)
    assert all(request.get_header("Apca-api-secret-key") == "secret" for request, _ in opener.requests)
    queries = [parse_qs(urlparse(request.full_url).query) for request, _ in opener.requests]
    assert [query["adjustment"][0] for query in queries] == ["raw", "raw", "all", "all"]
    assert queries[1]["page_token"] == ["raw-next"]
    assert queries[3]["page_token"] == ["adjusted-next"]
    assert len(tuple((tmp_path / "raw").rglob("*.json"))) == 4
    assert len(store.bars("security_apple")) == 2


def test_alpaca_collector_rejects_missing_credentials(tmp_path) -> None:
    from financial_event_model.market import AlpacaDailyBarCollector, MarketStore

    with pytest.raises(ValueError, match="credentials"):
        AlpacaDailyBarCollector(
            api_key="",
            api_secret="",
            raw_root=tmp_path / "raw",
            store=MarketStore(tmp_path / "market.sqlite3"),
        )


def test_alpaca_corporate_action_collector_preserves_source_payload(tmp_path) -> None:
    from financial_event_model.market import AlpacaDailyBarCollector, MarketStore

    opener = FakeOpener(
        {
            "corporate_actions": {
                "forward_splits": [
                    {
                        "id": "split_1",
                        "symbol": "AAPL",
                        "ex_date": "2024-06-10",
                        "process_date": "2024-06-07",
                        "old_rate": "1",
                        "new_rate": "4",
                    }
                ]
            },
            "next_page_token": None,
        }
    )
    store = MarketStore(tmp_path / "market.sqlite3")
    collector = AlpacaDailyBarCollector(
        api_key="key-id",
        api_secret="secret",
        raw_root=tmp_path / "raw",
        store=store,
        open_url=opener,
    )

    actions = collector.collect_corporate_actions(
        symbols={"AAPL": "security_apple"},
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
    )

    assert len(actions) == 1
    assert actions[0].action_type == "forward_split"
    assert actions[0].effective_date == date(2024, 6, 10)
    assert actions[0].source_payload["new_rate"] == "4"
    assert store.corporate_actions(
        "security_apple", as_of=datetime(2027, 1, 1, tzinfo=UTC)
    ) == actions


def test_french_factor_parser_converts_percent_to_decimal() -> None:
    from financial_event_model.market import parse_french_daily_factors

    csv_text = b"""Notes\n,Mkt-RF,SMB,HML,RF\n20240102, 0.50,-0.10,0.20,0.01\n20240103,-1.00, 0.30,0.40,0.02\n Annual Factors: January-December\n"""

    factors = parse_french_daily_factors(
        csv_text,
        source="ken_french_daily_3",
        received_at=datetime(2026, 8, 20, tzinfo=UTC),
    )

    assert factors[0].session_date == date(2024, 1, 2)
    assert factors[0].market_excess_return == pytest.approx(0.005)
    assert factors[0].smb == pytest.approx(-0.001)
    assert factors[0].risk_free_rate == pytest.approx(0.0001)


def test_factor_archive_parser_reads_the_official_zip_shape() -> None:
    from financial_event_model.market import parse_french_factor_archive

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "F-F_Research_Data_Factors_daily.csv",
            "Notes\n,Mkt-RF,SMB,HML,RF\n20240102,0.50,-0.10,0.20,0.01\n",
        )

    factors = parse_french_factor_archive(
        archive.getvalue(),
        received_at=datetime(2026, 8, 20, tzinfo=UTC),
    )

    assert len(factors) == 1
    assert factors[0].source == "ken_french_us_3_factor_daily"


def test_factor_fit_uses_only_pre_event_observations() -> None:
    from financial_event_model.market import estimate_factor_model

    observations = []
    for index in range(30):
        market = (index - 15) / 10_000
        smb = ((index % 5) - 2) / 20_000
        hml = ((index % 7) - 3) / 30_000
        risk_free = 0.0001
        stock_return = risk_free + 0.0002 + 1.2 * market + 0.3 * smb - 0.2 * hml
        observations.append(
            (
                date(2023, 11, 1) + timedelta(days=index),
                stock_return,
                market,
                smb,
                hml,
                risk_free,
            )
        )
    observations.append(
        (date(2024, 1, 2), 99.0, 99.0, 99.0, 99.0, 0.0)
    )

    model = estimate_factor_model(
        observations,
        event_start=date(2024, 1, 2),
        minimum_observations=20,
    )

    assert model.alpha == pytest.approx(0.0002)
    assert model.market_beta == pytest.approx(1.2)
    assert model.smb_beta == pytest.approx(0.3)
    assert model.hml_beta == pytest.approx(-0.2)
    assert model.observations == 30


def test_factor_fit_uses_only_the_latest_252_pre_event_observations() -> None:
    from financial_event_model.market import estimate_factor_model

    observations = []
    for index in range(253):
        market = (index % 11 - 5) / 1_000
        smb = (index % 7 - 3) / 2_000
        hml = (index % 5 - 2) / 3_000
        stock_return = 0.0001 + market + 0.5 * smb - 0.25 * hml
        if index == 0:
            stock_return = 100.0
        observations.append(
            (
                date(2023, 1, 1) + timedelta(days=index),
                stock_return,
                market,
                smb,
                hml,
                0.0,
            )
        )

    model = estimate_factor_model(
        observations,
        event_start=date(2024, 1, 1),
        minimum_observations=120,
    )

    assert model.observations == 252
    assert model.alpha == pytest.approx(0.0001)


def test_outcome_labels_use_correct_open_and_reproduce_simple_returns() -> None:
    from financial_event_model.market import (
        FactorObservation,
        FilingOutcomeInput,
        generate_outcome_label,
    )

    prior_start = date(2023, 11, 1)
    prior = []
    factors = []
    close = 80.0
    for index in range(30):
        close *= 1.002 + (index % 3) * 0.0001
        session = prior_start + timedelta(days=index)
        prior.append(_bar(session, close, volume=1_000))
        factors.append(
            FactorObservation(
                session_date=session,
                market_excess_return=0.001 + (index % 3) * 0.0001,
                smb=0.0001 * ((index % 5) - 2),
                hml=0.0001 * ((index % 7) - 3),
                risk_free_rate=0.0001,
                source="fixture",
                received_at=datetime(2026, 8, 20, tzinfo=UTC),
            )
        )
    event_start = date(2024, 1, 2)
    stock = []
    benchmark = []
    sector = []
    for index in range(1, 21):
        session = event_start + timedelta(days=index - 1)
        stock.append(
            _bar(
                session,
                100.0 * (1.01**index),
                open_price=100.0 if index == 1 else 100.0 * (1.01 ** (index - 1)),
                volume=2_000 if index <= 5 else 1_000,
            )
        )
        benchmark.append(
            _bar(
                session,
                100.0 * (1.005**index),
                security_id="security_spy",
                open_price=100.0 if index == 1 else 100.0 * (1.005 ** (index - 1)),
            )
        )
        sector.append(
            _bar(
                session,
                100.0 * (1.007**index),
                security_id="security_xlk",
                open_price=100.0 if index == 1 else 100.0 * (1.007 ** (index - 1)),
            )
        )
        factors.append(
            FactorObservation(
                session_date=session,
                market_excess_return=0.005,
                smb=0.0,
                hml=0.0,
                risk_free_rate=0.0001,
                source="fixture",
                received_at=datetime(2026, 8, 20, tzinfo=UTC),
            )
        )
    event = FilingOutcomeInput(
        event_id="filing:0000000001-24-000001",
        entity_id="sec-cik:0000000001",
        security_id="security_stock",
        tradable_at=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
        event_count_on_start_session=2,
    )

    label = generate_outcome_label(
        event,
        stock_bars=tuple(prior + stock),
        benchmark_bars=tuple(benchmark),
        sector_bars=tuple(sector),
        factors=tuple(factors),
        minimum_factor_observations=20,
    )

    assert label.start_session == event_start
    assert label.raw_return_1d == pytest.approx(1.01 - 1)
    assert label.raw_return_5d == pytest.approx(1.01**5 - 1)
    assert label.raw_return_20d == pytest.approx(1.01**20 - 1)
    assert label.market_adjusted_return_5d == pytest.approx(1.01**5 - 1.005**5)
    assert label.sector_adjusted_return_5d == pytest.approx(1.01**5 - 1.007**5)
    assert label.realized_volatility_20d == pytest.approx(0.0, abs=1e-12)
    assert label.maximum_adverse_excursion_20d == pytest.approx(-0.01)
    assert label.maximum_favourable_excursion_20d == pytest.approx(1.01**21 - 1)
    assert label.volume_abnormality_5d == pytest.approx(1.0)
    assert label.factor_residual_return_20d is not None
    assert label.contamination.multiple_same_day_filings is True
    assert label.contamination.missing_price_data is False


def test_outcome_start_never_uses_an_open_before_tradable_at() -> None:
    from financial_event_model.market import FilingOutcomeInput, generate_outcome_label

    bars = tuple(
        _bar(date(2024, 1, 2) + timedelta(days=index), 100 + index)
        for index in range(21)
    )
    event = FilingOutcomeInput(
        event_id="filing:late",
        entity_id="sec-cik:0000000001",
        security_id="security_stock",
        tradable_at=datetime(2024, 1, 2, 14, 45, tzinfo=UTC),
    )

    label = generate_outcome_label(
        event,
        stock_bars=bars,
        benchmark_bars=(),
        sector_bars=(),
        factors=(),
    )

    assert label.start_session == date(2024, 1, 3)
    assert label.start_price_timestamp >= event.tradable_at


def test_missing_horizon_fails_closed_with_contamination_flag() -> None:
    from financial_event_model.market import FilingOutcomeInput, generate_outcome_label

    event = FilingOutcomeInput(
        event_id="filing:short",
        entity_id="sec-cik:0000000001",
        security_id="security_stock",
        tradable_at=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
    )

    label = generate_outcome_label(
        event,
        stock_bars=(_bar(date(2024, 1, 2), 101.0, open_price=100.0),),
        benchmark_bars=(),
        sector_bars=(),
        factors=(),
    )

    assert label.raw_return_1d == pytest.approx(0.01)
    assert label.raw_return_5d is None
    assert label.factor_residual_return_20d is None
    assert label.contamination.missing_price_data is True


def test_unknown_trading_status_does_not_become_a_false_halt() -> None:
    from financial_event_model.market import FilingOutcomeInput, generate_outcome_label

    bar = _bar(date(2024, 1, 2), 101.0, open_price=100.0).model_copy(
        update={"trading_status": "unknown"}
    )
    event = FilingOutcomeInput(
        event_id="filing:status-unknown",
        entity_id="sec-cik:0000000001",
        security_id="security_stock",
        tradable_at=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
    )

    label = generate_outcome_label(
        event,
        stock_bars=(bar,),
        benchmark_bars=(),
        sector_bars=(),
        factors=(),
    )

    assert label.contamination.trading_halt is None


def test_one_hundred_fixture_outcomes_reproduce_source_price_ratios() -> None:
    from financial_event_model.market import FilingOutcomeInput, generate_outcome_label

    for index in range(100):
        growth = 1.001 + index / 1_000_000
        bars = tuple(
            _bar(
                date(2024, 1, 2) + timedelta(days=horizon - 1),
                100.0 * (growth**horizon),
                open_price=(
                    100.0 if horizon == 1 else 100.0 * (growth ** (horizon - 1))
                ),
            )
            for horizon in range(1, 21)
        )
        event = FilingOutcomeInput(
            event_id=f"filing:fixture-{index:03d}",
            entity_id=f"entity_{index:03d}",
            security_id="security_stock",
            tradable_at=bars[0].timestamp,
        )

        label = generate_outcome_label(
            event,
            stock_bars=bars,
            benchmark_bars=bars,
            sector_bars=bars,
            factors=(),
        )

        assert label.raw_return_1d == pytest.approx(growth - 1)
        assert label.raw_return_5d == pytest.approx(growth**5 - 1)
        assert label.raw_return_20d == pytest.approx(growth**20 - 1)
        assert label.start_price_timestamp == bars[0].timestamp
