"""Each status rule, with a positive control next to every negative case."""

import json

import pytest

from conftest import ScriptedModel, dataset_file, truth
from pinpoint.document import LoadOptions, load_document
from pinpoint.model import FieldStatus
from pinpoint.pipeline import PipelineOptions, extract_from_document
from pinpoint.schemas import INVOICE, RECEIPT

NO_OCR = PipelineOptions(load=LoadOptions(ocr_enabled=False))


async def _run(name, schema, overrides=None, drop=()):
    fields = {k: dict(v) for k, v in truth(name)["fields"].items()}
    for key, change in (overrides or {}).items():
        fields[key].update(change)
    for key in drop:
        fields.pop(key)
    document = load_document(dataset_file(f"{name}.pdf"), None, LoadOptions(ocr_enabled=False))
    model = ScriptedModel(json.dumps({"fields": fields}, ensure_ascii=False))
    return await extract_from_document(document, schema, model, NO_OCR)


async def test_ground_truth_is_verified():
    result = await _run("invoice-03", INVOICE)
    statuses = {f.key: f.status for f in result.fields}
    assert statuses["total"] == FieldStatus.VERIFIED
    assert statuses["supplier"] == FieldStatus.VERIFIED
    assert all(c.passed for c in result.checks)
    total = result.field("total")
    assert total.anchor.page == 0
    assert total.anchor.boxes


async def test_currency_code_is_verified_against_its_symbol():
    result = await _run("invoice-03", INVOICE)  # "154,46 €" supports EUR
    assert result.field("currency").status == FieldStatus.VERIFIED


async def test_quote_that_is_not_in_the_document_is_unverified():
    result = await _run("invoice-03", INVOICE, {"supplier": {"value": "Contoso Ltd", "quote": "Contoso Ltd"}})
    assert result.field("supplier").status == FieldStatus.UNVERIFIED
    assert result.field("invoice_number").status == FieldStatus.VERIFIED  # control


async def test_value_that_contradicts_its_quote_goes_to_review():
    t = truth("invoice-03")["fields"]["invoice_number"]
    result = await _run("invoice-03", INVOICE, {"invoice_number": {"value": t["value"] + "9"}})
    field = result.field("invoice_number")
    assert field.status == FieldStatus.REVIEW
    assert "differs" in " ".join(field.reasons)


async def test_number_written_differently_from_the_quote_is_still_verified():
    # The model normalises "154,46 €" to 154.46: same number, different notation.
    result = await _run("invoice-03", INVOICE)
    assert result.field("total").raw_value == pytest.approx(truth("invoice-03")["fields"]["total"]["value"])
    assert result.field("total").status == FieldStatus.VERIFIED


async def test_value_without_quote_is_unverified():
    result = await _run("invoice-03", INVOICE, {"supplier": {"quote": None}})
    assert result.field("supplier").status == FieldStatus.UNVERIFIED


async def test_null_value_is_missing_and_required_check_fails():
    result = await _run("invoice-03", INVOICE, {"supplier": {"value": None, "quote": None}})
    assert result.field("supplier").status == FieldStatus.MISSING
    required = next(c for c in result.checks if c.id == "required:supplier")
    assert not required.passed


async def test_failed_sum_check_sends_all_three_amounts_to_review():
    t = truth("invoice-03")["fields"]["subtotal"]
    # Quote and value agree with each other, but net + tax no longer equals total.
    result = await _run("invoice-03", INVOICE, {"subtotal": {"value": t["value"] + 1}})
    sum_check = next(c for c in result.checks if c.id == "sum:subtotal+tax=total")
    assert not sum_check.passed
    for key in ("subtotal", "tax", "total"):
        assert result.field(key).status == FieldStatus.REVIEW
    assert result.field("supplier").status == FieldStatus.VERIFIED  # control


async def test_due_date_before_issue_date_is_flagged():
    result = await _run(
        "invoice-03", INVOICE, {"due_date": {"value": "2026-01-01", "quote": truth("invoice-03")["fields"]["issue_date"]["quote"]}}
    )
    order = next(c for c in result.checks if c.id == "order:issue<=due")
    assert not order.passed


async def test_selection_read_from_a_paraphrase_goes_to_review():
    # receipt-04 is German: "Bar bezahlt" means paid in cash, but the option text "Cash" is not on the page.
    result = await _run("receipt-04", RECEIPT)
    method = result.field("payment_method")
    assert method.value == "Cash"
    assert method.status == FieldStatus.REVIEW


async def test_selection_written_out_is_verified():
    result = await _run("receipt-01", RECEIPT)  # "Paid by card"
    assert result.field("payment_method").status == FieldStatus.VERIFIED


async def test_value_outside_the_options_goes_to_review():
    result = await _run("receipt-01", RECEIPT, {"payment_method": {"value": "Crypto"}})
    assert result.field("payment_method").status == FieldStatus.REVIEW


async def test_wrong_page_number_is_corrected_not_punished():
    t = truth("invoice-03")["fields"]["supplier"]
    result = await _run("invoice-03", INVOICE, {"supplier": {"page": 3}})
    field = result.field("supplier")
    assert field.status == FieldStatus.VERIFIED
    assert field.anchor.page == 0
    assert t["value"] == field.value
    assert "not on page 3" in " ".join(field.reasons)


async def test_unparseable_number_goes_to_review():
    result = await _run("invoice-03", INVOICE, {"total": {"value": "about one hundred"}})
    assert result.field("total").status in (FieldStatus.REVIEW, FieldStatus.UNVERIFIED)
    assert result.field("total").value is None


async def test_model_that_answers_garbage_twice_raises():
    from pinpoint.prompt import ModelOutputError

    document = load_document(dataset_file("invoice-01.pdf"), None, LoadOptions(ocr_enabled=False))
    model = ScriptedModel("no json here", "still no json")
    with pytest.raises(ModelOutputError):
        await extract_from_document(document, INVOICE, model, NO_OCR)
    assert len(model.prompts) == 2  # the original prompt and one repair attempt


async def test_repair_prompt_recovers():
    document = load_document(dataset_file("invoice-01.pdf"), None, LoadOptions(ocr_enabled=False))
    good = json.dumps({"fields": truth("invoice-01")["fields"]})
    model = ScriptedModel("The supplier is Nordlicht.", good)
    result = await extract_from_document(document, INVOICE, model, NO_OCR)
    assert result.field("supplier").status == FieldStatus.VERIFIED
