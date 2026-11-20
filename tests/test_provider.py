import json

from conftest import ScriptedModel, dataset_file, truth
from pinpoint.document import LoadOptions
from pinpoint.pipeline import PipelineOptions, extract
from pinpoint.provider import INPUT_DOCUMENT, INPUT_KIND, evidence_text, fields_json, provider, task_type
from pinpoint.schemas import INVOICE


def test_task_type_and_provider_shapes():
    tt = task_type("pinpoint")
    p = provider("pinpoint")
    assert tt.id == p.id == p.task_type == "pinpoint:extract_fields"
    assert [s.name for s in tt.input_shape] == [INPUT_DOCUMENT]
    assert [v.value for v in p.optional_input_shape_enum_values[INPUT_KIND]] == ["invoice", "receipt"]


async def test_assistant_output_has_json_and_readable_evidence():
    fields = truth("invoice-02")["fields"]
    fields["iban"] = {"value": "DE00 0000", "quote": "DE00 0000", "page": 1}  # not on the page
    model = ScriptedModel(json.dumps({"fields": fields}))
    extraction = await extract(
        dataset_file("invoice-02.pdf"), INVOICE, model, None, PipelineOptions(load=LoadOptions(ocr_enabled=False))
    )
    data = json.loads(fields_json(extraction))
    assert data["document_type"] == "Invoice"
    assert data["fields"]["total"]["status"] == "verified"
    assert data["fields"]["total"]["page"] == 1
    assert data["fields"]["total"]["boxes"]
    text = evidence_text(extraction)
    assert "✓ Supplier: Harbour & Finch Design Ltd (page 1:" in text
    assert "✗ IBAN: DE00 0000 (no source found)" in text
