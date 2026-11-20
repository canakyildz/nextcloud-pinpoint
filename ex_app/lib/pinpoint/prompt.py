"""The prompt sent to the language model, and the parser for its answer.

The prompt is written for small local models (Nextcloud's own llm2, or a 7B model behind LocalAI or
Ollama) as much as for hosted ones: one task, a fixed output shape, and an example of that shape.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .model import FieldSpec, FieldType, Schema

MAX_DOCUMENT_CHARS = 24_000

_FORMAT_HINTS = {
    FieldType.TEXT: "text",
    FieldType.NUMBER: (
        "number; write a plain number with a dot as decimal separator, no currency, no thousands separators"
    ),
    FieldType.DATE: "date; write it as YYYY-MM-DD",
    FieldType.BOOLEAN: "true or false",
}


class ModelOutputError(ValueError):
    """The model's answer could not be read as the expected JSON."""


def _describe(field: FieldSpec) -> str:
    if field.type == FieldType.SELECTION and field.options:
        kind = "one of: " + ", ".join(json.dumps(o, ensure_ascii=False) for o in field.options)
    else:
        kind = _FORMAT_HINTS[field.type]
    line = f'- "{field.key}" ({field.label}; {kind})'
    if field.description:
        line += f": {field.description.strip()}"
    return line


def build_prompt(schema: Schema, document_text: str, max_chars: int = MAX_DOCUMENT_CHARS) -> str:
    truncated = len(document_text) > max_chars
    text = document_text[:max_chars]
    example_key = schema.fields[0].key if schema.fields else "field"
    example = {
        "fields": {
            example_key: {"value": "…", "quote": "…exact text from the document…", "page": 1},
            "another_field": {"value": None, "quote": None, "page": None},
        }
    }
    kind = schema.instructions.strip() or f"The document should contain: {schema.name}."
    lines = [
        "You read a document and extract data from it. Reply with one JSON object and nothing else.",
        "",
        kind,
        "",
        "Fields to extract:",
        *(_describe(f) for f in schema.fields),
        "",
        "For every field, return an object with:",
        '- "value": the value in the format given above, or null if the document does not contain it.',
        '- "quote": the shortest text from the document that contains the value, copied exactly as it is '
        "written there, character for character (keep its spelling, number format and punctuation). "
        "null when the value is null.",
        '- "page": the number of the page the quote is on.',
        "",
        "Do not guess and do not calculate values that are not written in the document. "
        "If a field is not in the document, use null.",
        "",
        "Reply in exactly this shape, with one entry per field:",
        json.dumps(example, ensure_ascii=False),
        "",
        "The document:",
        "<<<",
        text,
        ">>>",
    ]
    if truncated:
        lines.append("(The document was cut here because it is long.)")
    return "\n".join(lines)


def build_repair_prompt(previous_answer: str) -> str:
    return (
        "The following answer should have been one valid JSON object of the form "
        '{"fields": {"<field>": {"value": ..., "quote": ..., "page": ...}}} but could not be parsed. '
        "Return the same content as valid JSON only, with no other text.\n\n" + previous_answer[:8000]
    )


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
# Small models sometimes write numbers the way the document does, unquoted: "value": 7829,00
_COMMA_NUMBER_RE = re.compile(r"(:\s*)(-?\d{1,3}(?:[ .\u00a0\u202f]\d{3})*,\d+|-?\d+,\d+)(?=\s*[,}\]])")


def _quote_comma_numbers(text: str) -> str:
    return _COMMA_NUMBER_RE.sub(r'\1"\2"', text)


def parse_model_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model answer that may carry reasoning, fences or chatter."""
    cleaned = _THINK_RE.sub("", text or "").strip()
    fenced = _FENCE_RE.search(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ModelOutputError("The model did not return JSON.")
    candidate = cleaned[start : end + 1]
    repaired = _TRAILING_COMMA_RE.sub(r"\1", candidate)
    for attempt in (candidate, repaired, _quote_comma_numbers(repaired)):
        try:
            data = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ModelOutputError("The model's answer is not valid JSON.")


def field_answers(data: dict[str, Any], schema: Schema) -> dict[str, dict[str, Any]]:
    """Map the model's answer onto the schema's field keys. Tolerates a missing "fields" wrapper,
    keys written as labels, and bare values without a quote."""
    raw = data.get("fields", data)
    if not isinstance(raw, dict):
        raise ModelOutputError('The model\'s answer has no "fields" object.')
    by_folded = {str(k).casefold().strip(): v for k, v in raw.items()}
    answers: dict[str, dict[str, Any]] = {}
    for spec in schema.fields:
        entry = raw.get(spec.key)
        if entry is None:
            entry = by_folded.get(spec.key.casefold(), by_folded.get(spec.label.casefold()))
        if isinstance(entry, dict):
            answers[spec.key] = {
                "value": entry.get("value"),
                "quote": entry.get("quote"),
                "page": entry.get("page"),
            }
        elif entry is not None:
            answers[spec.key] = {"value": entry, "quote": None, "page": None}
        else:
            answers[spec.key] = {"value": None, "quote": None, "page": None}
    return answers
