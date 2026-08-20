import sqlite3
from datetime import date

import pytest
from pydantic import ValidationError


def test_security_master_applies_versioned_schema_once(tmp_path) -> None:
    from financial_event_model.identifiers import SecurityMaster

    database = tmp_path / "security_master.sqlite3"
    SecurityMaster(database)
    SecurityMaster(database)

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        versions = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert {
        "entities",
        "securities",
        "identifier_history",
        "universe_membership",
    } <= tables
    assert versions == [(1,)]


def test_resolution_uses_half_open_identifier_and_membership_history(tmp_path) -> None:
    from financial_event_model.identifiers import (
        EntityRecord,
        IdentifierRecord,
        SecurityMaster,
        SecurityRecord,
        UniverseMembershipRecord,
    )

    master = SecurityMaster(tmp_path / "security_master.sqlite3")
    master.add_entity(
        EntityRecord(
            entity_id="entity_apple",
            legal_name="Apple Inc.",
            cik="320193",
            incorporation_country="US",
            sector="Information Technology",
            industry="Technology Hardware",
            valid_from=date(1980, 12, 12),
        )
    )
    master.add_security(
        SecurityRecord(
            security_id="security_apple_common",
            entity_id="entity_apple",
            ticker="AAPL",
            exchange="NASDAQ",
            security_type="common_stock",
            currency="USD",
            valid_from=date(1980, 12, 12),
        )
    )
    master.add_identifier(
        IdentifierRecord(
            identifier_type="cik",
            identifier_value="320193",
            entity_id="entity_apple",
            valid_from=date(1980, 12, 12),
            source="sec",
        )
    )
    master.add_identifier(
        IdentifierRecord(
            identifier_type="ticker",
            identifier_value="AAPL-OLD",
            entity_id="entity_apple",
            security_id="security_apple_common",
            valid_from=date(1980, 12, 12),
            valid_to=date(2020, 1, 1),
            source="fixture",
        )
    )
    master.add_identifier(
        IdentifierRecord(
            identifier_type="ticker",
            identifier_value="AAPL",
            entity_id="entity_apple",
            security_id="security_apple_common",
            valid_from=date(2020, 1, 1),
            source="fixture",
        )
    )
    master.add_universe_membership(
        UniverseMembershipRecord(
            security_id="security_apple_common",
            universe_name="us_liquid_equities",
            membership_start=date(2015, 1, 1),
            membership_end=date(2021, 1, 1),
            reason_added="historical fixture",
            reason_removed="boundary fixture",
        )
    )

    before_ticker_change = master.resolve_filing(
        "320193", date(2019, 12, 31), "us_liquid_equities"
    )
    at_ticker_change = master.resolve_filing(
        "0000320193", date(2020, 1, 1), "us_liquid_equities"
    )
    at_membership_end = master.resolve_filing(
        "320193", date(2021, 1, 1), "us_liquid_equities"
    )

    assert before_ticker_change is not None
    assert before_ticker_change.cik == "0000320193"
    assert before_ticker_change.securities[0].ticker == "AAPL-OLD"
    assert before_ticker_change.securities[0].in_universe is True
    assert at_ticker_change is not None
    assert at_ticker_change.securities[0].ticker == "AAPL"
    assert at_ticker_change.securities[0].tradable is True
    assert at_membership_end is not None
    assert at_membership_end.securities[0].in_universe is False


def test_resolution_reports_delisted_security_and_honours_entity_validity(tmp_path) -> None:
    from financial_event_model.identifiers import (
        EntityRecord,
        SecurityMaster,
        SecurityRecord,
    )

    master = SecurityMaster(tmp_path / "security_master.sqlite3")
    master.add_entity(
        EntityRecord(
            entity_id="entity_old",
            legal_name="Old Company",
            cik="1234",
            valid_from=date(2010, 1, 1),
            valid_to=date(2030, 1, 1),
        )
    )
    master.add_security(
        SecurityRecord(
            security_id="security_old",
            entity_id="entity_old",
            ticker="OLD",
            exchange="NYSE",
            security_type="common_stock",
            currency="USD",
            valid_from=date(2010, 1, 1),
            delisted_at=date(2021, 1, 1),
        )
    )

    resolution = master.resolve_filing(
        "1234", date(2022, 1, 1), "us_liquid_equities"
    )

    assert resolution is not None
    assert resolution.securities[0].tradable is False
    assert master.resolve_filing(
        "1234", date(2030, 1, 1), "us_liquid_equities"
    ) is None


def test_records_reject_invalid_ranges_and_overlapping_identifiers(tmp_path) -> None:
    from financial_event_model.identifiers import (
        EntityRecord,
        IdentifierRecord,
        SecurityMaster,
    )

    with pytest.raises(ValidationError, match="valid_to must be after valid_from"):
        EntityRecord(
            entity_id="entity_invalid",
            legal_name="Invalid Company",
            cik="1",
            valid_from=date(2020, 1, 1),
            valid_to=date(2020, 1, 1),
        )

    master = SecurityMaster(tmp_path / "security_master.sqlite3")
    master.add_entity(
        EntityRecord(
            entity_id="entity_one",
            legal_name="One Company",
            cik="1",
            valid_from=date(2010, 1, 1),
        )
    )
    first = IdentifierRecord(
        identifier_type="cik",
        identifier_value="1",
        entity_id="entity_one",
        valid_from=date(2010, 1, 1),
        valid_to=date(2020, 1, 1),
        source="fixture",
    )
    overlapping = IdentifierRecord(
        identifier_type="cik",
        identifier_value="1",
        entity_id="entity_one",
        valid_from=date(2019, 1, 1),
        source="fixture",
    )
    master.add_identifier(first)

    with pytest.raises(ValueError, match="overlapping identifier history"):
        master.add_identifier(overlapping)
