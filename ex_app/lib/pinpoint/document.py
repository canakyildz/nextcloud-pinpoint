"""Turn a PDF or an image into pages of positioned words.

Digital PDFs keep their own text layer, which is exact. Pages without one (scans, photos) go through
Tesseract, which returns a box for every word. Nextcloud's own OCR task type returns plain text without
positions, so it cannot tell us *where* a value is on the page; that is why OCR happens here.
"""

from __future__ import annotations

import io
import logging
import shutil
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageOps

from .model import Box, Document, Page, TextSource, Word

LOG = logging.getLogger(__name__)

PDF_MIME = "application/pdf"
IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/tiff", "image/webp", "image/bmp", "image/gif"})
SUPPORTED_MIMES = frozenset({PDF_MIME, *IMAGE_MIMES})

MIN_TEXT_LAYER_CHARS = 20
"""A PDF page with less text than this is treated as a scan and sent to OCR."""

OCR_DPI = 300
MAX_IMAGE_PIXELS = 80_000_000


class DocumentError(ValueError):
    """The file cannot be read as a document. The message is safe to show to the user."""


@dataclass(frozen=True, slots=True)
class LoadOptions:
    max_pages: int = 20
    ocr_languages: str = "eng"
    ocr_enabled: bool = True


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def sniff_mime(data: bytes, declared: str | None = None) -> str:
    """Trust the bytes over the declared type: a renamed file should not reach the wrong parser."""
    if data[:5] == b"%PDF-":
        return PDF_MIME
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if declared in SUPPORTED_MIMES:
        return declared
    raise DocumentError("Unsupported file type. Pinpoint reads PDF files and images (PNG, JPEG, TIFF, WebP).")


def load_document(data: bytes, mime: str | None = None, options: LoadOptions | None = None) -> Document:
    options = options or LoadOptions()
    mime = sniff_mime(data, mime)
    document = _load_pdf(data, options) if mime == PDF_MIME else _load_image(data, options)
    if document.word_count == 0:
        if not options.ocr_enabled or not ocr_available():
            raise DocumentError("This document has no text layer and OCR is not available on this server.")
        raise DocumentError("No text could be read from this document.")
    return document


def _load_pdf(data: bytes, options: LoadOptions) -> Document:
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # pymupdf raises its own FileDataError and friends
        raise DocumentError("The PDF could not be opened. It may be damaged.") from exc
    with pdf:
        if pdf.needs_pass:
            raise DocumentError("The PDF is password-protected.")
        pages: list[Page] = []
        for index in range(min(pdf.page_count, options.max_pages)):
            page = pdf[index]
            words = _text_layer_words(page, index)
            if sum(len(w.text) for w in words) >= MIN_TEXT_LAYER_CHARS:
                pages.append(Page(index, page.rect.width, page.rect.height, words, TextSource.TEXT_LAYER))
                continue
            if options.ocr_enabled and ocr_available():
                pixmap = page.get_pixmap(dpi=OCR_DPI)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                ocr_words = _ocr_words(image, index, options.ocr_languages)
                pages.append(Page(index, page.rect.width, page.rect.height, ocr_words, TextSource.OCR))
            else:
                pages.append(Page(index, page.rect.width, page.rect.height, words, TextSource.TEXT_LAYER))
        return Document(pages, truncated=pdf.page_count > options.max_pages)


def _text_layer_words(page: pymupdf.Page, index: int) -> list[Word]:
    width, height = page.rect.width, page.rect.height
    if width <= 0 or height <= 0:
        return []
    # Text extraction reports positions on the unrotated page; map them onto the page as displayed.
    matrix = page.rotation_matrix
    line_ids: dict[tuple[int, int], int] = {}
    words: list[Word] = []
    for x0, y0, x1, y1, raw_text, block_no, line_no, _word_no in page.get_text("words", sort=True):
        # NFKC turns ligatures ("ﬁ") and full-width forms into plain letters, which models read reliably.
        text = unicodedata.normalize("NFKC", raw_text).strip()
        if not text:
            continue
        rect = pymupdf.Rect(x0, y0, x1, y1) * matrix
        line = line_ids.setdefault((block_no, line_no), len(line_ids))
        words.append(
            Word(
                text=text,
                box=Box(
                    index,
                    _clamp(rect.x0 / width),
                    _clamp(rect.y0 / height),
                    _clamp(rect.x1 / width),
                    _clamp(rect.y1 / height),
                ),
                line=line,
            )
        )
    return words


def _load_image(data: bytes, options: LoadOptions) -> Document:
    if not options.ocr_enabled or not ocr_available():
        raise DocumentError("Images need OCR, which is not available on this server.")
    pages: list[Page] = []
    truncated = False
    for index, image in enumerate(_image_frames(data)):
        if index >= options.max_pages:
            truncated = True
            break
        words = _ocr_words(image, index, options.ocr_languages)
        pages.append(Page(index, float(image.width), float(image.height), words, TextSource.OCR))
    return Document(pages, truncated=truncated)


def _image_frames(data: bytes) -> Iterator[Image.Image]:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise DocumentError("The image could not be opened.") from exc
    frame = 0
    while True:
        yield ImageOps.exif_transpose(image).convert("RGB")
        frame += 1
        try:
            image.seek(frame)
        except EOFError:
            return


def _ocr_words(image: Image.Image, index: int, languages: str) -> list[Word]:
    import pytesseract  # noqa: PLC0415 (lazy: the module must load on machines without Tesseract)

    try:
        data = pytesseract.image_to_data(image, lang=languages, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractError as exc:
        LOG.warning("Tesseract failed on page %s: %s", index + 1, exc)
        raise DocumentError(f"OCR failed on page {index + 1}. Check the OCR languages setting.") from exc
    width, height = image.width, image.height
    line_ids: dict[tuple[int, int, int], int] = {}
    words: list[Word] = []
    for i, raw_text in enumerate(data["text"]):
        text = unicodedata.normalize("NFKC", raw_text or "").strip()
        if not text or float(data["conf"][i]) < 0:
            continue
        left, top, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        line = line_ids.setdefault(key, len(line_ids))
        words.append(
            Word(
                text=text,
                box=Box(
                    index,
                    _clamp(left / width),
                    _clamp(top / height),
                    _clamp((left + w) / width),
                    _clamp((top + h) / height),
                ),
                line=line,
            )
        )
    return words


def page_lines(page: Page) -> list[list[Word]]:
    """Words grouped by line, in reading order."""
    lines: dict[int, list[Word]] = {}
    for word in page.words:
        lines.setdefault(word.line, []).append(word)
    return [lines[k] for k in sorted(lines)]


def document_text(document: Document) -> str:
    """Plain text with page markers, as the model sees it."""
    parts: list[str] = []
    for page in document.pages:
        parts.append(f"=== Page {page.index + 1} ===")
        parts.extend(" ".join(w.text for w in line) for line in page_lines(page))
    return "\n".join(parts)


def render_page(data: bytes, page_index: int, mime: str | None = None, max_width: int = 1600) -> bytes:
    """Render one page as PNG for the review screen."""
    mime = sniff_mime(data, mime)
    if mime == PDF_MIME:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if not 0 <= page_index < pdf.page_count:
                raise DocumentError("Page out of range.")
            page = pdf[page_index]
            zoom = min(max_width / page.rect.width, 4.0) if page.rect.width else 1.0
            return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
    for index, frame in enumerate(_image_frames(data)):
        if index == page_index:
            image = frame
            if image.width > max_width:
                image = image.resize((max_width, round(image.height * max_width / image.width)))
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue()
    raise DocumentError("Page out of range.")


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
