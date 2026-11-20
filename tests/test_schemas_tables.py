import json

import pytest

from pinpoint.model import FieldType
from pinpoint.schemas import INVOICE, RECEIPT, schema_from_table, slugify, template
from pinpoint.tables import CellError, cell_value, column_requests, evidence_markdown, source_markdown


def _columns():
    return [
        {"id": 1, "title": "Lieferant", "type": "text", "subtype": "line", "description": "Who sent it"},
        {"id": 2, "title": "Gesamtbetrag", "type": "number", "subtype": ""},
        {"id": 3, "title": "Rechnungsdatum", "type": "datetime", "subtype": "date", "mandatory": True},
        {"id": 4, "title": "Fällig am", "type": "datetime", "subtype": "date"},
        {"id": 5, "title": "Method", "type": "selection", "subtype": "",
         "selectionOptions": [{"id": 0, "label": "Cash"}, {"id": 1, "label": "Card"}]},
        {"id": 6, "title": "Paid", "type": "selection", "subtype": "check"},
        {"id": 7, "title": "Rating", "type": "number", "subtype": "stars"},
        {"id": 8, "title": "Owner", "type": "usergroup", "subtype": ""},
        {"id": 9, "title": "Source", "type": "text", "subtype": "rich"},
        {"id": 10, "title": "Evidence", "type": "text", "subtype": "rich"},
        {"id": 11, "title": "Lieferant", "type": "text", "subtype": "long"},
    ]


def test_table_columns_become_fields():
    schema = schema_from_table({"id": 7, "title": "Rechnungen", "description": "Eingangsrechnungen"}, _columns())
    assert schema.id == "table:7"
    assert schema.instructions == "Eingangsrechnungen"
    by_column = {f.column_id: f for f in schema.fields}
    assert set(by_column) == {1, 2, 3, 4, 5, 6, 11}  # stars, usergroup, Source and Evidence are skipped
    assert by_column[1].description == "Who sent it"
    assert by_column[2].type == FieldType.NUMBER and by_column[2].role == "total"
    assert by_column[3].required and by_column[3].role == "issue_date"
    assert by_column[4].role == "due_date"
    assert by_column[5].options == ("Cash", "Card")
    assert by_column[6].type == FieldType.BOOLEAN
    assert by_column[1].key != by_column[11].key  # duplicate titles get distinct keys


def test_slugify():
    assert slugify("Fällig am (Datum)") == "fallig_am_datum"
    assert slugify("€€€") == "field"


def test_templates():
    assert template("invoice") is INVOICE
    assert template("template:receipt") is RECEIPT
    with pytest.raises(KeyError):
        template("passport")


def test_column_requests_cover_every_field_plus_provenance_columns():
    requests = column_requests(RECEIPT)
    titles = [body["title"] for _, body in requests]
    assert titles == [f.label for f in RECEIPT.fields] + ["Source", "Evidence"]
    selection = dict(requests)["selection"]
    assert json.loads(selection["selectionOptions"])[1] == {"id": 1, "label": "Card"}


def test_cell_values():
    schema = schema_from_table({"id": 1, "title": "T"}, _columns())
    by_column = {f.column_id: f for f in schema.fields}
    columns = {c["id"]: c for c in _columns()}
    assert cell_value(by_column[2], "12.5", columns[2]) == 12.5
    assert cell_value(by_column[3], "2026-03-14", columns[3]) == "2026-03-14"
    assert cell_value(by_column[5], "card", columns[5]) == 1
    assert cell_value(by_column[6], True, columns[6]) == "true"
    assert cell_value(by_column[1], None, columns[1]) is None
    with pytest.raises(CellError):
        cell_value(by_column[5], "Crypto", columns[5])


def test_evidence_lists_page_and_text_and_marks_edits():
    result = {
        "fields": [
            {"key": "merchant", "value": "Corner Market", "status": "verified",
             "anchor": {"page": 0, "matched_text": "Corner *Market*"}},
            {"key": "total", "value": 12.0, "status": "review", "anchor": {"page": 0, "matched_text": "$12.00"}},
            {"key": "date", "value": None, "status": "missing", "anchor": None},
        ],
        "checks": [{"id": "required:merchant", "label": "x", "passed": True}],
    }
    text = evidence_markdown(RECEIPT, result, {"merchant": "Corner Market", "total": 13.0, "date": None})
    assert "**Merchant**: Corner Market · page 1 · “Corner \\*Market\\*” · verified" in text
    assert "**Total amount**: 13.0 · entered by a person" in text
    assert "**Date**: empty" in text


def test_source_markdown_escapes_the_file_name():
    assert source_markdown("a_[b].pdf", "https://x/f/1") == "[a\\_\\[b\\].pdf](https://x/f/1)"
