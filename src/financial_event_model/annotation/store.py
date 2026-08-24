"""SQLite persistence for append-only annotation history and frozen releases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from financial_event_model.contracts import Contract
from financial_event_model.ontology import OntologyDefinition

from .models import AnnotationProgress, AnnotationRecord, AnnotationTask

if TYPE_CHECKING:
    from .dataset import DatasetRelease


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _model_json(model: Contract) -> str:
    return _canonical_json(model.model_dump(mode="json"))


class AnnotationStore:
    def __init__(self, path: str | Path, ontology: OntologyDefinition) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ontology = ontology
        self._migrate()

    def add_tasks(self, tasks: tuple[AnnotationTask, ...]) -> None:
        with self._connection() as connection:
            for task in tasks:
                for label in task.candidate_labels:
                    self.ontology.label(label)
                payload = _model_json(task)
                content_hash = hashlib.sha256(payload.encode()).hexdigest()
                existing = connection.execute(
                    "SELECT content_hash FROM annotation_tasks WHERE event_id = ?",
                    (task.event_id,),
                ).fetchone()
                if existing is not None:
                    if existing["content_hash"] != content_hash:
                        raise ValueError(
                            f"annotation task {task.event_id} already exists with different content"
                        )
                    continue
                connection.execute(
                    """
                    INSERT INTO annotation_tasks (
                        event_id, company, entity_id, related_event_group,
                        source_published_at, tradable_at, filing_type,
                        annotation_round, content_hash, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.event_id,
                        task.company,
                        task.entity_id,
                        task.related_event_group,
                        task.source_published_at.isoformat(),
                        task.tradable_at.isoformat(),
                        task.filing_type,
                        task.annotation_round.value,
                        content_hash,
                        payload,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    def get_task(self, event_id: str) -> AnnotationTask | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM annotation_tasks WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return None if row is None else AnnotationTask.model_validate_json(row["payload_json"])

    def list_tasks(self) -> tuple[AnnotationTask, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM annotation_tasks ORDER BY event_id"
            ).fetchall()
        return tuple(AnnotationTask.model_validate_json(row["payload_json"]) for row in rows)

    def save_annotation(self, record: AnnotationRecord) -> None:
        task = self.get_task(record.event_id)
        if task is None:
            raise ValueError(f"unknown annotation task: {record.event_id}")
        record.validate_against(self.ontology, task)
        current = self._current_for_annotator(record.event_id, record.annotator_id)
        if current is None and record.supersedes_annotation_id is not None:
            raise ValueError("supersedes_annotation_id has no current annotation")
        if current is not None and record.supersedes_annotation_id != current.annotation_id:
            raise ValueError(
                "supersedes_annotation_id does not reference the current annotation"
            )
        if current is not None and record.created_at <= current.created_at:
            raise ValueError("replacement created_at must be later than current annotation")
        payload = _model_json(record)
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO annotations (
                        annotation_id, event_id, annotator_id, ontology_version,
                        labels_json, attributes_json, evidence_spans_json,
                        confidence, ambiguity_flag, no_material_event, created_at,
                        supersedes_annotation_id, adjudication_status, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.annotation_id,
                        record.event_id,
                        record.annotator_id,
                        record.ontology_version,
                        _canonical_json(list(record.labels)),
                        _canonical_json(record.attributes),
                        _canonical_json(
                            [span.model_dump(mode="json") for span in record.evidence_spans]
                        ),
                        record.confidence,
                        int(record.ambiguity_flag),
                        int(record.no_material_event),
                        record.created_at.isoformat(),
                        record.supersedes_annotation_id,
                        record.adjudication_status.value,
                        payload,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"annotation could not be saved: {error}") from error

    def current_annotations(self, event_id: str) -> tuple[AnnotationRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT a.payload_json
                FROM annotations AS a
                WHERE a.event_id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM annotations AS newer
                      WHERE newer.supersedes_annotation_id = a.annotation_id
                  )
                ORDER BY a.annotator_id, a.created_at, a.annotation_id
                """,
                (event_id,),
            ).fetchall()
        return tuple(AnnotationRecord.model_validate_json(row["payload_json"]) for row in rows)

    def annotation_history(
        self, event_id: str, annotator_id: str
    ) -> tuple[AnnotationRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM annotations
                WHERE event_id = ? AND annotator_id = ?
                ORDER BY created_at, annotation_id
                """,
                (event_id, annotator_id),
            ).fetchall()
        return tuple(AnnotationRecord.model_validate_json(row["payload_json"]) for row in rows)

    def next_unannotated_task(self, annotator_id: str) -> AnnotationTask | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT task.payload_json
                FROM annotation_tasks AS task
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM annotations AS current
                    WHERE current.event_id = task.event_id
                      AND current.annotator_id = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM annotations AS newer
                          WHERE newer.supersedes_annotation_id = current.annotation_id
                      )
                )
                ORDER BY CASE task.annotation_round
                    WHEN 'calibration' THEN 1
                    WHEN 'gold' THEN 2
                    WHEN 'expansion' THEN 3
                    ELSE 4
                END, task.event_id
                LIMIT 1
                """,
                (annotator_id,),
            ).fetchone()
        return None if row is None else AnnotationTask.model_validate_json(row["payload_json"])

    def annotation_progress(self, annotator_id: str) -> AnnotationProgress:
        annotator_id = annotator_id.strip()
        if not annotator_id:
            raise ValueError("annotator_id is required")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN EXISTS (
                           SELECT 1
                           FROM annotations AS current
                           WHERE current.event_id = task.event_id
                             AND current.annotator_id = ?
                             AND NOT EXISTS (
                                 SELECT 1 FROM annotations AS newer
                                 WHERE newer.supersedes_annotation_id = current.annotation_id
                             )
                       ) THEN 1 ELSE 0 END) AS completed
                FROM annotation_tasks AS task
                """,
                (annotator_id,),
            ).fetchone()
        total = int(row["total"])
        completed = int(row["completed"] or 0)
        return AnnotationProgress(
            annotator_id=annotator_id,
            total=total,
            completed=completed,
            remaining=total - completed,
        )

    def freeze_release(self, release: DatasetRelease) -> None:
        existing = self.get_release(release.release_id)
        if existing is not None:
            if existing.content_hash == release.content_hash:
                return
            raise ValueError(f"release {release.release_id} is already frozen")
        if release.expected_content_hash() != release.content_hash:
            raise ValueError("release content_hash does not match its manifest")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO annotation_releases (
                    release_id, content_hash, evidence_kind, ontology_version,
                    manifest_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    release.release_id,
                    release.content_hash,
                    release.evidence_kind,
                    release.ontology_version,
                    release.model_dump_json(),
                    release.created_at.isoformat(),
                ),
            )

    def get_release(self, release_id: str) -> DatasetRelease | None:
        from .dataset import DatasetRelease

        with self._connection() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM annotation_releases WHERE release_id = ?",
                (release_id,),
            ).fetchone()
        if row is None:
            return None
        release = DatasetRelease.model_validate_json(row["manifest_json"])
        if release.expected_content_hash() != release.content_hash:
            raise ValueError(f"frozen release {release_id} failed its content hash")
        return release

    def apply_down_migration(self) -> None:
        migration = (
            Path(__file__).with_name("migrations") / "0001_annotations.down.sql"
        ).read_text(encoding="utf-8")
        with self._connection() as connection:
            connection.executescript(migration)

    def schema_objects(self) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%' AND type IN ('table', 'index')
                ORDER BY name
                """
            ).fetchall()
        return tuple(row["name"] for row in rows)

    def _current_for_annotator(
        self, event_id: str, annotator_id: str
    ) -> AnnotationRecord | None:
        return next(
            (
                record
                for record in self.current_annotations(event_id)
                if record.annotator_id == annotator_id
            ),
            None,
        )

    def _migrate(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS annotation_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = connection.execute(
                "SELECT 1 FROM annotation_schema_migrations WHERE version = 1"
            ).fetchone()
            if applied is None:
                migration = (
                    Path(__file__).with_name("migrations") / "0001_annotations.sql"
                ).read_text(encoding="utf-8")
                connection.executescript(migration)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()
