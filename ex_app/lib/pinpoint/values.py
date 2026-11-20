"""Parse numbers and dates the way they are written on real documents.

Invoices are written in many conventions: "1,234.50", "1.234,50", "1 234,50", "1'234.50", "14.03.2026",
"03/14/2026", "14 March 2026", "14. März 2026". The model is asked for normalised values (a plain decimal,
an ISO date); these helpers check that the normalised value really matches what the document says.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Literal

DecimalHint = Literal[",", "."] | None
DateOrder = Literal["dmy", "mdy"] | None

_SPACES = "\u00a0\u202f\u2009\u2007 "
_NUMBER_RE = re.compile(r"[-−(]?\d(?:[\d.,'’" + _SPACES + r"]*\d)?\)?-?")
_NUMBER_TOKEN_RE = re.compile(r"[-−(]?\d(?:[\d.,'’]*\d)?\)?-?")

_MONTHS: dict[str, int] = {}
for _number, _names in enumerate(
    [
        "january jan januar janvier enero gennaio januari janeiro ocak",
        "february feb februar février fevrier febrero febbraio februari fevereiro şubat subat",
        "march mar märz maerz mars marzo maart março marco mart",
        "april apr avril abril aprile nisan",
        "may mai mayo maggio mei maio mayıs mayis",
        "june jun juni juin junio giugno junho haziran",
        "july jul juli juillet julio luglio julho temmuz",
        "august aug août aout agosto augustus ağustos agustos",
        "september sep sept septembre septiembre settembre setembro eylül eylul",
        "october oct oktober octobre octubre ottobre outubro ekim",
        "november nov novembre noviembre novembro kasım kasim",
        "december dec dezember décembre decembre diciembre dicembre dezembro aralık aralik",
    ],
    start=1,
):
    for _name in _names.split():
        _MONTHS[_name] = _number

_MONTH_PATTERN = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))
_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{2,4})\b"), "dmy-dot"),
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"), "ambiguous"),
    (
        re.compile(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\.?\s+(?:de\s+)?(" + _MONTH_PATTERN + r")\.?,?\s+(?:de\s+)?(\d{4})\b",
            re.IGNORECASE,
        ),
        "d-month-y",
    ),
    (
        re.compile(r"\b(" + _MONTH_PATTERN + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.IGNORECASE),
        "month-d-y",
    ),
]


_TYPOGRAPHY = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u00ab": '"',
        "\u00bb": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u202f": " ",
        "\u2009": " ",
    }
)


def normalize_text(value: str) -> str:
    """Case- and width-insensitive form used to compare quotes with the document."""
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(_TYPOGRAPHY)
    return " ".join(value.casefold().split())


def parse_number(text: str | int | float, decimal_hint: DecimalHint = None) -> float | None:
    """Parse one number written in any common convention. Returns None if it is not a number."""
    if isinstance(text, bool):
        return None
    if isinstance(text, int | float):
        return float(text)
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    s = s.replace("−", "-")
    if s.endswith("-"):
        negative, s = True, s[:-1]
    if s.startswith("-"):
        negative, s = not negative, s[1:]
    # Drop currency symbols and codes around the number, keep separators and digits.
    s = re.sub(r"^[^\d]+|[^\d]+$", "", s)
    for space in _SPACES:
        s = s.replace(space, "")
    s = s.replace("'", "").replace("’", "")
    if not s or not re.fullmatch(r"\d[\d.,]*", s):
        return None

    commas, dots = s.count(","), s.count(".")
    if commas and dots:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
    elif commas or dots:
        sep = "," if commas else "."
        count = commas or dots
        after = len(s) - s.rfind(sep) - 1
        if count > 1:
            decimal = None  # several separators of one kind are thousands separators
        elif after == 3:
            # "1,234" or "1.234": thousands, unless the document writes decimals with this separator.
            decimal = sep if decimal_hint == sep else None
        else:
            decimal = sep
    else:
        decimal = None

    if decimal is None:
        digits = s.replace(",", "").replace(".", "")
    else:
        thousands = "." if decimal == "," else ","
        integer, _, fraction = s.rpartition(decimal)
        integer = integer.replace(thousands, "")
        if not re.fullmatch(r"\d*", integer) or not re.fullmatch(r"\d+", fraction):
            return None
        digits = f"{integer or '0'}.{fraction}"
    try:
        value = float(digits)
    except ValueError:
        return None
    return -value if negative else value


def numbers_in(text: str, decimal_hint: DecimalHint = None) -> list[float]:
    """Every number a piece of text could reasonably contain, including space-grouped thousands."""
    candidates: list[float] = []
    for pattern in (_NUMBER_TOKEN_RE, _NUMBER_RE):
        for match in pattern.finditer(text):
            parsed = parse_number(match.group(0).strip(), decimal_hint)
            if parsed is not None:
                candidates.append(parsed)
            # The same digits read with the other decimal convention, when the separator is ambiguous.
            if decimal_hint is None:
                for hint in (",", "."):
                    alt = parse_number(match.group(0).strip(), hint)
                    if alt is not None and alt not in candidates:
                        candidates.append(alt)
    return candidates


def numbers_equal(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.005, abs(b) * 1e-9)


def _year(text: str) -> int:
    year = int(text)
    if year < 100:
        year += 2000 if year < 70 else 1900
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def dates_in(text: str, order: DateOrder = None) -> list[date]:
    """Every date a piece of text contains. Ambiguous "03/04/2026" yields both readings without a hint."""
    found: list[date] = []

    def add(candidate: date | None) -> None:
        if candidate is not None and candidate not in found:
            found.append(candidate)

    for pattern, kind in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            if kind == "ymd":
                add(_safe_date(int(m[1]), int(m[2]), int(m[3])))
            elif kind == "dmy-dot":
                add(_safe_date(_year(m[3]), int(m[2]), int(m[1])))
            elif kind == "ambiguous":
                a, b, year = int(m[1]), int(m[2]), _year(m[3])
                if a > 12 or order == "dmy":
                    add(_safe_date(year, b, a))
                elif b > 12 or order == "mdy":
                    add(_safe_date(year, a, b))
                else:
                    add(_safe_date(year, b, a))
                    add(_safe_date(year, a, b))
            elif kind == "d-month-y":
                add(_safe_date(int(m[3]), _MONTHS[m[2].casefold()], int(m[1])))
            elif kind == "month-d-y":
                add(_safe_date(int(m[3]), _MONTHS[m[1].casefold()], int(m[2])))
    return found


def parse_date(value: object, order: DateOrder = None) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    found = dates_in(value.strip(), order)
    return found[0] if len(found) == 1 else None


def is_ambiguous_date(text: str) -> bool:
    """True when the text holds a date like 03/04/2026 that reads differently in Europe and the US."""
    return any(int(m[1]) <= 12 and int(m[2]) <= 12 and m[1] != m[2] for m in _DATE_PATTERNS[2][0].finditer(text))


def detect_conventions(text: str) -> tuple[DecimalHint, DateOrder]:
    """Guess the document's decimal separator and date order from its unambiguous examples."""
    comma_decimal = len(re.findall(r"\d\.\d{3},\d{1,2}\b", text)) + len(
        re.findall(r"(?<![\d.,])\d{1,3},\d{2}\b(?![.,]\d)", text)
    )
    dot_decimal = len(re.findall(r"\d,\d{3}\.\d{1,2}\b", text)) + len(
        re.findall(r"(?<![\d.,])\d{1,3}\.\d{2}\b(?![.,]\d)", text)
    )
    decimal: DecimalHint = None
    if comma_decimal > dot_decimal:
        decimal = ","
    elif dot_decimal > comma_decimal:
        decimal = "."

    dmy = mdy = 0
    for m in _DATE_PATTERNS[2][0].finditer(text):
        a, b = int(m[1]), int(m[2])
        if a > 12 >= b:
            dmy += 1
        elif b > 12 >= a:
            mdy += 1
    dmy += len(_DATE_PATTERNS[1][0].findall(text))  # 14.03.2026 is always day first
    order: DateOrder = None
    if dmy > mdy:
        order = "dmy"
    elif mdy > dmy:
        order = "mdy"
    return decimal, order
