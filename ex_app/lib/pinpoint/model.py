"""Data model shared by the extraction pipeline, the API and the evals.

Coordinates are normalised to the page: (0, 0) is the top-left corner and (1, 1) the bottom-right,
so the same box works for the PDF page, a rendered PNG of any size and the overlay in the browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FieldType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    SELECTION = "selection"
    BOOLEAN = "boolean"


class FieldStatus(StrEnum):
    VERIFIED = "verified"
    """The quote was found in the document and the value agrees with it."""
    REVIEW = "review"
    """Found, but something needs a human look (fuzzy match, value differs from quote, failed check)."""
    UNVERIFIED = "unverified"
    """The model gave a value but its quote is nowhere in the document. Treat as a guess."""
    MISSING = "missing"
    """The model reported that the document does not contain this field."""


class TextSource(StrEnum):
    TEXT_LAYER = "text-layer"
    OCR = "ocr"


@dataclass(frozen=True, slots=True)
class Box:
    page: int
    """Zero-based page index."""
    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: Box) -> Box:
        assert self.page == other.page
        return Box(
            self.page,
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def to_dict(self) -> dict[str, float | int]:
        return {
            "page": self.page,
            "x0": round(self.x0, 5),
            "y0": round(self.y0, 5),
            "x1": round(self.x1, 5),
            "y1": round(self.y1, 5),
        }


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    box: Box
    line: int
    """Line number within the page, used to rebuild reading order and to split highlight boxes."""


@dataclass(slots=True)
class Page:
    index: int
    width: float
    height: float
    words: list[Word]
    source: TextSource


@dataclass(slots=True)
class Document:
    pages: list[Page]
    truncated: bool = False
    """True when the document had more pages than the configured limit."""

    @property
    def word_count(self) -> int:
        return sum(len(p.words) for p in self.pages)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    type: FieldType = FieldType.TEXT
    description: str = ""
    required: bool = False
    options: tuple[str, ...] = ()
    """Allowed values for selection fields."""
    role: str | None = None
    """Semantic role used by cross-field checks, e.g. "total", "subtotal", "tax", "issue_date"."""
    column_id: int | None = None
    """The Tables column this field is written to, when the schema comes from a table."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type.value,
            "description": self.description,
            "required": self.required,
            "options": list(self.options),
            "role": self.role,
            "column_id": self.column_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldSpec:
        return cls(
            key=str(data["key"]),
            label=str(data["label"]),
            type=FieldType(data.get("type", "text")),
            description=str(data.get("description", "")),
            required=bool(data.get("required", False)),
            options=tuple(str(o) for o in data.get("options", ())),
            role=data.get("role"),
            column_id=data.get("column_id"),
        )


@dataclass(frozen=True, slots=True)
class Schema:
    id: str
    name: str
    fields: tuple[FieldSpec, ...]
    instructions: str = ""
    """Extra guidance for the model, e.g. what kind of document this is."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "instructions": self.instructions,
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schema:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            instructions=str(data.get("instructions", "")),
            fields=tuple(FieldSpec.from_dict(f) for f in data["fields"]),
        )


@dataclass(slots=True)
class Anchor:
    page: int
    boxes: list[Box]
    """One box per line the quote spans."""
    score: float
    """1.0 for an exact match, lower for fuzzy matches."""
    method: str
    """"exact", "compact" (ignoring spaces) or "fuzzy"."""
    matched_text: str


@dataclass(slots=True)
class FieldResult:
    key: str
    value: Any
    """Normalised value (ISO date string, float, str, bool) or None."""
    raw_value: Any
    """What the model returned before normalisation."""
    quote: str | None
    status: FieldStatus
    reasons: list[str] = field(default_factory=list)
    anchor: Anchor | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "raw_value": self.raw_value,
            "quote": self.quote,
            "status": self.status.value,
            "reasons": self.reasons,
            "anchor": None
            if self.anchor is None
            else {
                "page": self.anchor.page,
                "boxes": [b.to_dict() for b in self.anchor.boxes],
                "score": round(self.anchor.score, 3),
                "method": self.anchor.method,
                "matched_text": self.anchor.matched_text,
            },
        }


@dataclass(slots=True)
class CheckResult:
    id: str
    label: str
    passed: bool
    fields: list[str]
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "passed": self.passed,
            "fields": self.fields,
            "detail": self.detail,
        }


@dataclass(slots=True)
class Extraction:
    schema: Schema
    fields: list[FieldResult]
    checks: list[CheckResult]
    pages: list[dict[str, Any]]
    """Per page: index, width, height, text source."""
    truncated: bool = False
    model_output: str = ""
    timings: dict[str, float] = field(default_factory=dict)

    def field(self, key: str) -> FieldResult | None:
        return next((f for f in self.fields if f.key == key), None)

    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in FieldStatus}
        for f in self.fields:
            counts[f.status.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema.to_dict(),
            "fields": [f.to_dict() for f in self.fields],
            "checks": [c.to_dict() for c in self.checks],
            "pages": self.pages,
            "truncated": self.truncated,
            "summary": self.summary(),
            "timings": {k: round(v, 3) for k, v in self.timings.items()},
        }
