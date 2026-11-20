from pinpoint.anchor import DocumentIndex
from pinpoint.model import Box, Document, Page, TextSource, Word


def _page(index: int, lines: list[str]) -> Page:
    words = []
    for line_no, line in enumerate(lines):
        x = 0.1
        for token in line.split(" "):
            width = 0.012 * len(token)
            words.append(Word(token, Box(index, x, 0.1 + line_no * 0.03, x + width, 0.12 + line_no * 0.03), line_no))
            x += width + 0.01
    return Page(index, 595, 842, words, TextSource.TEXT_LAYER)


def _index(*pages: list[str]) -> DocumentIndex:
    return DocumentIndex(Document([_page(i, lines) for i, lines in enumerate(pages)]))


def test_exact_match_returns_document_boxes():
    index = _index(["Invoice No. RE-2026-0412", "Total due: 1,234.50 EUR"])
    anchor = index.locate("1,234.50 EUR")
    assert anchor is not None
    assert anchor.method == "exact"
    assert anchor.score == 1.0
    assert anchor.matched_text == "1,234.50 EUR"
    assert len(anchor.boxes) == 1
    assert anchor.boxes[0].page == 0


def test_match_is_case_and_typography_insensitive():
    index = _index(["“Pinecrest Software Inc.”"])
    assert index.locate('"pinecrest software inc."').method == "exact"


def test_short_quote_inside_a_word_is_not_a_match():
    # "50" occurs only inside "1,234.50": pointing at it would be a false source.
    index = _index(["Total 1,234.50"])
    assert index.locate("50") is None


def test_longer_quote_may_end_inside_a_word():
    index = _index(["Pinecrest Software Inc."])
    anchor = index.locate("Pinecrest Software Inc")
    assert anchor is not None
    assert anchor.score < 1.0


def test_quote_across_lines_gets_one_box_per_line():
    index = _index(["Harbour & Finch", "Design Ltd"])
    anchor = index.locate("Harbour & Finch Design Ltd")
    assert anchor is not None
    assert len(anchor.boxes) == 2


def test_compact_match_handles_ocr_splitting_a_number():
    index = _index(["Total 1 234,50 €"])  # OCR split the thousands group into its own word
    anchor = index.locate("1234,50 €")
    assert anchor is not None
    assert anchor.method == "compact"


def test_fuzzy_match_tolerates_ocr_noise_but_scores_lower():
    index = _index(["Bluefield Analytlcs LLC"])  # OCR read i as l
    anchor = index.locate("Bluefield Analytics LLC")
    assert anchor is not None
    assert anchor.method == "fuzzy"
    assert 0.85 <= anchor.score < 0.97


def test_unrelated_quote_is_not_found():
    index = _index(["Invoice", "Total 12.00"])
    assert index.locate("Payable to Contoso Ltd by bank transfer") is None


def test_named_page_is_searched_first():
    index = _index(["Total 10.00"], ["Total 10.00"])
    assert index.locate("Total 10.00", preferred_page=1).page == 1
    assert index.locate("Total 10.00").page == 0


def test_no_break_space_inside_a_word():
    page = Page(0, 595, 842, [Word("9 394,80", Box(0, 0.1, 0.1, 0.2, 0.12), 0)], TextSource.TEXT_LAYER)
    index = DocumentIndex(Document([page]))
    anchor = index.locate("9 394,80")
    assert anchor is not None
    assert anchor.method == "exact"
