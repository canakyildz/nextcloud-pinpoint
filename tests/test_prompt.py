import pytest

from pinpoint.model import FieldSpec, FieldType, Schema
from pinpoint.prompt import ModelOutputError, build_prompt, field_answers, parse_model_json
from pinpoint.schemas import INVOICE, RECEIPT


def test_prompt_lists_fields_with_formats_and_contains_the_document():
    prompt = build_prompt(RECEIPT, "=== Page 1 ===\nCorner Market\nTOTAL $12.00")
    assert '"total" (Total amount; number' in prompt
    assert '"date" (Date; date; write it as YYYY-MM-DD)' in prompt
    assert '"payment_method" (Payment method; one of: "Cash", "Card", "Other")' in prompt
    assert "TOTAL $12.00" in prompt
    assert "character for character" in prompt


def test_long_documents_are_cut_and_the_model_is_told():
    prompt = build_prompt(INVOICE, "x" * 100, max_chars=10)
    assert "x" * 11 not in prompt
    assert "cut here" in prompt


@pytest.mark.parametrize(
    "answer",
    [
        '{"fields": {"total": {"value": 1, "quote": "1", "page": 1}}}',
        'Sure! Here it is:\n```json\n{"fields": {"total": {"value": 1}}}\n```\nAnything else?',
        '<think>The total is 1, so...</think>{"fields": {"total": {"value": 1,},},}',
    ],
)
def test_parse_model_json_tolerates_common_wrappers(answer):
    assert "fields" in parse_model_json(answer)


@pytest.mark.parametrize("answer", ["", "I could not read the document.", "{not json at all}", "[1, 2]"])
def test_parse_model_json_rejects_non_json(answer):
    with pytest.raises(ModelOutputError):
        parse_model_json(answer)


def test_field_answers_accepts_labels_bare_values_and_missing_wrapper():
    schema = Schema(
        "s",
        "S",
        (
            FieldSpec("total", "Total amount", FieldType.NUMBER),
            FieldSpec("supplier", "Supplier"),
            FieldSpec("date", "Date", FieldType.DATE),
        ),
    )
    answers = field_answers({"Total Amount": {"value": 5, "quote": "5.00", "page": 1}, "supplier": "ACME"}, schema)
    assert answers["total"] == {"value": 5, "quote": "5.00", "page": 1}
    assert answers["supplier"] == {"value": "ACME", "quote": None, "page": None}
    assert answers["date"] == {"value": None, "quote": None, "page": None}


def test_field_answers_rejects_a_non_object():
    with pytest.raises(ModelOutputError):
        field_answers({"fields": ["a"]}, INVOICE)
