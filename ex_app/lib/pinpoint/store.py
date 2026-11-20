"""Extraction jobs, kept in SQLite in the ExApp's persistent storage.

Only the review queue lives here: job status and the extracted values with their quotes. Documents
are never copied to disk; they are read from Nextcloud as the user each time. Approved data lives in
Nextcloud Tables, inside Nextcloud's own database and backups. Jobs are deleted after a retention period.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    """Extracted, waiting for review."""
    FAILED = "failed"
    SAVED = "saved"
    """Approved and written to a table."""


@dataclass(slots=True)
class Job:
    id: str
    user_id: str
    file_id: int
    file_name: str
    mime: str
    schema_id: str
    schema: dict[str, Any]
    status: JobStatus
    created_at: float
    updated_at: float
    error: str | None = None
    result: dict[str, Any] | None = None
    table_id: int | None = None
    row_id: int | None = None
    saved_values: dict[str, Any] | None = None

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "fileId": self.file_id,
            "fileName": self.file_name,
            "mime": self.mime,
            "schemaId": self.schema_id,
            "schemaName": self.schema.get("name"),
            "status": self.status.value,
            "error": self.error,
            "tableId": self.table_id,
            "rowId": self.row_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.result is not None:
            data["summary"] = self.result.get("summary")
        if include_result:
            data["schema"] = self.schema
            data["result"] = self.result
            data["savedValues"] = self.saved_values
        return data


_MIGRATIONS = [
    """
    CREATE TABLE jobs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        file_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        mime TEXT NOT NULL,
        schema_id TEXT NOT NULL,
        schema_json TEXT NOT NULL,
        status TEXT NOT NULL,
        error TEXT,
        result_json TEXT,
        table_id INTEGER,
        row_id INTEGER,
        saved_values_json TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX jobs_by_user ON jobs (user_id, created_at DESC);
    CREATE INDEX jobs_by_status ON jobs (status);
    """,
]


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(_MIGRATIONS[version:], start=version + 1):
                db.executescript(script)
                db.execute(f"PRAGMA user_version = {number}")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    async def _run(self, fn: Any, *args: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            user_id=row["user_id"],
            file_id=row["file_id"],
            file_name=row["file_name"],
            mime=row["mime"],
            schema_id=row["schema_id"],
            schema=json.loads(row["schema_json"]),
            status=JobStatus(row["status"]),
            error=row["error"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            table_id=row["table_id"],
            row_id=row["row_id"],
            saved_values=json.loads(row["saved_values_json"]) if row["saved_values_json"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def create(
        self, user_id: str, file_id: int, file_name: str, mime: str, schema: dict[str, Any], table_id: int | None
    ) -> Job:
        now = time.time()
        job = Job(
            id=uuid.uuid4().hex,
            user_id=user_id,
            file_id=file_id,
            file_name=file_name,
            mime=mime,
            schema_id=schema["id"],
            schema=schema,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            table_id=table_id,
        )

        def insert() -> None:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO jobs (id, user_id, file_id, file_name, mime, schema_id, schema_json, status,"
                    " table_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        job.id,
                        user_id,
                        file_id,
                        file_name,
                        mime,
                        job.schema_id,
                        json.dumps(schema),
                        job.status.value,
                        table_id,
                        now,
                        now,
                    ),
                )

        await self._run(insert)
        return job

    async def get(self, job_id: str, user_id: str | None = None) -> Job | None:
        """Fetch a job. With `user_id`, a job that belongs to someone else is reported as missing."""

        def select() -> sqlite3.Row | None:
            with self._connect() as db:
                if user_id is None:
                    return db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return db.execute("SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)).fetchone()

        row = await self._run(select)
        return self._row_to_job(row) if row else None

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Job]:
        def select() -> list[sqlite3.Row]:
            with self._connect() as db:
                return db.execute(
                    "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
                ).fetchall()

        return [self._row_to_job(r) for r in await self._run(select)]

    async def unfinished(self) -> list[Job]:
        def select() -> list[sqlite3.Row]:
            with self._connect() as db:
                return db.execute(
                    "SELECT * FROM jobs WHERE status IN (?, ?) ORDER BY created_at",
                    (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
                ).fetchall()

        return [self._row_to_job(r) for r in await self._run(select)]

    async def update(self, job_id: str, **changes: Any) -> None:
        columns: dict[str, Callable[[Any], Any]] = {
            "status": lambda v: v.value if isinstance(v, JobStatus) else v,
            "error": lambda v: v,
            "result": lambda v: json.dumps(v) if v is not None else None,
            "table_id": lambda v: v,
            "row_id": lambda v: v,
            "saved_values": lambda v: json.dumps(v) if v is not None else None,
        }
        names = {"result": "result_json", "saved_values": "saved_values_json"}
        assignments, values = [], []
        for key, value in changes.items():
            assignments.append(f"{names.get(key, key)} = ?")
            values.append(columns[key](value))
        assignments.append("updated_at = ?")
        values.extend([time.time(), job_id])

        def execute() -> None:
            with self._connect() as db:
                db.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values)  # noqa: S608

        await self._run(execute)

    async def delete(self, job_id: str, user_id: str) -> bool:
        def execute() -> int:
            with self._connect() as db:
                return db.execute("DELETE FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)).rowcount

        return bool(await self._run(execute))

    async def delete_older_than(self, days: float) -> int:
        cutoff = time.time() - days * 86400

        def execute() -> int:
            with self._connect() as db:
                return db.execute(
                    "DELETE FROM jobs WHERE updated_at < ? AND status NOT IN (?, ?)",
                    (cutoff, JobStatus.QUEUED.value, JobStatus.RUNNING.value),
                ).rowcount

        return int(await self._run(execute))

    async def delete_for_user(self, user_id: str) -> int:
        def execute() -> int:
            with self._connect() as db:
                return db.execute("DELETE FROM jobs WHERE user_id = ?", (user_id,)).rowcount

        return int(await self._run(execute))
