"""Extraction jobs from start to finish: queue, run, review, save to Tables."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .document import SUPPORTED_MIMES, DocumentError, LoadOptions, render_page
from .model import FieldStatus, Schema
from .nextcloud import Gateway, NextcloudError
from .pipeline import PipelineOptions, extract
from .prompt import ModelOutputError
from .schemas import EVIDENCE_COLUMN, SOURCE_COLUMN, TEMPLATES, schema_from_table, template
from .store import Job, JobStatus, JobStore
from .tables import CellError, cell_value, evidence_markdown, source_markdown
from .verify import normalize_value

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Settings:
    max_pages: int = 20
    max_file_mb: float = 25
    ocr_languages: str = "eng+deu+fra+spa+ita+nld"
    model_timeout_minutes: float = 20
    keep_days: float = 30


class UserError(ValueError):
    """A problem the user can act on. Shown as is."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class _Lru(OrderedDict[Any, bytes]):
    def __init__(self, capacity: int) -> None:
        super().__init__()
        self.capacity = capacity

    def get_or_none(self, key: Any) -> bytes | None:
        value = self.get(key)
        if value is not None:
            self.move_to_end(key)
        return value

    def put(self, key: Any, value: bytes) -> None:
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.capacity:
            self.popitem(last=False)


class PinpointService:
    def __init__(
        self,
        store: JobStore,
        gateway: Gateway,
        settings: Callable[[], Awaitable[Settings]],
        app_id: str = "pinpoint",
        workers: int = 1,
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.settings = settings
        self.app_id = app_id
        self.workers = workers
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._pages = _Lru(64)
        self._files = _Lru(2)
        self._idle = asyncio.Event()
        self._idle.set()

    # Lifecycle --------------------------------------------------------------------------------------

    async def start(self) -> None:
        for job in await self.store.unfinished():
            LOG.info("Requeueing job %s after restart", job.id)
            await self.store.update(job.id, status=JobStatus.QUEUED)
            self._queue.put_nowait(job.id)
        self._tasks = [asyncio.create_task(self._worker(), name=f"pinpoint-worker-{i}") for i in range(self.workers)]
        self._tasks.append(asyncio.create_task(self._housekeeping(), name="pinpoint-housekeeping"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def wait_idle(self) -> None:
        """For tests: wait until the queue is empty and no job is running."""
        await self._queue.join()

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._run(job_id)
            except Exception:
                LOG.exception("Job %s crashed", job_id)
            finally:
                self._queue.task_done()

    async def _housekeeping(self) -> None:
        await asyncio.sleep(60)  # let AppAPI finish enabling the app first
        while True:
            try:
                settings = await self.settings()
                removed = await self.store.delete_older_than(settings.keep_days)
                if removed:
                    LOG.info("Removed %s jobs older than %s days", removed, settings.keep_days)
            except Exception as exc:
                LOG.warning("Housekeeping skipped: %s", exc)
            await asyncio.sleep(6 * 3600)

    # Schemas and tables -----------------------------------------------------------------------------

    async def tables(self, user_id: str) -> list[dict[str, Any]]:
        tables = await self.gateway.list_tables(user_id)
        return [
            {"id": t["id"], "title": t.get("title", ""), "emoji": t.get("emoji") or "", "owner": t.get("ownership")}
            for t in tables
        ]

    async def table_schema(self, user_id: str, table_id: int) -> Schema:
        table = await self.gateway.get_table(user_id, table_id)
        columns = await self.gateway.table_columns(user_id, table_id)
        schema = schema_from_table(table, columns)
        if not schema.fields:
            raise UserError("This table has no columns Pinpoint can fill. Add text, number, date or selection columns.")
        return schema

    @staticmethod
    def templates() -> list[dict[str, Any]]:
        return [s.to_dict() for s in TEMPLATES.values()]

    async def create_table(self, user_id: str, template_id: str, title: str | None) -> dict[str, Any]:
        try:
            schema = template(template_id)
        except KeyError as exc:
            raise UserError(str(exc)) from None
        table = await self.gateway.create_table(user_id, schema, (title or schema.name + "s").strip()[:200])
        return {"id": table["id"], "title": table.get("title", ""), "emoji": table.get("emoji") or ""}

    # Jobs ---------------------------------------------------------------------------------------------

    async def submit(self, user_id: str, file_id: int, table_id: int) -> Job:
        settings = await self.settings()
        info = await self.gateway.file_info(user_id, file_id)
        if info.mime not in SUPPORTED_MIMES:
            raise UserError(f"{info.name} is not a PDF or an image, so Pinpoint cannot read it.")
        if info.size > settings.max_file_mb * 1024 * 1024:
            raise UserError(f"{info.name} is larger than the {settings.max_file_mb:g} MB limit set by your admin.")
        schema = await self.table_schema(user_id, table_id)
        job = await self.store.create(user_id, info.id, info.name, info.mime, schema.to_dict(), table_id)
        self._queue.put_nowait(job.id)
        return job

    async def _run(self, job_id: str) -> None:
        job = await self.store.get(job_id)
        if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return
        await self.store.update(job.id, status=JobStatus.RUNNING, error=None)
        settings = await self.settings()
        try:
            data = await self._file(job.user_id, job.file_id)
            model = await self.gateway.text_model(
                job.user_id, f"{self.app_id}:{job.id}", settings.model_timeout_minutes * 60
            )
            options = PipelineOptions(
                load=LoadOptions(max_pages=settings.max_pages, ocr_languages=settings.ocr_languages)
            )
            extraction = await extract(data, Schema.from_dict(job.schema), model, job.mime, options)
        except (DocumentError, NextcloudError, ModelOutputError, UserError) as exc:
            await self._fail(job, str(exc))
            return
        except Exception:
            LOG.exception("Extraction failed for job %s", job.id)
            await self._fail(job, "Something went wrong while reading this document. The server log has details.")
            return
        result = extraction.to_dict()
        await self.store.update(job.id, status=JobStatus.DONE, result=result)
        summary = result["summary"]
        to_check = summary[FieldStatus.REVIEW.value] + summary[FieldStatus.UNVERIFIED.value]
        await self.gateway.notify(
            job.user_id,
            f"Pinpoint read {job.file_name}",
            f"{summary[FieldStatus.VERIFIED.value]} values verified, {to_check} to check.",
            await self.review_url(job.id),
        )

    async def _fail(self, job: Job, message: str) -> None:
        await self.store.update(job.id, status=JobStatus.FAILED, error=message)
        await self.gateway.notify(
            job.user_id, f"Pinpoint could not read {job.file_name}", message, await self.review_url(job.id)
        )

    async def _file(self, user_id: str, file_id: int) -> bytes:
        key = (user_id, file_id)
        data = self._files.get_or_none(key)
        if data is None:
            data = await self.gateway.download(user_id, file_id)
            self._files.put(key, data)
        return data

    async def retry(self, user_id: str, job_id: str) -> Job:
        job = await self._job(user_id, job_id)
        if job.status not in (JobStatus.FAILED, JobStatus.DONE):
            raise UserError("Only finished jobs can be run again.", 409)
        await self.store.update(job.id, status=JobStatus.QUEUED, error=None, result=None)
        self._queue.put_nowait(job.id)
        return await self._job(user_id, job_id)

    async def get(self, user_id: str, job_id: str) -> Job:
        return await self._job(user_id, job_id)

    async def list_jobs(self, user_id: str) -> list[Job]:
        return await self.store.list_for_user(user_id)

    async def delete(self, user_id: str, job_id: str) -> None:
        if not await self.store.delete(job_id, user_id):
            raise UserError("Not found.", 404)
        for key in [k for k in self._pages if k[0] == job_id]:
            del self._pages[key]

    async def _job(self, user_id: str, job_id: str) -> Job:
        job = await self.store.get(job_id, user_id)
        if job is None:
            raise UserError("Not found.", 404)
        return job

    async def page_png(self, user_id: str, job_id: str, page: int) -> bytes:
        job = await self._job(user_id, job_id)
        key = (job_id, page)
        png = self._pages.get_or_none(key)
        if png is None:
            # Downloaded as the user each time the cache is cold: if the file was unshared, this fails.
            data = await self._file(user_id, job.file_id)
            try:
                png = await asyncio.to_thread(render_page, data, page, job.mime)
            except DocumentError as exc:
                raise UserError(str(exc), 404) from None
            self._pages.put(key, png)
        return png

    async def save(self, user_id: str, job_id: str, values: dict[str, Any]) -> Job:
        job = await self._job(user_id, job_id)
        if job.status == JobStatus.SAVED:
            raise UserError("This document was already saved to the table.", 409)
        if job.status != JobStatus.DONE or job.result is None or job.table_id is None:
            raise UserError("This job has nothing to save yet.", 409)
        schema = Schema.from_dict(job.schema)
        columns = {c["id"]: c for c in await self.gateway.table_columns(user_id, job.table_id)}
        extracted = {f["key"]: f.get("value") for f in job.result.get("fields", [])}

        clean: dict[str, Any] = {}
        data: dict[int, Any] = {}
        problems: list[str] = []
        for spec in schema.fields:
            raw = values.get(spec.key, extracted.get(spec.key))
            value, problem = normalize_value(spec, raw, None, None)
            if problem:
                problems.append(f"{spec.label}: {problem}")
                continue
            clean[spec.key] = value
            column = columns.get(spec.column_id) if spec.column_id is not None else None
            if column is None:
                continue  # the column was deleted after extraction
            try:
                cell = cell_value(spec, value, column)
            except CellError as exc:
                problems.append(str(exc))
                continue
            if cell is not None:
                data[column["id"]] = cell
        if problems:
            raise UserError("; ".join(problems))

        public = await self.gateway.public_url()
        for column in columns.values():
            title = str(column.get("title", "")).strip().casefold()
            if column.get("type") != "text":
                continue
            if title == SOURCE_COLUMN.casefold():
                data[column["id"]] = source_markdown(
                    job.file_name, f"{public}/index.php/f/{job.file_id}", await self.review_url(job.id)
                )
            elif title == EVIDENCE_COLUMN.casefold():
                data[column["id"]] = evidence_markdown(schema, job.result, clean)

        row_id = await self.gateway.create_row(user_id, job.table_id, data)
        await self.store.update(job.id, status=JobStatus.SAVED, row_id=row_id, saved_values=clean)
        return await self._job(user_id, job_id)

    async def review_url(self, job_id: str) -> str:
        return f"{await self.gateway.public_url()}/index.php/apps/app_api/embedded/{self.app_id}/main/jobs/{job_id}"
