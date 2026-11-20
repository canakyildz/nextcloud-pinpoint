"""Pinpoint as a TaskProcessing provider, so the Assistant (and anything else using TaskProcessing,
such as Context Agent or Flow) can extract fields from a document.

It registers a custom task type. The Assistant renders it from its input and output shapes, with no
frontend code: pick a file, pick a document type, get the fields as JSON plus a readable evidence list.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
from typing import Any

from nc_py_api import AsyncNextcloudApp
from nc_py_api.ex_app.providers.task_processing import (
    ShapeDescriptor,
    ShapeEnumValue,
    ShapeType,
    TaskProcessingProvider,
    TaskType,
)

from .document import DocumentError, LoadOptions
from .model import Extraction, FieldStatus
from .nextcloud import NextcloudError, TaskProcessingModel
from .pipeline import PipelineOptions, extract
from .prompt import ModelOutputError
from .schemas import TEMPLATES, template
from .service import Settings

LOG = logging.getLogger(__name__)

# Slot names are also the labels the Assistant shows, so they are written for people.
INPUT_DOCUMENT = "Document"
INPUT_KIND = "Document type"
OUTPUT_FIELDS = "Fields (JSON)"
OUTPUT_EVIDENCE = "Evidence"

FALLBACK_POLL_SECONDS = 30.0


def task_type(app_id: str) -> TaskType:
    return TaskType(
        id=f"{app_id}:extract_fields",
        name="Extract fields from a document",
        description="Reads an invoice or receipt and returns its fields, each with the page and text it came from.",
        input_shape=[
            ShapeDescriptor(name=INPUT_DOCUMENT, description="A PDF or an image", shape_type=ShapeType.FILE),
        ],
        output_shape=[
            ShapeDescriptor(
                name=OUTPUT_FIELDS, description="The extracted values with their sources", shape_type=ShapeType.TEXT
            ),
            ShapeDescriptor(name=OUTPUT_EVIDENCE, description="Where each value was found", shape_type=ShapeType.TEXT),
        ],
    )


def provider(app_id: str) -> TaskProcessingProvider:
    return TaskProcessingProvider(
        id=f"{app_id}:extract_fields",
        name="Pinpoint",
        task_type=f"{app_id}:extract_fields",
        expected_runtime=60,
        optional_input_shape=[
            ShapeDescriptor(name=INPUT_KIND, description="What kind of document it is", shape_type=ShapeType.ENUM),
        ],
        optional_input_shape_enum_values={
            INPUT_KIND: [ShapeEnumValue(name=s.name, value=s.id.removeprefix("template:")) for s in TEMPLATES.values()],
        },
        optional_input_shape_defaults={INPUT_KIND: "invoice"},
    )


def evidence_text(extraction: Extraction) -> str:
    labels = {s.key: s.label for s in extraction.schema.fields}
    marks = {
        FieldStatus.VERIFIED: "✓",
        FieldStatus.REVIEW: "?",
        FieldStatus.UNVERIFIED: "✗",
        FieldStatus.MISSING: "–",
    }
    lines = []
    for f in extraction.fields:
        if f.status == FieldStatus.MISSING:
            lines.append(f"{marks[f.status]} {labels[f.key]}: not in the document")
            continue
        where = f' (page {f.anchor.page + 1}: "{f.anchor.matched_text}")' if f.anchor else " (no source found)"
        lines.append(f"{marks[f.status]} {labels[f.key]}: {f.value}{where}")
        lines.extend(f"    {reason}" for reason in f.reasons)
    for check in extraction.checks:
        if not check.id.startswith("required:"):
            lines.append(f"{'✓' if check.passed else '✗'} {check.label}")
    lines.append("")
    lines.append("✓ verified in the document · ? check this value · ✗ not found in the document")
    return "\n".join(lines)


def fields_json(extraction: Extraction) -> str:
    out: dict[str, Any] = {}
    for f in extraction.fields:
        out[f.key] = {
            "value": f.value,
            "status": f.status.value,
            "page": f.anchor.page + 1 if f.anchor else None,
            "source_text": f.anchor.matched_text if f.anchor else None,
            "boxes": [b.to_dict() for b in f.anchor.boxes] if f.anchor else [],
        }
    return json.dumps({"document_type": extraction.schema.name, "fields": out}, ensure_ascii=False, indent=2)


class ProviderWorker:
    """Takes tasks from Nextcloud and runs them. Nextcloud 33+ pushes a trigger when a task arrives;
    a slow poll covers older servers and missed triggers."""

    def __init__(self, app_id: str, settings: Any) -> None:
        self.app_id = app_id
        self.settings = settings
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def trigger(self, provider_id: str) -> None:
        self._wake.set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="pinpoint-provider")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        nc = AsyncNextcloudApp()
        provider_id = f"{self.app_id}:extract_fields"
        while True:
            try:
                if not await nc.enabled_state:
                    await self._sleep()
                    continue
                response = await nc.providers.task_processing.next_task([provider_id], [provider_id])
                if not response:
                    await self._sleep()
                    continue
                await self._handle(nc, response["task"])
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Provider loop error")
                await asyncio.sleep(5)

    async def _sleep(self) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=FALLBACK_POLL_SECONDS)
        self._wake.clear()

    async def _handle(self, nc: AsyncNextcloudApp, task: dict[str, Any]) -> None:
        task_id = task["id"]
        settings: Settings = await self.settings()
        try:
            kind = task["input"].get(INPUT_KIND) or "invoice"
            schema = template(kind)
            data = await _task_input_file(nc, task_id, int(task["input"][INPUT_DOCUMENT]))
            user_nc = AsyncNextcloudApp()
            await user_nc.set_user(task["userId"])
            model = TaskProcessingModel(user_nc, f"{self.app_id}:task:{task_id}", settings.model_timeout_minutes * 60)
            await nc.providers.task_processing.set_progress(task_id, 10)
            extraction = await extract(
                data,
                schema,
                model,
                None,
                PipelineOptions(load=LoadOptions(max_pages=settings.max_pages, ocr_languages=settings.ocr_languages)),
            )
        except (DocumentError, NextcloudError, ModelOutputError, KeyError) as exc:
            await nc.providers.task_processing.report_result(
                task_id, error_message=str(exc), user_facing_error_message=str(exc)
            )
            return
        except Exception as exc:
            LOG.exception("Task %s failed", task_id)
            await nc.providers.task_processing.report_result(
                task_id, error_message=repr(exc), user_facing_error_message="Pinpoint could not read this document."
            )
            return
        await nc.providers.task_processing.report_result(
            task_id, {OUTPUT_FIELDS: fields_json(extraction), OUTPUT_EVIDENCE: evidence_text(extraction)}
        )


async def _task_input_file(nc: AsyncNextcloudApp, task_id: int, file_id: int) -> bytes:
    # Files given to a task may live outside the user's storage (Assistant uploads), so they are read
    # through the provider endpoint. nc_py_api has no public helper for it yet.
    buffer = io.BytesIO()
    await nc._session.download2stream(f"/ocs/v2.php/taskprocessing/tasks_provider/{task_id}/file/{file_id}", buffer)
    return buffer.getvalue()
