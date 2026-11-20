from datetime import date

import pytest

from pinpoint.values import (
    dates_in,
    detect_conventions,
    is_ambiguous_date,
    normalize_text,
    numbers_in,
    parse_date,
    parse_number,
)


@pytest.mark.parametrize(
    ("text", "hint", "expected"),
    [
        ("1,234.56", None, 1234.56),
        ("1.234,56", None, 1234.56),
        ("1 234,56", None, 1234.56),
        ("1 234,56 €", None, 1234.56),
        ("1'234.50 CHF", None, 1234.5),
        ("€ 99", None, 99.0),
        ("$0.99", None, 0.99),
        ("(12.50)", None, -12.5),
        ("12.50-", None, -12.5),
        ("−7,00", None, -7.0),
        ("1,234", None, 1234.0),
        ("1,234", ",", 1.234),
        ("1.234", ".", 1.234),
        ("1.234.567", None, 1234567.0),
        ("12,5", None, 12.5),
        (42, None, 42.0),
    ],
)
def test_parse_number(text, hint, expected):
    assert parse_number(text, hint) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "1.2.3,4.5", "--", True])
def test_parse_number_rejects_non_numbers(text):
    assert parse_number(text) is None


def test_numbers_in_finds_space_grouped_and_ambiguous_readings():
    found = numbers_in("Total TTC: 9 394,80 € (2 items)")
    assert 9394.80 in found
    assert 2.0 in found


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-03-14", date(2026, 3, 14)),
        ("14.03.2026", date(2026, 3, 14)),
        ("14. 3. 26", date(2026, 3, 14)),
        ("03/14/2026", date(2026, 3, 14)),
        ("14/03/2026", date(2026, 3, 14)),
        ("14 March 2026", date(2026, 3, 14)),
        ("March 14, 2026", date(2026, 3, 14)),
        ("14. März 2026", date(2026, 3, 14)),
        ("14 mars 2026", date(2026, 3, 14)),
        ("14 de marzo de 2026", date(2026, 3, 14)),
        ("14 Mart 2026", date(2026, 3, 14)),
        ("1st Feb 2026", date(2026, 2, 1)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_ambiguous_date_yields_both_readings_without_a_hint():
    assert dates_in("05/03/2026") == [date(2026, 3, 5), date(2026, 5, 3)]
    assert dates_in("05/03/2026", "dmy") == [date(2026, 3, 5)]
    assert dates_in("05/03/2026", "mdy") == [date(2026, 5, 3)]
    assert parse_date("05/03/2026") is None  # two readings: not a usable value on its own
    assert is_ambiguous_date("05/03/2026")
    assert not is_ambiguous_date("14/03/2026")
    assert not is_ambiguous_date("03/03/2026")  # same either way


def test_impossible_dates_are_ignored():
    assert dates_in("31.02.2026") == []


def test_detect_conventions():
    assert detect_conventions("Total 1.234,56 €  Datum 14.03.2026") == (",", "dmy")
    assert detect_conventions("Total $1,234.56 due 03/14/2026") == (".", "mdy")
    assert detect_conventions("Invoice") == (None, None)


def test_normalize_text_ignores_case_width_and_typography():
    assert normalize_text("  “Total” DUE  ") == '"total" due'
    assert normalize_text("ﬁle – 1") == "file - 1"
