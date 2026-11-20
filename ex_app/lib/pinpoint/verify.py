"""Decide how far each extracted value can be trusted.

The status never comes from the model's own confidence. It comes from three things Pinpoint can check:
1. Is the quote really in the document? (anchor)
2. Does the value agree with the text at that spot? (consistency)
3. Do the values agree with each other? (cross-field checks, e.g. net + tax = total)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .anchor import DocumentIndex
from .model import CheckResult, FieldResult, FieldSpec, FieldStatus, FieldType, Schema
from .values import (
    DateOrder,
    DecimalHint,
    dates_in,
    is_ambiguous_date,
    normalize_text,
    numbers_equal,
    numbers_in,
    parse_date,
    parse_number,
)

VERIFIED_MIN_SCORE = 0.95
SUM_TOLERANCE = 0.011

_CURRENCY_SYMBOLS = {
    "EUR": ("€", "eur", "euro"),
    "USD": ("$", "usd", "us$"),
    "GBP": ("£", "gbp"),
    "JPY": ("¥", "jpy", "yen"),
    "CHF": ("chf", "fr."),
    "TRY": ("₺", "try", "tl"),
    "PLN": ("zł", "zl", "pln"),
    "SEK": ("kr", "sek"),
    "NOK": ("kr", "nok"),
    "DKK": ("kr", "dkk"),
    "INR": ("₹", "inr"),
}
_TRUE_WORDS = ("yes", "true", "paid", "ja", "oui", "sí", "si", "evet", "x", "✓", "✔")
_FALSE_WORDS = ("no", "false", "unpaid", "nein", "non", "hayır", "hayir")


def normalize_value(spec: FieldSpec, raw: Any, decimal: DecimalHint, order: DateOrder) -> tuple[Any, str | None]:
    """Turn the model's value into the field's type. Returns (value, problem)."""
    if raw is None or (isinstance(raw, str) and raw.strip().casefold() in ("", "null", "none", "n/a")):
        return None, None
    if spec.type == FieldType.NUMBER:
        number = parse_number(raw if isinstance(raw, int | float) else str(raw), decimal)
        if number is None:
            return None, f"“{raw}” is not a number"
        return number, None
    if spec.type == FieldType.DATE:
        parsed = parse_date(str(raw), order)
        if parsed is None:
            return None, f"“{raw}” is not a date"
        return parsed.isoformat(), None
    if spec.type == FieldType.BOOLEAN:
        if isinstance(raw, bool):
            return raw, None
        folded = str(raw).strip().casefold()
        if folded in _TRUE_WORDS:
            return True, None
        if folded in _FALSE_WORDS:
            return False, None
        return None, f"“{raw}” is not yes or no"
    if spec.type == FieldType.SELECTION:
        text = str(raw).strip()
        for option in spec.options:
            if option.casefold() == text.casefold():
                return option, None
        return text, f"“{text}” is not one of the column's options"
    text = str(raw).strip()
    if spec.role == "currency":
        text = _currency_code(text)
    return text, None


def _currency_code(text: str) -> str:
    """ "€" → "EUR": the column holds codes, the document often shows symbols."""
    folded = text.casefold()
    for code, symbols in _CURRENCY_SYMBOLS.items():
        if folded == code.casefold() or (folded in symbols and folded not in ("kr", "fr.")):
            return code
    return text


def value_matches_text(spec: FieldSpec, value: Any, text: str, decimal: DecimalHint, order: DateOrder) -> bool:
    """Does `text` (taken from the document) actually say `value`?"""
    if spec.type == FieldType.NUMBER:
        return any(numbers_equal(n, float(value)) for n in numbers_in(text, decimal))
    if spec.type == FieldType.DATE:
        return date.fromisoformat(value) in dates_in(text, order)
    folded_text = normalize_text(text)
    if spec.type == FieldType.BOOLEAN:
        return False  # yes/no is always an interpretation of the text
    folded_value = normalize_text(str(value))
    if not folded_value:
        return False
    if folded_value in folded_text:
        return True
    # No fuzzy matching for text: "RE-67859" is not "RE-6785". A value is verified only when the document
    # says it literally (ignoring case and typography), or shows a currency's symbol for its code.
    upper = str(value).strip().upper()
    return upper in _CURRENCY_SYMBOLS and any(symbol in folded_text for symbol in _CURRENCY_SYMBOLS[upper])


def verify_field(
    spec: FieldSpec,
    answer: dict[str, Any],
    index: DocumentIndex,
    decimal: DecimalHint,
    order: DateOrder,
) -> FieldResult:
    raw = answer.get("value")
    quote = answer.get("quote")
    quote = str(quote).strip() if quote not in (None, "") else None
    value, problem = normalize_value(spec, raw, decimal, order)

    if value is None and problem is None:
        return FieldResult(
            spec.key, None, raw, quote, FieldStatus.MISSING, ["The model found no value in the document."]
        )

    reasons: list[str] = []
    if problem:
        reasons.append(problem)

    if quote is None:
        reasons.append("The model gave no quote, so the value cannot be traced to the document.")
        return FieldResult(spec.key, value, raw, None, FieldStatus.UNVERIFIED, reasons)

    page = answer.get("page")
    preferred = int(page) - 1 if isinstance(page, int | float) and not isinstance(page, bool) else None
    anchor = index.locate(quote, preferred)
    if anchor is None:
        reasons.append("The quoted text does not appear in the document.")
        return FieldResult(spec.key, value, raw, quote, FieldStatus.UNVERIFIED, reasons)

    status = FieldStatus.VERIFIED
    if preferred is not None and anchor.page != preferred:
        reasons.append(f"Found on page {anchor.page + 1}, not on page {preferred + 1} as the model said.")
    if anchor.score < VERIFIED_MIN_SCORE:
        status = FieldStatus.REVIEW
        reasons.append(f"The quote only approximately matches the document ({round(anchor.score * 100)}%).")
    if problem:
        status = FieldStatus.REVIEW
    elif not value_matches_text(spec, value, anchor.matched_text, decimal, order):
        status = FieldStatus.REVIEW
        if spec.type in (FieldType.SELECTION, FieldType.BOOLEAN):
            reasons.append("The value is the model's reading of the quoted text, not a literal copy.")
        else:
            reasons.append("The value differs from what the quoted text says.")
    if spec.type == FieldType.DATE and order is None and is_ambiguous_date(anchor.matched_text):
        status = FieldStatus.REVIEW
        reasons.append("The date could be day/month or month/day; the document gives no other hint.")
    return FieldResult(spec.key, value, raw, quote, status, reasons, anchor)


def run_checks(schema: Schema, results: list[FieldResult]) -> list[CheckResult]:
    by_role: dict[str, FieldResult] = {}
    for spec in schema.fields:
        result = next(r for r in results if r.key == spec.key)
        if spec.role and spec.role not in by_role:
            by_role[spec.role] = result
    checks: list[CheckResult] = []

    for spec in schema.fields:
        if spec.required:
            result = next(r for r in results if r.key == spec.key)
            checks.append(
                CheckResult(
                    id=f"required:{spec.key}",
                    label=f"{spec.label} is present",
                    passed=result.value is not None,
                    fields=[spec.key],
                    detail="" if result.value is not None else "This field is required but was not found.",
                )
            )

    subtotal, tax, total = by_role.get("subtotal"), by_role.get("tax"), by_role.get("total")
    if subtotal and tax and total and None not in (subtotal.value, tax.value, total.value):
        expected = float(subtotal.value) + float(tax.value)
        passed = abs(expected - float(total.value)) <= SUM_TOLERANCE
        checks.append(
            CheckResult(
                id="sum:subtotal+tax=total",
                label="Net amount + tax = total",
                passed=passed,
                fields=[subtotal.key, tax.key, total.key],
                detail="" if passed else f"{subtotal.value:g} + {tax.value:g} = {expected:.2f}, not {total.value:g}",
            )
        )

    issued, due = by_role.get("issue_date"), by_role.get("due_date")
    if issued and due and issued.value and due.value:
        passed = date.fromisoformat(due.value) >= date.fromisoformat(issued.value)
        checks.append(
            CheckResult(
                id="order:issue<=due",
                label="Due date is not before the issue date",
                passed=passed,
                fields=[issued.key, due.key],
                detail="" if passed else f"Due {due.value} is before issue {issued.value}",
            )
        )

    for check in checks:
        if check.passed or check.id.startswith("required:"):
            continue
        for result in results:
            if result.key in check.fields and result.status == FieldStatus.VERIFIED:
                result.status = FieldStatus.REVIEW
                result.reasons.append(f"Check failed: {check.label}.")
    return checks
