"""Small local experiment ledger with immutable configuration snapshots."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ExperimentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    recorded_at: AwareDatetime
    config: dict[str, Any]
    config_hash: str = Field(min_length=64, max_length=64)


class ExperimentStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    run_id TEXT PRIMARY KEY,
                    model_version TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    config_hash TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        config_paths: Iterable[str | Path],
        *,
        model_version: str,
        run_id: str | None = None,
    ) -> ExperimentRecord:
        config = _load_configs(config_paths)
        if not config:
            raise ValueError("at least one configuration file is required")
        config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
        record = ExperimentRecord(
            run_id=run_id or str(uuid4()),
            model_version=model_version,
            recorded_at=datetime.now(timezone.utc),
            config=config,
            config_hash=hashlib.sha256(config_json.encode()).hexdigest(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO experiments VALUES (?, ?, ?, ?, ?)",
                (
                    record.run_id,
                    record.model_version,
                    record.recorded_at.isoformat(),
                    config_json,
                    record.config_hash,
                ),
            )
        return record

    def get(self, run_id: str) -> ExperimentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, model_version, recorded_at, config_json, config_hash
                FROM experiments
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return ExperimentRecord(
            run_id=row[0],
            model_version=row[1],
            recorded_at=datetime.fromisoformat(row[2]),
            config=json.loads(row[3]),
            config_hash=row[4],
        )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


def _load_configs(config_paths: Iterable[str | Path]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for supplied_path in config_paths:
        path = Path(supplied_path)
        if path.stem in config:
            raise ValueError(f"duplicate configuration name: {path.stem}")
        with path.open(encoding="utf-8") as stream:
            config[path.stem] = yaml.safe_load(stream)
    return config
