"""Find a quote from the model in the document and return the boxes it covers.

The model is asked to copy, for every value, the exact text it read it from. This module looks that text
up in the words the document actually contains. Boxes always come from the document's own word
positions, never from the model, so a highlight can only point at text that is really on the page.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from .model import Anchor, Box, Document, Page
from .values import normalize_text

EXACT_SCORE = 1.0
INNER_SCORE = 0.97
"""Exact match that starts or ends inside a word, e.g. "Inc" in "Inc.". Accepted for longer quotes only."""
COMPACT_SCORE = 0.96
"""Match after removing all spaces, for OCR that splits or joins words differently."""
FUZZY_THRESHOLD = 85.0
MIN_INNER_LENGTH = 6
MIN_FUZZY_LENGTH = 4


@dataclass(slots=True)
class _PageIndex:
    page: Page
    text: str
    """Normalised words joined by single spaces."""
    starts: list[int]
    ends: list[int]
    compact: str
    """`text` without spaces."""
    compact_owner: list[int]
    """For every character of `compact`, the index of the word it belongs to."""


class DocumentIndex:
    def __init__(self, document: Document) -> None:
        self.document = document
        self._pages = [self._index_page(page) for page in document.pages]

    @staticmethod
    def _index_page(page: Page) -> _PageIndex:
        parts: list[str] = []
        starts: list[int] = []
        ends: list[int] = []
        compact: list[str] = []
        compact_owner: list[int] = []
        position = 0
        for i, word in enumerate(page.words):
            # A "word" can hold a no-break space ("9 394,80" in French), which normalises to a space.
            token = normalize_text(word.text)
            if parts:
                position += 1  # the joining space
            starts.append(position)
            parts.append(token)
            position += len(token)
            ends.append(position)
            squeezed = token.replace(" ", "")
            compact.append(squeezed)
            compact_owner.extend([i] * len(squeezed))
        return _PageIndex(page, " ".join(parts), starts, ends, "".join(compact), compact_owner)

    def locate(self, quote: str, preferred_page: int | None = None) -> Anchor | None:
        """Find `quote`, trying the page the model named first. `preferred_page` is zero-based."""
        needle = normalize_text(quote)
        if not needle:
            return None
        pages = sorted(
            self._pages,
            key=lambda p: (p.page.index != preferred_page, p.page.index),
        )
        for strategy in (self._exact, self._compact):
            for page in pages:
                anchor = strategy(page, needle)
                if anchor is not None:
                    return anchor
        if len(needle) < MIN_FUZZY_LENGTH:
            return None
        best: Anchor | None = None
        for page in pages:
            anchor = self._fuzzy(page, needle)
            if anchor is not None and (best is None or anchor.score > best.score):
                best = anchor
        return best

    def _exact(self, index: _PageIndex, needle: str) -> Anchor | None:
        inner: Anchor | None = None
        start = index.text.find(needle)
        while start != -1:
            end = start + len(needle)
            first, last = self._words_for_span(index, start, end)
            on_boundary = index.starts[first] == start and index.ends[last] == end
            if on_boundary:
                return self._anchor(index, first, last, EXACT_SCORE, "exact")
            if inner is None and len(needle) >= MIN_INNER_LENGTH:
                inner = self._anchor(index, first, last, INNER_SCORE, "exact")
            start = index.text.find(needle, start + 1)
        return inner

    def _compact(self, index: _PageIndex, needle: str) -> Anchor | None:
        compact_needle = needle.replace(" ", "")
        if len(compact_needle) < MIN_INNER_LENGTH:
            return None
        start = index.compact.find(compact_needle)
        if start == -1:
            return None
        first = index.compact_owner[start]
        last = index.compact_owner[start + len(compact_needle) - 1]
        return self._anchor(index, first, last, COMPACT_SCORE, "compact")

    def _fuzzy(self, index: _PageIndex, needle: str) -> Anchor | None:
        if not index.text:
            return None
        alignment = fuzz.partial_ratio_alignment(needle, index.text, score_cutoff=FUZZY_THRESHOLD)
        if alignment is None or alignment.dest_end <= alignment.dest_start:
            return None
        first, last = self._words_for_span(index, alignment.dest_start, alignment.dest_end)
        return self._anchor(index, first, last, alignment.score / 100.0, "fuzzy")

    @staticmethod
    def _words_for_span(index: _PageIndex, start: int, end: int) -> tuple[int, int]:
        first = next(i for i, e in enumerate(index.ends) if e > start)
        last = max(i for i, s in enumerate(index.starts) if s < end)
        return first, max(first, last)

    @staticmethod
    def _anchor(index: _PageIndex, first: int, last: int, score: float, method: str) -> Anchor:
        words = index.page.words[first : last + 1]
        boxes: list[Box] = []
        current_line: int | None = None
        for word in words:
            if boxes and word.line == current_line:
                boxes[-1] = boxes[-1].union(word.box)
            else:
                boxes.append(word.box)
                current_line = word.line
        return Anchor(
            page=index.page.index,
            boxes=boxes,
            score=score,
            method=method,
            matched_text=" ".join(w.text for w in words),
        )
