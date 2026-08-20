"""SQLite-backed point-in-time security master."""

import sqlite3
from datetime import date
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator

from financial_event_model.contracts import Contract


def normalize_cik(value: str) -> str:
    stripped = value.strip()
    if not stripped.isdigit() or len(stripped) > 10:
        raise ValueError("CIK must contain at most 10 digits")
    return stripped.zfill(10)


def _stored_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


class DatedRecord(Contract):
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def validate_validity_range(self) -> Self:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class EntityRecord(DatedRecord):
    entity_id: str = Field(min_length=1)
    legal_name: str = Field(min_length=1)
    cik: str
    incorporation_country: str | None = None
    sector: str | None = None
    industry: str | None = None

    @field_validator("cik", mode="before")
    @classmethod
    def normalize_cik(cls, value: str) -> str:
        return normalize_cik(value)


class SecurityRecord(DatedRecord):
    security_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    security_type: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    delisted_at: date | None = None


class IdentifierRecord(DatedRecord):
    identifier_type: str = Field(min_length=1)
    identifier_value: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    security_id: str | None = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize_identifier(self) -> Self:
        self.identifier_type = self.identifier_type.casefold()
        if self.identifier_type == "cik":
            self.identifier_value = normalize_cik(self.identifier_value)
        return self


class UniverseMembershipRecord(Contract):
    security_id: str = Field(min_length=1)
    universe_name: str = Field(min_length=1)
    membership_start: date
    membership_end: date | None = None
    reason_added: str = Field(min_length=1)
    reason_removed: str | None = None

    @model_validator(mode="after")
    def validate_membership_range(self) -> Self:
        if (
            self.membership_end is not None
            and self.membership_end <= self.membership_start
        ):
            raise ValueError("membership_end must be after membership_start")
        return self


class SecurityResolution(Contract):
    security_id: str
    ticker: str
    exchange: str
    security_type: str
    currency: str
    tradable: bool
    in_universe: bool


class FilingResolution(Contract):
    entity_id: str
    legal_name: str
    cik: str
    securities: tuple[SecurityResolution, ...]


class SecurityMasterIntegrityError(RuntimeError):
    """Raised when point-in-time identity data is ambiguous."""


class SecurityMaster:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def add_entity(self, record: EntityRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.entity_id,
                    record.legal_name,
                    record.cik,
                    record.incorporation_country,
                    record.sector,
                    record.industry,
                    _stored_date(record.valid_from),
                    _stored_date(record.valid_to),
                ),
            )

    def add_security(self, record: SecurityRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO securities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.security_id,
                    record.entity_id,
                    record.ticker,
                    record.exchange,
                    record.security_type,
                    record.currency,
                    _stored_date(record.valid_from),
                    _stored_date(record.valid_to),
                    _stored_date(record.delisted_at),
                ),
            )

    def add_identifier(self, record: IdentifierRecord) -> None:
        with self._connect() as connection:
            overlap = connection.execute(
                """
                SELECT 1
                FROM identifier_history
                WHERE identifier_type = :identifier_type
                  AND identifier_value = :identifier_value
                  AND valid_from < coalesce(:valid_to, '9999-12-31')
                  AND (valid_to IS NULL OR valid_to > :valid_from)
                LIMIT 1
                """,
                {
                    "identifier_type": record.identifier_type,
                    "identifier_value": record.identifier_value,
                    "valid_from": _stored_date(record.valid_from),
                    "valid_to": _stored_date(record.valid_to),
                },
            ).fetchone()
            if overlap is not None:
                raise ValueError("overlapping identifier history")
            connection.execute(
                """
                INSERT INTO identifier_history (
                    identifier_type,
                    identifier_value,
                    entity_id,
                    security_id,
                    valid_from,
                    valid_to,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.identifier_type,
                    record.identifier_value,
                    record.entity_id,
                    record.security_id,
                    _stored_date(record.valid_from),
                    _stored_date(record.valid_to),
                    record.source,
                ),
            )

    def add_universe_membership(self, record: UniverseMembershipRecord) -> None:
        with self._connect() as connection:
            overlap = connection.execute(
                """
                SELECT 1
                FROM universe_membership
                WHERE security_id = :security_id
                  AND universe_name = :universe_name
                  AND membership_start < coalesce(:membership_end, '9999-12-31')
                  AND (membership_end IS NULL OR membership_end > :membership_start)
                LIMIT 1
                """,
                {
                    "security_id": record.security_id,
                    "universe_name": record.universe_name,
                    "membership_start": _stored_date(record.membership_start),
                    "membership_end": _stored_date(record.membership_end),
                },
            ).fetchone()
            if overlap is not None:
                raise ValueError("overlapping universe membership")
            connection.execute(
                """
                INSERT INTO universe_membership VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.security_id,
                    record.universe_name,
                    _stored_date(record.membership_start),
                    _stored_date(record.membership_end),
                    record.reason_added,
                    record.reason_removed,
                ),
            )

    def resolve_filing(
        self,
        cik: str,
        filing_date: date,
        universe_name: str,
    ) -> FilingResolution | None:
        normalized_cik = normalize_cik(cik)
        as_of = filing_date.isoformat()
        entity = self._resolve_entity(normalized_cik, as_of)
        if entity is None:
            return None
        securities = self._resolve_securities(
            entity["entity_id"], as_of, universe_name
        )
        return FilingResolution(
            entity_id=entity["entity_id"],
            legal_name=entity["legal_name"],
            cik=normalized_cik,
            securities=securities,
        )

    def _resolve_entity(self, cik: str, as_of: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT e.entity_id, e.legal_name
                FROM identifier_history AS identifier
                JOIN entities AS e ON e.entity_id = identifier.entity_id
                WHERE identifier.identifier_type = 'cik'
                  AND identifier.identifier_value = :cik
                  AND identifier.valid_from <= :as_of
                  AND (identifier.valid_to IS NULL OR :as_of < identifier.valid_to)
                  AND e.valid_from <= :as_of
                  AND (e.valid_to IS NULL OR :as_of < e.valid_to)
                """,
                {"cik": cik, "as_of": as_of},
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    """
                    SELECT entity_id, legal_name
                    FROM entities
                    WHERE cik = :cik
                      AND valid_from <= :as_of
                      AND (valid_to IS NULL OR :as_of < valid_to)
                    """,
                    {"cik": cik, "as_of": as_of},
                ).fetchall()
        if len(rows) > 1:
            raise SecurityMasterIntegrityError(
                f"CIK {cik} resolves to multiple entities at {as_of}"
            )
        return rows[0] if rows else None

    def _resolve_securities(
        self,
        entity_id: str,
        as_of: str,
        universe_name: str,
    ) -> tuple[SecurityResolution, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    security.security_id,
                    coalesce(
                        (
                            SELECT identifier.identifier_value
                            FROM identifier_history AS identifier
                            WHERE identifier.identifier_type = 'ticker'
                              AND identifier.security_id = security.security_id
                              AND identifier.valid_from <= :as_of
                              AND (
                                  identifier.valid_to IS NULL
                                  OR :as_of < identifier.valid_to
                              )
                            ORDER BY identifier.valid_from DESC
                            LIMIT 1
                        ),
                        security.ticker
                    ) AS ticker,
                    security.exchange,
                    security.security_type,
                    security.currency,
                    CASE
                        WHEN security.delisted_at IS NULL
                          OR :as_of < security.delisted_at THEN 1
                        ELSE 0
                    END AS tradable,
                    EXISTS (
                        SELECT 1
                        FROM universe_membership AS membership
                        WHERE membership.security_id = security.security_id
                          AND membership.universe_name = :universe_name
                          AND membership.membership_start <= :as_of
                          AND (
                              membership.membership_end IS NULL
                              OR :as_of < membership.membership_end
                          )
                    ) AS in_universe
                FROM securities AS security
                WHERE security.entity_id = :entity_id
                  AND security.valid_from <= :as_of
                  AND (security.valid_to IS NULL OR :as_of < security.valid_to)
                ORDER BY security.security_id
                """,
                {
                    "entity_id": entity_id,
                    "as_of": as_of,
                    "universe_name": universe_name,
                },
            ).fetchall()
        return tuple(
            SecurityResolution(
                security_id=row["security_id"],
                ticker=row["ticker"],
                exchange=row["exchange"],
                security_type=row["security_type"],
                currency=row["currency"],
                tradable=bool(row["tradable"]),
                in_universe=bool(row["in_universe"]),
            )
            for row in rows
        )

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = 1"
            ).fetchone()
            if applied is None:
                migration = (
                    Path(__file__).with_name("migrations")
                    / "0001_security_master.sql"
                ).read_text(encoding="utf-8")
                connection.executescript(migration)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection
