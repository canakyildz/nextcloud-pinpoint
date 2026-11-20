"""What to extract. A schema comes from a Nextcloud Tables table (its columns) or from a built-in template.

The table is the schema: add a column to the table and Pinpoint starts extracting it. Column descriptions
are passed to the model as field descriptions, so users steer extraction where they already work.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .model import FieldSpec, FieldType, Schema

SOURCE_COLUMN = "Source"
EVIDENCE_COLUMN = "Evidence"
RESERVED_COLUMNS = frozenset({SOURCE_COLUMN.casefold(), EVIDENCE_COLUMN.casefold()})

INVOICE = Schema(
    id="template:invoice",
    name="Invoice",
    instructions="The document is an invoice or a bill.",
    fields=(
        FieldSpec("supplier", "Supplier", FieldType.TEXT, "Company or person who issued the invoice.", True),
        FieldSpec("invoice_number", "Invoice number", FieldType.TEXT, "The invoice's own number or reference.", True),
        FieldSpec("issue_date", "Issue date", FieldType.DATE, "Date the invoice was issued.", True, role="issue_date"),
        FieldSpec("due_date", "Due date", FieldType.DATE, "Payment due date, if stated.", role="due_date"),
        FieldSpec(
            "currency",
            "Currency",
            FieldType.TEXT,
            "ISO 4217 code such as EUR, USD or GBP. As the quote, copy an amount with its currency symbol.",
            role="currency",
        ),
        FieldSpec("subtotal", "Net amount", FieldType.NUMBER, "Total before tax.", role="subtotal"),
        FieldSpec("tax", "Tax amount", FieldType.NUMBER, "Total tax (VAT) amount.", role="tax"),
        FieldSpec("total", "Total amount", FieldType.NUMBER, "Total amount to pay, including tax.", True, role="total"),
        FieldSpec("iban", "IBAN", FieldType.TEXT, "Supplier's IBAN for payment, if stated."),
    ),
)

RECEIPT = Schema(
    id="template:receipt",
    name="Receipt",
    instructions="The document is a till receipt or a payment receipt.",
    fields=(
        FieldSpec("merchant", "Merchant", FieldType.TEXT, "Name of the shop, restaurant or company.", True),
        FieldSpec("date", "Date", FieldType.DATE, "Date of the purchase.", True, role="issue_date"),
        FieldSpec(
            "currency",
            "Currency",
            FieldType.TEXT,
            "ISO 4217 code such as EUR, USD or GBP. As the quote, copy an amount with its currency symbol.",
            role="currency",
        ),
        FieldSpec("tax", "Tax amount", FieldType.NUMBER, "Total tax (VAT) included, if stated.", role="tax"),
        FieldSpec("total", "Total amount", FieldType.NUMBER, "Total amount paid.", True, role="total"),
        FieldSpec(
            "payment_method",
            "Payment method",
            FieldType.SELECTION,
            "How the purchase was paid.",
            options=("Cash", "Card", "Other"),
        ),
    ),
)

TEMPLATES: dict[str, Schema] = {s.id: s for s in (INVOICE, RECEIPT)}


def template(template_id: str) -> Schema:
    if not template_id.startswith("template:"):
        template_id = f"template:{template_id}"
    try:
        return TEMPLATES[template_id]
    except KeyError:
        raise KeyError(f"Unknown template {template_id!r}") from None


def slugify(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "field"


def column_field_type(column: dict[str, Any]) -> FieldType | None:
    """Map a Tables column to a field type. None means Pinpoint does not fill this column."""
    kind = column.get("type")
    subtype = column.get("subtype") or ""
    if kind == "text" and subtype in ("", "line", "long", "rich"):
        return FieldType.TEXT
    if kind == "number" and subtype == "":
        return FieldType.NUMBER
    if kind == "datetime" and subtype in ("date", ""):
        return FieldType.DATE
    if kind == "selection" and subtype == "":
        return FieldType.SELECTION
    if kind == "selection" and subtype == "check":
        return FieldType.BOOLEAN
    return None


_ROLE_HINTS = {
    "total": ("total", "gesamt", "summe", "montant total", "importe total", "amount due", "grand total"),
    "subtotal": ("net", "subtotal", "netto", "sous-total", "before tax"),
    "tax": ("tax", "vat", "mwst", "ust", "tva", "iva", "kdv"),
    "issue_date": ("invoice date", "issue date", "date", "datum", "rechnungsdatum"),
    "due_date": ("due", "fällig", "faellig", "payment date"),
}


def _guess_role(label: str, field_type: FieldType) -> str | None:
    text = label.casefold()
    if field_type == FieldType.TEXT and any(h in text for h in ("currency", "währung", "devise", "moneda", "valuta")):
        return "currency"
    if field_type == FieldType.NUMBER:
        for role in ("subtotal", "tax", "total"):
            if any(hint in text for hint in _ROLE_HINTS[role]):
                return role
    if field_type == FieldType.DATE:
        if any(hint in text for hint in _ROLE_HINTS["due_date"]):
            return "due_date"
        if any(hint in text for hint in _ROLE_HINTS["issue_date"]):
            return "issue_date"
    return None


def schema_from_table(table: dict[str, Any], columns: list[dict[str, Any]]) -> Schema:
    """Build a schema from a Tables table and its columns (Tables API v1 column objects)."""
    fields: list[FieldSpec] = []
    used: set[str] = set()
    for column in columns:
        title = str(column.get("title", "")).strip()
        if not title or title.casefold() in RESERVED_COLUMNS:
            continue
        field_type = column_field_type(column)
        if field_type is None:
            continue
        key = slugify(title)
        while key in used:
            key = f"{key}_{len(used)}"
        used.add(key)
        options: tuple[str, ...] = ()
        if field_type == FieldType.SELECTION:
            options = tuple(str(o.get("label", "")) for o in column.get("selectionOptions") or [] if o.get("label"))
        fields.append(
            FieldSpec(
                key=key,
                label=title,
                type=field_type,
                description=str(column.get("description") or ""),
                required=bool(column.get("mandatory")),
                options=options,
                role=_guess_role(title, field_type),
                column_id=int(column["id"]),
            )
        )
    description = str(table.get("description") or "").strip()
    return Schema(
        id=f"table:{table['id']}",
        name=str(table.get("title") or f"Table {table['id']}"),
        instructions=description,
        fields=tuple(fields),
    )
