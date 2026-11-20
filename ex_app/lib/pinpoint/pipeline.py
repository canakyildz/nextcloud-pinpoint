"""The extraction pipeline: document → text with positions → model → verified fields.

Nothing in here talks to Nextcloud. The model is any object with an async `complete(prompt)`, which
is how the same pipeline runs inside the ExApp (through Nextcloud's TaskProcessing), in the tests
(a scripted fake) and in the evals (an OpenAI-compatible endpoint or a fault-injecting oracle).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

from .anchor import DocumentIndex
from .document import LoadOptions, document_text, load_document
from .model import Document, Extraction, Schema
from .prompt import (
    MAX_DOCUMENT_CHARS,
    ModelOutputError,
    build_prompt,
    build_repair_prompt,
    field_answers,
    parse_model_json,
)
from .values import detect_conventions
from .verify import run_checks, verify_field

LOG = logging.getLogger(__name__)


class TextModel(Protocol):
    async def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class PipelineOptions:
    load: LoadOptions = field(default_factory=LoadOptions)
    max_document_chars: int = MAX_DOCUMENT_CHARS
    repair_attempts: int = 1


async def extract(
    data: bytes,
    schema: Schema,
    model: TextModel,
    mime: str | None = None,
    options: PipelineOptions | None = None,
) -> Extraction:
    options = options or PipelineOptions()
    timings: dict[str, float] = {}

    started = time.perf_counter()
    document = await asyncio.to_thread(load_document, data, mime, options.load)
    timings["read_document"] = time.perf_counter() - started

    return await extract_from_document(document, schema, model, options, timings)


async def extract_from_document(
    document: Document,
    schema: Schema,
    model: TextModel,
    options: PipelineOptions | None = None,
    timings: dict[str, float] | None = None,
) -> Extraction:
    options = options or PipelineOptions()
    timings = timings if timings is not None else {}
    text = document_text(document)
    prompt = build_prompt(schema, text, options.max_document_chars)

    started = time.perf_counter()
    answer = await model.complete(prompt)
    attempts = 0
    while True:
        try:
            data = parse_model_json(answer)
            answers = field_answers(data, schema)
            break
        except ModelOutputError:
            if attempts >= options.repair_attempts:
                raise
            attempts += 1
            LOG.info("Model answer was not valid JSON, asking it to repair (attempt %s)", attempts)
            answer = await model.complete(build_repair_prompt(answer))
    timings["model"] = time.perf_counter() - started

    started = time.perf_counter()
    index = DocumentIndex(document)
    decimal, order = detect_conventions(text)
    fields = [verify_field(spec, answers[spec.key], index, decimal, order) for spec in schema.fields]
    checks = run_checks(schema, fields)
    timings["verify"] = time.perf_counter() - started

    return Extraction(
        schema=schema,
        fields=fields,
        checks=checks,
        pages=[
            {"index": p.index, "width": p.width, "height": p.height, "source": p.source.value} for p in document.pages
        ],
        truncated=document.truncated or len(text) > options.max_document_chars,
        model_output=answer,
        timings=timings,
    )
