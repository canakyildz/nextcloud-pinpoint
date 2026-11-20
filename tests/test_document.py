import io

import pymupdf
import pytest
from PIL import Image

from conftest import dataset_file, requires_ocr
from pinpoint.anchor import DocumentIndex
from pinpoint.document import (
    DocumentError,
    LoadOptions,
    document_text,
    load_document,
    render_page,
    sniff_mime,
)

NO_OCR = LoadOptions(ocr_enabled=False)


def _pdf(text: str, rotate: int = 0, password: str | None = None) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 100), text, fontsize=12)
    page.set_rotation(rotate)
    if password:
        return pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    return pdf.tobytes()


def test_text_layer_words_have_normalised_boxes():
    document = load_document(dataset_file("invoice-01.pdf"), "application/pdf", NO_OCR)
    assert len(document.pages) == 1
    page = document.pages[0]
    assert page.source.value == "text-layer"
    assert page.words
    for word in page.words:
        assert 0 <= word.box.x0 < word.box.x1 <= 1
        assert 0 <= word.box.y0 < word.box.y1 <= 1


def test_document_text_has_page_markers_and_lines():
    text = document_text(load_document(dataset_file("invoice-02.pdf"), None, NO_OCR))
    assert text.startswith("=== Page 1 ===")
    assert "Harbour & Finch Design Ltd" in text


def test_rotated_page_boxes_follow_the_displayed_page():
    upright = load_document(_pdf("Total due 1,234.50 EUR long enough"), None, NO_OCR)
    rotated = load_document(_pdf("Total due 1,234.50 EUR long enough", rotate=90), None, NO_OCR)
    a = DocumentIndex(upright).locate("1,234.50").boxes[0]
    b = DocumentIndex(rotated).locate("1,234.50").boxes[0]
    # Upright text runs left to right near the top; on a page rotated by 90° it runs top to bottom.
    assert (a.x1 - a.x0) > (a.y1 - a.y0)
    assert (b.y1 - b.y0) > (b.x1 - b.x0)
    for box in (a, b):
        assert 0 <= box.x0 < box.x1 <= 1 and 0 <= box.y0 < box.y1 <= 1


def test_password_protected_pdf_is_refused_with_a_clear_message():
    with pytest.raises(DocumentError, match="password"):
        load_document(_pdf("secret invoice text here", password="pw"), None, NO_OCR)


def test_bytes_decide_the_type_not_the_declared_mime():
    assert sniff_mime(dataset_file("invoice-01.pdf"), "image/png") == "application/pdf"
    with pytest.raises(DocumentError, match="Unsupported"):
        sniff_mime(b"PK\x03\x04 zip file", "application/zip")


def test_damaged_pdf():
    with pytest.raises(DocumentError):
        load_document(b"%PDF-1.7 broken", None, NO_OCR)


def test_image_without_ocr_is_refused():
    with pytest.raises(DocumentError, match="OCR"):
        load_document(dataset_file("receipt-01-scan.jpg"), None, NO_OCR)


def test_page_limit_marks_the_document_truncated():
    pdf = pymupdf.open()
    for n in range(3):
        pdf.new_page().insert_text((72, 100), f"Page number {n} with enough text on it", fontsize=12)
    document = load_document(pdf.tobytes(), None, LoadOptions(max_pages=2, ocr_enabled=False))
    assert len(document.pages) == 2
    assert document.truncated


def test_render_pdf_page_and_image():
    png = render_page(dataset_file("invoice-01.pdf"), 0, max_width=600)
    assert Image.open(io.BytesIO(png)).width == 600
    png = render_page(dataset_file("receipt-01-scan.jpg"), 0, max_width=300)
    assert Image.open(io.BytesIO(png)).width == 300
    with pytest.raises(DocumentError):
        render_page(dataset_file("invoice-01.pdf"), 5)


@requires_ocr
@pytest.mark.ocr
def test_scanned_receipt_goes_through_ocr():
    document = load_document(dataset_file("receipt-01-scan.jpg"), None, LoadOptions(ocr_languages="eng+deu"))
    assert document.pages[0].source.value == "ocr"
    assert "sonnenschein" in document_text(document).casefold()
