"""Stage 1: PDF extraction with paragraph-aware text and boilerplate-free output.

Unlike a naive `page.extract_text()` join (which produces one text blob per
page with no real paragraph structure), this module:
1. Extracts words with bounding boxes per page
2. Groups words into lines, then lines into paragraphs using vertical-gap
   detection (a gap much larger than normal line spacing means a new
   paragraph, not just wrapped text)
3. Strips repeated header/footer boilerplate (see clean.py) before assembling
   final paragraph text

This directly feeds chunk_document() in chunk.py, which depends on real
`\n\n`-separated paragraphs to chunk correctly (see ISSUES_AND_FIXES.md for
what happens when it doesn't get real paragraph structure).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import pdfplumber

from src.rag.clean import BoilerplateDetector, Line

# A gap between consecutive lines larger than this multiple of the page's
# typical single-line gap is treated as a paragraph break.
PARAGRAPH_GAP_MULTIPLIER = 1.8
# Absolute floor so pages with unusually tight line spacing don't produce
# a near-zero threshold that treats every line as its own paragraph.
MIN_PARAGRAPH_GAP = 4.0


@dataclass
class WordBox:
    text: str
    x0: float
    top: float
    bottom: float


class PageOffset(TypedDict):
    page: int
    start_char: int
    end_char: int


class ExtractedDocument(TypedDict):
    source: str
    full_text: str
    page_offsets: list[PageOffset]
    total_pages: int


def _extract_page_lines(page: "pdfplumber.page.Page") -> list[Line]:
    """Group words on a page into lines, sorted top-to-bottom, left-to-right."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []

    boxes = [WordBox(w["text"], w["x0"], w["top"], w["bottom"]) for w in words]
    boxes.sort(key=lambda b: (round(b.top, 1), b.x0))

    lines: list[Line] = []
    current_words: list[WordBox] = []
    current_top = None

    for box in boxes:
        if current_top is None or abs(box.top - current_top) <= 2.0:
            current_words.append(box)
            current_top = box.top if current_top is None else current_top
        else:
            lines.append(_words_to_line(current_words, page.height))
            current_words = [box]
            current_top = box.top

    if current_words:
        lines.append(_words_to_line(current_words, page.height))

    return lines


def _words_to_line(words: list[WordBox], page_height: float) -> Line:
    words_sorted = sorted(words, key=lambda w: w.x0)
    text = " ".join(w.text for w in words_sorted)
    top = min(w.top for w in words_sorted)
    bottom = max(w.bottom for w in words_sorted)
    return Line(text=text, top=top, bottom=bottom, page_height=page_height)


def _typical_line_gap(lines: list[Line]) -> float:
    """Median gap between consecutive lines, used as the 'normal spacing' baseline."""
    gaps = []
    for i in range(1, len(lines)):
        gap = lines[i].top - lines[i - 1].bottom
        if gap > 0:
            gaps.append(gap)
    if not gaps:
        return MIN_PARAGRAPH_GAP
    gaps.sort()
    return max(gaps[len(gaps) // 2], MIN_PARAGRAPH_GAP)


def _assemble_paragraphs(lines: list[Line]) -> str:
    """Join lines into paragraph-structured text using vertical-gap detection."""
    if not lines:
        return ""

    typical_gap = _typical_line_gap(lines)
    break_threshold = typical_gap * PARAGRAPH_GAP_MULTIPLIER

    paragraphs: list[str] = []
    current_lines: list[str] = [lines[0].text]

    for i in range(1, len(lines)):
        gap = lines[i].top - lines[i - 1].bottom
        if gap > break_threshold:
            paragraphs.append(" ".join(current_lines))
            current_lines = [lines[i].text]
        else:
            current_lines.append(lines[i].text)

    if current_lines:
        paragraphs.append(" ".join(current_lines))

    return "\n\n".join(p for p in paragraphs if p.strip())


def extract_document(pdf_path: Path, strip_boilerplate: bool = True) -> ExtractedDocument:
    """Extract one PDF into paragraph-structured, boilerplate-free text.

    Args:
        pdf_path: Path to the PDF file.
        strip_boilerplate: If True, detect and remove repeated headers/footers
            (page numbers, doc stamps, etc.) before assembling paragraphs.

    Returns:
        ExtractedDocument with full_text (real \n\n paragraph breaks) and
        page_offsets mapping char ranges back to page numbers.
    """
    with pdfplumber.open(pdf_path) as pdf:
        pages_lines: list[list[Line]] = [_extract_page_lines(page) for page in pdf.pages]

    if strip_boilerplate:
        detector = BoilerplateDetector()
        boilerplate = detector.detect(pages_lines)
        pages_lines = [detector.strip(lines, boilerplate) for lines in pages_lines]

    full_text = ""
    page_offsets: list[PageOffset] = []

    for i, lines in enumerate(pages_lines, start=1):
        page_text = _assemble_paragraphs(lines)
        start = len(full_text)
        full_text += page_text + "\n\n"
        page_offsets.append({"page": i, "start_char": start, "end_char": len(full_text)})

    return ExtractedDocument(
        source=pdf_path.name,
        full_text=full_text,
        page_offsets=page_offsets,
        total_pages=len(pages_lines),
    )
