"""Materialize accepted SEC evidence into the temporal knowledge store."""

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import KnowledgeRecord, MaterializationResult
from .policy import DailyTradabilityPolicy
from .store import KnowledgeStore


class SecKnowledgeMaterializer:
    def __init__(
        self,
        *,
        sec_manifest_path: str | Path,
        normalization_manifest_path: str | Path,
        knowledge_store_path: str | Path,
        policy: DailyTradabilityPolicy,
        entity_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.sec_manifest_path = Path(sec_manifest_path)
        self.normalization_manifest_path = Path(normalization_manifest_path)
        self.store = KnowledgeStore(knowledge_store_path)
        self.policy = policy
        self.entity_resolver = entity_resolver or (lambda cik: f"sec-cik:{cik}")

    def run(self, *, limit: int | None = None) -> MaterializationResult:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        source_rows = self._source_rows()
        normalized_rows = self._normalized_rows()
        if limit is not None:
            normalized_rows = normalized_rows[:limit]
        skipped: list[int] = []
        materialized = 0
        for normalized in normalized_rows:
            source_id = int(normalized["source_document_id"])
            source = source_rows.get(source_id)
            if (
                source is None
                or source["acceptance_at"] is None
                or (entity_id := self.entity_resolver(source["cik"])) is None
            ):
                skipped.append(source_id)
                continue
            published = datetime.fromisoformat(source["acceptance_at"])
            first_observed = datetime.fromisoformat(source["first_observed_at"])
            downloaded = datetime.fromisoformat(source["downloaded_at"])
            processed = datetime.fromisoformat(normalized["processed_at"])
            normalized_source = f"sec-normalized:{normalized['normalization_id']}"
            digest = hashlib.sha256(
                f"{normalized_source}:{self.policy.version}".encode("utf-8")
            ).hexdigest()
            self.store.put(
                KnowledgeRecord(
                    record_id=f"knowledge_{digest}",
                    entity_id=entity_id,
                    knowledge_type="sec_document",
                    knowledge_key=(
                        f"{source['accession_number']}:{source_id}"
                    ),
                    source_id=normalized_source,
                    content_hash=normalized["output_hash"],
                    payload={
                        "accession_number": source["accession_number"],
                        "cik": source["cik"],
                        "document_type": source["document_type"],
                        "filename": source["filename"],
                        "form": source["form"],
                        "is_amendment": bool(source["is_amendment"]),
                        "normalization_id": normalized["normalization_id"],
                        "parser_version": normalized["parser_version"],
                        "source_document_id": source_id,
                    },
                    event_effective_at=None,
                    source_published_at=published,
                    first_observed_at=first_observed,
                    downloaded_at=downloaded,
                    processed_at=processed,
                    tradable_at=self.policy.tradable_at(published),
                    policy_version=self.policy.version,
                )
            )
            materialized += 1
        return MaterializationResult(
            selected=len(normalized_rows),
            materialized=materialized,
            skipped=len(skipped),
            skipped_source_document_ids=tuple(skipped),
        )

    def _source_rows(self) -> dict[int, sqlite3.Row]:
        with sqlite3.connect(self.sec_manifest_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT document.document_id, document.accession_number,
                       document.document_type, document.filename,
                       filing.cik, filing.acceptance_at, filing.form,
                       filing.is_amendment, filing.first_observed_at,
                       request.response_received_at AS downloaded_at
                FROM sec_documents AS document
                JOIN sec_filings AS filing
                  ON filing.accession_number = document.accession_number
                JOIN sec_requests AS request
                  ON request.request_id = document.source_request_id
                """
            ).fetchall()
        return {int(row["document_id"]): row for row in rows}

    def _normalized_rows(self) -> list[sqlite3.Row]:
        with sqlite3.connect(self.normalization_manifest_path) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT normalization_id, source_document_id, parser_version,
                       output_hash, created_at AS processed_at
                FROM normalized_documents
                WHERE success = 1 AND output_hash IS NOT NULL
                ORDER BY normalization_id
                """
            ).fetchall()
