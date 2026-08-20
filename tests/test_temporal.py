import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError


UTC = timezone.utc


def _record(**overrides):
    from financial_event_model.temporal import KnowledgeRecord

    published = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    values = {
        "record_id": "record_original",
        "entity_id": "entity_apple",
        "knowledge_type": "sec_filing",
        "knowledge_key": "0000320193-24-000001",
        "source_id": "normalized:1",
        "content_hash": "a" * 64,
        "payload": {"form": "8-K"},
        "event_effective_at": None,
        "source_published_at": published,
        "first_observed_at": datetime(2026, 8, 20, 1, 0, tzinfo=UTC),
        "downloaded_at": datetime(2026, 8, 20, 1, 1, tzinfo=UTC),
        "processed_at": datetime(2026, 8, 20, 1, 2, tzinfo=UTC),
        "tradable_at": datetime(2024, 1, 3, 14, 30, tzinfo=UTC),
        "policy_version": "sec-daily-v0.1",
    }
    values.update(overrides)
    return KnowledgeRecord(**values)


def test_six_timestamp_contract_rejects_impossible_processing_order() -> None:
    with pytest.raises(ValidationError, match="processed_at"):
        _record(
            processed_at=datetime(2026, 8, 20, 0, 59, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("published", "expected"),
    [
        ("2024-01-02T15:00:00Z", "2024-01-03T14:30:00Z"),
        ("2024-01-02T22:00:00Z", "2024-01-03T14:45:00Z"),
        ("2024-01-06T17:00:00Z", "2024-01-08T14:45:00Z"),
        ("2024-07-03T18:00:00Z", "2024-07-05T13:45:00Z"),
    ],
)
def test_daily_tradability_policy_obeys_sessions_holidays_and_early_close(
    published: str,
    expected: str,
) -> None:
    from financial_event_model.temporal import DailyTradabilityPolicy

    policy = DailyTradabilityPolicy(processing_latency=timedelta(minutes=15))

    assert policy.tradable_at(datetime.fromisoformat(published.replace("Z", "+00:00"))) == (
        datetime.fromisoformat(expected.replace("Z", "+00:00"))
    )


def test_halt_resume_can_only_delay_tradability() -> None:
    from financial_event_model.temporal import DailyTradabilityPolicy

    policy = DailyTradabilityPolicy(processing_latency=timedelta(minutes=15))
    published = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)

    assert policy.tradable_at(
        published,
        trading_resumed_at=datetime(2024, 1, 4, 16, 0, tzinfo=UTC),
    ) == datetime(2024, 1, 5, 14, 30, tzinfo=UTC)


def test_exact_knowledge_query_excludes_future_amendments_and_revisions(tmp_path) -> None:
    from financial_event_model.temporal import KnowledgeStore

    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    original = _record()
    amendment = _record(
        record_id="record_amendment",
        knowledge_key="0000320193-24-000002",
        source_id="normalized:2",
        content_hash="b" * 64,
        payload={"form": "8-K/A"},
        source_published_at=datetime(2024, 1, 5, 20, 0, tzinfo=UTC),
        tradable_at=datetime(2024, 1, 8, 14, 30, tzinfo=UTC),
    )
    future_xbrl = _record(
        record_id="record_xbrl_revision",
        knowledge_type="xbrl_fact",
        knowledge_key="revenue:2023Q4",
        source_id="companyfacts:2",
        content_hash="c" * 64,
        payload={"value": 101},
        source_published_at=datetime(2024, 1, 9, 20, 0, tzinfo=UTC),
        tradable_at=datetime(2024, 1, 10, 14, 30, tzinfo=UTC),
    )
    for record in (original, amendment, future_xbrl):
        store.put(record)

    known = store.get_known_information(
        entity_id="entity_apple",
        decision_time="2024-01-04T14:05:00Z",
    )

    assert [record.record_id for record in known] == ["record_original"]
    assert store.get_known_information(
        entity_id="entity_apple",
        decision_time="2024-01-03T14:29:59Z",
    ) == ()
    assert len(
        store.get_known_information(
            entity_id="entity_apple",
            decision_time="2024-01-03T14:30:00Z",
        )
    ) == 1


def test_future_sector_version_cannot_rewrite_history(tmp_path) -> None:
    from financial_event_model.temporal import KnowledgeStore

    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.put(
        _record(
            record_id="sector_old",
            knowledge_type="sector_classification",
            knowledge_key="gics_sector",
            source_id="classification:1",
            payload={"sector": "Technology"},
        )
    )
    store.put(
        _record(
            record_id="sector_future",
            knowledge_type="sector_classification",
            knowledge_key="gics_sector",
            source_id="classification:2",
            content_hash="d" * 64,
            payload={"sector": "Communication Services"},
            source_published_at=datetime(2025, 1, 2, 15, 0, tzinfo=UTC),
            tradable_at=datetime(2025, 1, 3, 14, 30, tzinfo=UTC),
        )
    )

    known = store.get_known_information(
        "entity_apple", "2024-01-04T14:05:00Z", latest_per_key=True
    )

    assert [record.payload for record in known] == [{"sector": "Technology"}]


def test_future_price_adjustment_cannot_reveal_a_corporate_action(tmp_path) -> None:
    from financial_event_model.temporal import KnowledgeStore

    store = KnowledgeStore(tmp_path / "knowledge.sqlite3")
    store.put(
        _record(
            record_id="future_split_adjustment",
            knowledge_type="price_adjustment",
            knowledge_key="AAPL:2024-01-02",
            source_id="prices:revision:2",
            payload={"adjustment_factor": 0.25},
            source_published_at=datetime(2024, 6, 10, 20, 0, tzinfo=UTC),
            tradable_at=datetime(2024, 6, 11, 13, 30, tzinfo=UTC),
        )
    )

    assert store.get_known_information(
        "entity_apple", "2024-01-04T14:05:00Z"
    ) == ()


def test_sec_materializer_uses_acceptance_not_download_as_publication_time(tmp_path) -> None:
    from financial_event_model.temporal import (
        DailyTradabilityPolicy,
        SecKnowledgeMaterializer,
    )

    sec_manifest = tmp_path / "sec.sqlite3"
    normalized_manifest = tmp_path / "normalized.sqlite3"
    with sqlite3.connect(sec_manifest) as connection:
        connection.executescript(
            """
            CREATE TABLE sec_requests (
                request_id INTEGER PRIMARY KEY,
                response_received_at TEXT NOT NULL
            );
            CREATE TABLE sec_filings (
                accession_number TEXT PRIMARY KEY,
                cik TEXT NOT NULL,
                acceptance_at TEXT,
                form TEXT NOT NULL,
                is_amendment INTEGER NOT NULL,
                first_observed_at TEXT NOT NULL
            );
            CREATE TABLE sec_documents (
                document_id INTEGER PRIMARY KEY,
                accession_number TEXT NOT NULL,
                document_type TEXT,
                filename TEXT,
                source_request_id INTEGER NOT NULL
            );
            INSERT INTO sec_requests VALUES (7, '2026-08-20T01:01:00+00:00');
            INSERT INTO sec_filings VALUES (
                '0000320193-24-000001', '0000320193',
                '2024-01-02T15:00:00+00:00', '8-K', 0,
                '2026-08-20T01:00:00+00:00'
            );
            INSERT INTO sec_documents VALUES (
                11, '0000320193-24-000001', '8-K', 'filing.htm', 7
            );
            """
        )
    with sqlite3.connect(normalized_manifest) as connection:
        connection.executescript(
            """
            CREATE TABLE normalized_documents (
                normalization_id INTEGER PRIMARY KEY,
                source_document_id INTEGER NOT NULL,
                parser_version TEXT NOT NULL,
                output_hash TEXT,
                created_at TEXT NOT NULL,
                success INTEGER NOT NULL
            );
            INSERT INTO normalized_documents VALUES (
                13, 11, 'sec-html-v0.1',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                '2026-08-20T01:02:00+00:00', 1
            );
            """
        )
    materializer = SecKnowledgeMaterializer(
        sec_manifest_path=sec_manifest,
        normalization_manifest_path=normalized_manifest,
        knowledge_store_path=tmp_path / "knowledge.sqlite3",
        policy=DailyTradabilityPolicy(processing_latency=timedelta(minutes=15)),
        entity_resolver=lambda cik: "entity_apple" if cik == "0000320193" else None,
    )

    result = materializer.run()
    records = materializer.store.get_known_information(
        "entity_apple", "2024-01-03T14:30:00Z"
    )

    assert result.materialized == 1
    assert records[0].source_published_at == datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    assert records[0].downloaded_at == datetime(2026, 8, 20, 1, 1, tzinfo=UTC)
    assert records[0].tradable_at == datetime(2024, 1, 3, 14, 30, tzinfo=UTC)


def test_split_guards_reject_duplicate_hashes_and_overlapping_outcomes() -> None:
    from financial_event_model.temporal import (
        assert_disjoint_content_hashes,
        assert_non_overlapping_outcome_windows,
    )

    with pytest.raises(ValueError, match="duplicate content"):
        assert_disjoint_content_hashes({"a", "b"}, {"b", "c"})
    with pytest.raises(ValueError, match="outcome window"):
        assert_non_overlapping_outcome_windows(
            [(datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 5, tzinfo=UTC))],
            [(datetime(2024, 1, 4, tzinfo=UTC), datetime(2024, 1, 8, tzinfo=UTC))],
        )


def test_temporal_migration_has_a_working_down_script(tmp_path) -> None:
    from financial_event_model.temporal import KnowledgeStore

    database = tmp_path / "knowledge.sqlite3"
    store = KnowledgeStore(database)
    down = (
        Path(__file__).parents[1]
        / "src"
        / "financial_event_model"
        / "temporal"
        / "migrations"
        / "0001_knowledge_records.down.sql"
    ).read_text(encoding="utf-8")

    with store._connect() as connection:
        connection.executescript(down)
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_records'"
        ).fetchone()

    assert table is None
