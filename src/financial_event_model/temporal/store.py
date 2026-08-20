"""SQLite-backed exact historical knowledge query."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import KnowledgeRecord


class KnowledgeStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def put(self, record: KnowledgeRecord) -> None:
        item = record.as_utc()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_records (
                    record_id, entity_id, knowledge_type, knowledge_key,
                    source_id, content_hash, payload_json, event_effective_at,
                    source_published_at, first_observed_at, downloaded_at,
                    processed_at, tradable_at, policy_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (record_id) DO UPDATE SET
                    entity_id = excluded.entity_id,
                    knowledge_type = excluded.knowledge_type,
                    knowledge_key = excluded.knowledge_key,
                    source_id = excluded.source_id,
                    content_hash = excluded.content_hash,
                    payload_json = excluded.payload_json,
                    event_effective_at = excluded.event_effective_at,
                    source_published_at = excluded.source_published_at,
                    first_observed_at = excluded.first_observed_at,
                    downloaded_at = excluded.downloaded_at,
                    processed_at = excluded.processed_at,
                    tradable_at = excluded.tradable_at,
                    policy_version = excluded.policy_version
                """,
                (
                    item.record_id,
                    item.entity_id,
                    item.knowledge_type,
                    item.knowledge_key,
                    item.source_id,
                    item.content_hash,
                    json.dumps(item.payload, separators=(",", ":"), sort_keys=True),
                    _stored_datetime(item.event_effective_at),
                    _stored_datetime(item.source_published_at),
                    _stored_datetime(item.first_observed_at),
                    _stored_datetime(item.downloaded_at),
                    _stored_datetime(item.processed_at),
                    _stored_datetime(item.tradable_at),
                    item.policy_version,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_known_information(
        self,
        entity_id: str,
        decision_time: str | datetime,
        *,
        latest_per_key: bool = False,
    ) -> tuple[KnowledgeRecord, ...]:
        decision = _parse_decision_time(decision_time)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM knowledge_records
                WHERE entity_id = ? AND tradable_at <= ?
                ORDER BY tradable_at, record_id
                """,
                (entity_id, decision.isoformat()),
            ).fetchall()
        records = tuple(_record_from_row(row) for row in rows)
        if not latest_per_key:
            return records
        latest: dict[tuple[str, str], KnowledgeRecord] = {}
        for record in records:
            latest[(record.knowledge_type, record.knowledge_key)] = record
        return tuple(
            sorted(latest.values(), key=lambda item: (item.tradable_at, item.record_id))
        )

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS temporal_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                int(row[0])
                for row in connection.execute(
                    "SELECT version FROM temporal_schema_migrations"
                ).fetchall()
            }
            migration_root = Path(__file__).with_name("migrations")
            for path in sorted(migration_root.glob("[0-9][0-9][0-9][0-9]_*.sql")):
                version = int(path.name[:4])
                if version not in applied:
                    connection.executescript(path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _stored_datetime(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _parse_decision_time(value: str | datetime) -> datetime:
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("decision_time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _record_from_row(row: sqlite3.Row) -> KnowledgeRecord:
    values: dict[str, Any] = dict(row)
    values["payload"] = json.loads(values.pop("payload_json"))
    values.pop("created_at")
    return KnowledgeRecord(**values)
