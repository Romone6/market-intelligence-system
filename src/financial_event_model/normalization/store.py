"""Separate persistence and orchestration for normalized SEC documents."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import NormalizedDocument, NormalizationRunResult
from .sec_html import normalize_sec_html


_TEXT_SUFFIXES = {".htm", ".html", ".txt"}
_PRIMARY_TYPES = {"8-K", "8-K/A", "10-Q", "10-Q/A"}


class NormalizationStore:
    def __init__(self, output_root: str | Path, manifest_path: str | Path) -> None:
        self.output_root = Path(output_root)
        self.manifest_path = Path(manifest_path)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def reusable(self, source_document_id: int, source_hash: str, parser_version: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT local_path
                FROM normalized_documents
                WHERE source_document_id = ?
                  AND source_content_hash = ?
                  AND parser_version = ?
                  AND success = 1
                """,
                (source_document_id, source_hash, parser_version),
            ).fetchone()
        return row is not None and Path(row["local_path"]).is_file()

    def save(self, document: NormalizedDocument) -> bool:
        body = (
            json.dumps(
                document.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        output_hash = hashlib.sha256(body).hexdigest()
        destination = (
            self.output_root
            / "sec"
            / output_hash[:2]
            / f"{output_hash}.json"
        )
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
            temporary.write_bytes(body)
            temporary.replace(destination)
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT output_hash, local_path, success
                FROM normalized_documents
                WHERE source_document_id = ? AND parser_version = ?
                """,
                (document.source_document_id, document.parser_version),
            ).fetchone()
            reused = (
                existing is not None
                and existing["success"] == 1
                and existing["output_hash"] == output_hash
                and Path(existing["local_path"]).is_file()
            )
            connection.execute(
                """
                INSERT INTO normalized_documents (
                    source_document_id, source_content_hash, parser_version,
                    output_hash, local_path, parent_document_id, is_exhibit,
                    language, parsing_quality, warnings_json, success, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
                ON CONFLICT (source_document_id, parser_version) DO UPDATE SET
                    source_content_hash = excluded.source_content_hash,
                    output_hash = excluded.output_hash,
                    local_path = excluded.local_path,
                    parent_document_id = excluded.parent_document_id,
                    is_exhibit = excluded.is_exhibit,
                    language = excluded.language,
                    parsing_quality = excluded.parsing_quality,
                    warnings_json = excluded.warnings_json,
                    success = 1,
                    error = NULL,
                    created_at = excluded.created_at
                """,
                (
                    document.source_document_id,
                    document.source_content_hash,
                    document.parser_version,
                    output_hash,
                    str(destination),
                    document.parent_document_id,
                    int(document.is_exhibit),
                    document.language,
                    document.parsing_quality,
                    json.dumps(document.warnings),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return reused

    def record_failure(
        self,
        *,
        source_document_id: int,
        source_content_hash: str,
        parser_version: str,
        parent_document_id: int | None,
        is_exhibit: bool,
        error: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO normalized_documents (
                    source_document_id, source_content_hash, parser_version,
                    output_hash, local_path, parent_document_id, is_exhibit,
                    language, parsing_quality, warnings_json, success, error, created_at
                ) VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, '[]', 0, ?, ?)
                ON CONFLICT (source_document_id, parser_version) DO UPDATE SET
                    source_content_hash = excluded.source_content_hash,
                    output_hash = NULL,
                    local_path = NULL,
                    parent_document_id = excluded.parent_document_id,
                    is_exhibit = excluded.is_exhibit,
                    language = NULL,
                    parsing_quality = NULL,
                    warnings_json = '[]',
                    success = 0,
                    error = excluded.error,
                    created_at = excluded.created_at
                """,
                (
                    source_document_id,
                    source_content_hash,
                    parser_version,
                    parent_document_id,
                    int(is_exhibit),
                    error,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS normalization_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = connection.execute(
                "SELECT 1 FROM normalization_schema_migrations WHERE version = 1"
            ).fetchone()
            if applied is None:
                migration = (
                    Path(__file__).with_name("migrations")
                    / "0001_normalized_documents.sql"
                ).read_text(encoding="utf-8")
                connection.executescript(migration)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.manifest_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection


class SecNormalizationPipeline:
    def __init__(
        self,
        *,
        sec_manifest_path: str | Path,
        output_root: str | Path,
        normalization_manifest_path: str | Path,
        parser_version: str,
    ) -> None:
        self.sec_manifest_path = Path(sec_manifest_path)
        self.parser_version = parser_version
        self.store = NormalizationStore(output_root, normalization_manifest_path)

    def run(self, *, limit: int) -> NormalizationRunResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self._source_rows()
        selected = _stratified_rows(rows, limit)
        primary_by_accession = _primary_documents(rows)
        completed = reused = 0
        failed_ids: list[int] = []
        for row in selected:
            source_id = int(row["document_id"])
            source_hash = row["content_hash"]
            is_exhibit = (row["document_type"] or "").casefold().startswith("ex-")
            parent_id = (
                primary_by_accession.get(row["accession_number"])
                if is_exhibit
                else None
            )
            if self.store.reusable(source_id, source_hash, self.parser_version):
                reused += 1
                continue
            try:
                raw_content = Path(row["local_path"]).read_bytes()
                actual_hash = hashlib.sha256(raw_content).hexdigest()
                if actual_hash != source_hash:
                    raise ValueError("source content hash does not match Stage 2 manifest")
                document = normalize_sec_html(
                    raw_content,
                    source_document_id=source_id,
                    accession_number=row["accession_number"],
                    source_content_hash=source_hash,
                    document_type=row["document_type"],
                    filename=row["filename"],
                    parser_version=self.parser_version,
                    parent_document_id=parent_id,
                )
                if self.store.save(document):
                    reused += 1
                else:
                    completed += 1
            except Exception as error:
                self.store.record_failure(
                    source_document_id=source_id,
                    source_content_hash=source_hash,
                    parser_version=self.parser_version,
                    parent_document_id=parent_id,
                    is_exhibit=is_exhibit,
                    error=f"{type(error).__name__}: {error}",
                )
                failed_ids.append(source_id)
        return NormalizationRunResult(
            selected=len(selected),
            completed=completed,
            reused=reused,
            failed=len(failed_ids),
            source_document_ids=tuple(int(row["document_id"]) for row in selected),
            failed_document_ids=tuple(failed_ids),
        )

    def _source_rows(self) -> list[sqlite3.Row]:
        with sqlite3.connect(self.sec_manifest_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT document_id, accession_number, document_type, sequence,
                       filename, content_hash, local_path
                FROM sec_documents
                ORDER BY document_id
                """
            ).fetchall()
        return [
            row
            for row in rows
            if Path(row["filename"] or row["local_path"]).suffix.casefold()
            in _TEXT_SUFFIXES
            and (
                (row["document_type"] or "").upper() in _PRIMARY_TYPES
                or (row["document_type"] or "").upper().startswith("EX-")
            )
        ]


def _sequence_key(value: str | None) -> tuple[int, str]:
    return (int(value), value) if value and value.isdigit() else (10**9, value or "")


def _primary_documents(rows: list[sqlite3.Row]) -> dict[str, int]:
    candidates: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if (row["document_type"] or "").upper() in _PRIMARY_TYPES:
            candidates[row["accession_number"]].append(row)
    return {
        accession: int(min(items, key=lambda row: _sequence_key(row["sequence"]))["document_id"])
        for accession, items in candidates.items()
    }


def _stratified_rows(rows: list[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[row["accession_number"][:10]].append(row)
    selected: list[sqlite3.Row] = []
    rank = 0
    while len(selected) < limit:
        added = False
        for cik in sorted(groups):
            if rank < len(groups[cik]):
                selected.append(groups[cik][rank])
                added = True
                if len(selected) == limit:
                    return selected
        if not added:
            break
        rank += 1
    return selected
