"""Reversible SQLite persistence for market inputs and labels."""

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .models import CorporateAction, FactorObservation, MarketBar, OutcomeLabel


class MarketStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def put_bars(self, bars: tuple[MarketBar, ...]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO market_bars (
                    security_id, symbol, session_date, timestamp,
                    source_timestamp, open, high, low, close, volume,
                    adjusted_open, adjusted_high, adjusted_low, adjusted_close,
                    adjustment_factor, trading_status, source,
                    source_received_at, source_content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_bar_values(bar) for bar in bars],
            )

    def bars(
        self,
        security_id: str,
        *,
        start: date | None = None,
        end: date | None = None,
        as_of: datetime | None = None,
    ) -> tuple[MarketBar, ...]:
        conditions = ["security_id = :security_id"]
        parameters: dict[str, object] = {"security_id": security_id}
        if start is not None:
            conditions.append("session_date >= :start")
            parameters["start"] = start.isoformat()
        if end is not None:
            conditions.append("session_date <= :end")
            parameters["end"] = end.isoformat()
        if as_of is not None:
            if as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware")
            conditions.append("source_received_at <= :as_of")
            parameters["as_of"] = as_of.astimezone(timezone.utc).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM market_bars
                WHERE {' AND '.join(conditions)}
                ORDER BY session_date, source_received_at, bar_id
                """,
                parameters,
            ).fetchall()
        latest = {row["session_date"]: row for row in rows}
        return tuple(_bar_from_row(latest[key]) for key in sorted(latest))

    def put_factors(self, factors: tuple[FactorObservation, ...]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO factor_observations (
                    session_date, market_excess_return, smb, hml,
                    risk_free_rate, source, received_at, source_content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.session_date.isoformat(),
                        item.market_excess_return,
                        item.smb,
                        item.hml,
                        item.risk_free_rate,
                        item.source,
                        item.received_at.astimezone(timezone.utc).isoformat(),
                        item.source_content_hash,
                    )
                    for item in factors
                ],
            )

    def put_corporate_actions(self, actions: tuple[CorporateAction, ...]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO corporate_actions (
                    action_id, security_id, symbol, action_type, effective_date,
                    announced_at, first_observed_at, source,
                    source_content_hash, source_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.action_id,
                        item.security_id,
                        item.symbol,
                        item.action_type,
                        item.effective_date.isoformat(),
                        (
                            item.announced_at.astimezone(timezone.utc).isoformat()
                            if item.announced_at is not None
                            else None
                        ),
                        item.first_observed_at.astimezone(timezone.utc).isoformat(),
                        item.source,
                        item.source_content_hash,
                        json.dumps(item.source_payload, sort_keys=True, separators=(",", ":")),
                    )
                    for item in actions
                ],
            )

    def corporate_actions(
        self,
        security_id: str,
        *,
        as_of: datetime,
    ) -> tuple[CorporateAction, ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM corporate_actions
                WHERE security_id = ? AND first_observed_at <= ?
                ORDER BY effective_date, action_id, first_observed_at
                """,
                (security_id, as_of.astimezone(timezone.utc).isoformat()),
            ).fetchall()
        return tuple(_corporate_action_from_row(row) for row in rows)

    def factors(self, *, end: date | None = None) -> tuple[FactorObservation, ...]:
        query = "SELECT * FROM factor_observations"
        parameters: tuple[str, ...] = ()
        if end is not None:
            query += " WHERE session_date <= ?"
            parameters = (end.isoformat(),)
        query += " ORDER BY session_date, received_at, factor_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        latest = {row["session_date"]: row for row in rows}
        return tuple(_factor_from_row(latest[key]) for key in sorted(latest))

    def put_outcome(self, label: OutcomeLabel) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outcome_labels (
                    event_id, label_version, payload_json, generated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (event_id, label_version) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    generated_at = excluded.generated_at
                """,
                (
                    label.event_id,
                    label.label_version,
                    label.model_dump_json(),
                    label.generated_at.astimezone(timezone.utc).isoformat(),
                ),
            )

    def record_request(
        self,
        *,
        request_url: str,
        adjustment: str,
        feed: str,
        requested_at: datetime,
        response_received_at: datetime,
        http_status: int,
        content_hash: str,
        local_path: Path,
        error: str | None = None,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO market_requests (
                    request_url, adjustment, feed, requested_at,
                    response_received_at, http_status, content_hash,
                    local_path, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_url,
                    adjustment,
                    feed,
                    requested_at.astimezone(timezone.utc).isoformat(),
                    response_received_at.astimezone(timezone.utc).isoformat(),
                    http_status,
                    content_hash,
                    str(local_path),
                    error,
                ),
            )
            return int(cursor.lastrowid)

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                int(row[0])
                for row in connection.execute(
                    "SELECT version FROM market_schema_migrations"
                ).fetchall()
            }
            root = Path(__file__).with_name("migrations")
            for path in sorted(root.glob("[0-9][0-9][0-9][0-9]_*.sql")):
                version = int(path.name[:4])
                if version not in applied:
                    connection.executescript(path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _bar_values(bar: MarketBar) -> tuple[object, ...]:
    return (
        bar.security_id,
        bar.symbol,
        bar.session_date.isoformat(),
        bar.timestamp.astimezone(timezone.utc).isoformat(),
        (
            bar.source_timestamp.astimezone(timezone.utc).isoformat()
            if bar.source_timestamp is not None
            else None
        ),
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.adjusted_open,
        bar.adjusted_high,
        bar.adjusted_low,
        bar.adjusted_close,
        bar.adjustment_factor,
        bar.trading_status,
        bar.source,
        bar.source_received_at.astimezone(timezone.utc).isoformat(),
        bar.source_content_hash,
    )


def _bar_from_row(row: sqlite3.Row) -> MarketBar:
    values = dict(row)
    values.pop("bar_id")
    return MarketBar(**values)


def _factor_from_row(row: sqlite3.Row) -> FactorObservation:
    values = dict(row)
    values.pop("factor_id")
    return FactorObservation(**values)


def _corporate_action_from_row(row: sqlite3.Row) -> CorporateAction:
    values = dict(row)
    values["source_payload"] = json.loads(values.pop("source_payload_json"))
    return CorporateAction(**values)
