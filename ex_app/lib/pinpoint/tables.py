"""Writing extracted values into Nextcloud Tables.

Every row Pinpoint writes carries its provenance inside Tables itself: a "Source" cell that links the
file, and an "Evidence" cell listing, per field, the page and the exact text it was read from. A row
keeps telling you where it came from long after the review screen is gone.
"""

from __future__ import annotations

import json
from typing import Any

from .model import FieldSpec, FieldStatus, FieldType, Schema
from .schemas import EVIDENCE_COLUMN, SOURCE_COLUMN

STATUS_LABELS = {
    FieldStatus.VERIFIED.value: "verified",
    FieldStatus.REVIEW.value: "checked by a person",
    FieldStatus.UNVERIFIED.value: "accepted by a person, no source in the document",
    FieldStatus.MISSING.value: "entered by a person",
}


def column_requests(schema: Schema) -> list[tuple[str, dict[str, Any]]]:
    """The Tables API calls (column kind, body) that create a table for a template schema."""
    requests: list[tuple[str, dict[str, Any]]] = []
    for spec in schema.fields:
        body: dict[str, Any] = {
            "title": spec.label,
            "description": spec.description,
            "mandatory": False,
        }
        if spec.type == FieldType.NUMBER:
            requests.append(("number", {**body, "numberDecimals": 2}))
        elif spec.type == FieldType.DATE:
            requests.append(("datetime", {**body, "subtype": "date"}))
        elif spec.type == FieldType.SELECTION:
            options = [{"id": i, "label": label} for i, label in enumerate(spec.options)]
            requests.append(("selection", {**body, "selectionOptions": json.dumps(options)}))
        elif spec.type == FieldType.BOOLEAN:
            requests.append(
                ("selection", {**body, "subtype": "check", "selectionOptions": "[]", "selectionDefault": "false"})
            )
        else:
            requests.append(("text", {**body, "subtype": "line"}))
    requests.append(
        (
            "text",
            {
                "title": SOURCE_COLUMN,
                "subtype": "rich",
                "description": "The document this row was extracted from (written by Pinpoint).",
            },
        )
    )
    requests.append(
        (
            "text",
            {
                "title": EVIDENCE_COLUMN,
                "subtype": "rich",
                "description": "Where each value was found in the document (written by Pinpoint).",
            },
        )
    )
    return requests


class CellError(ValueError):
    pass


def cell_value(spec: FieldSpec, value: Any, column: dict[str, Any]) -> Any:
    """Convert a reviewed value into what the Tables API stores for that column."""
    if value is None or value == "":
        return None
    if spec.type == FieldType.NUMBER:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise CellError(f"{spec.label}: “{value}” is not a number") from None
    if spec.type == FieldType.DATE:
        return str(value)[:10]
    if spec.type == FieldType.BOOLEAN:
        return "true" if value in (True, "true", "1", 1) else "false"
    if spec.type == FieldType.SELECTION:
        for option in column.get("selectionOptions") or []:
            if str(option.get("label", "")).casefold() == str(value).casefold():
                return option["id"]
        raise CellError(f"{spec.label}: “{value}” is not one of the column's options")
    return str(value)


def _md_escape(text: str) -> str:
    for char in ("\\", "*", "_", "`", "[", "]", "|"):
        text = text.replace(char, "\\" + char)
    return text.replace("\n", " ")


def source_markdown(file_name: str, file_url: str, review_url: str | None = None) -> str:
    line = f"[{_md_escape(file_name)}]({file_url})"
    if review_url:
        line += f" · [review in Pinpoint]({review_url})"
    return line


def evidence_markdown(schema: Schema, result: dict[str, Any], saved: dict[str, Any]) -> str:
    """One line per field: value, status, page and the exact text it came from."""
    fields = {f["key"]: f for f in result.get("fields", [])}
    lines: list[str] = []
    for spec in schema.fields:
        found = fields.get(spec.key, {})
        value = saved.get(spec.key, found.get("value"))
        extracted = found.get("value")
        if value is None or value == "":
            lines.append(f"- **{_md_escape(spec.label)}**: empty")
            continue
        status = STATUS_LABELS.get(found.get("status", ""), "")
        if _differs(spec, value, extracted):
            status = "entered by a person"
        anchor = found.get("anchor")
        where = ""
        if anchor and status != "entered by a person":
            where = f" · page {anchor['page'] + 1} · “{_md_escape(anchor['matched_text'])}”"
        lines.append(f"- **{_md_escape(spec.label)}**: {_md_escape(str(value))}{where} · {status}")
    checks = [c for c in result.get("checks", []) if not c["id"].startswith("required:")]
    for check in checks:
        lines.append(f"- {'✓' if check['passed'] else '✗'} {_md_escape(check['label'])}")
    return "\n".join(lines)


def _differs(spec: FieldSpec, value: Any, extracted: Any) -> bool:
    if extracted is None:
        return True
    if spec.type == FieldType.NUMBER:
        try:
            return abs(float(value) - float(extracted)) > 0.005
        except (TypeError, ValueError):
            return True
    return str(value).strip() != str(extracted).strip()
