"""Stage 2: Header/footer boilerplate detection and removal.

Two signals combined, per ISSUES_AND_FIXES.md's design notes:
1. Position: is the line in the top/bottom margin band of the page?
2. Frequency: does a recurring word fragment (n-gram) of this line repeat
   across most pages?

A local trial using only a fixed "first/last 2 lines" window missed footer
lines that sat further from the page edge (e.g. "Order: ZDT3W9PY5",
"Address: 825 S 22nd St") — using a fraction of page height instead of a
fixed line count catches those regardless of how many lines are stacked in
the margin.

Detection is n-gram-based, not whole-line-based (see ISSUES_AND_FIXES.md
Open Issue #1): a whole-line exact match misses a recurring line when noise
(e.g. a semi-transparent watermark overlapping the footer) renders slightly
differently around it on every page — "address: # s #nd st" recurs cleanly
as a *fragment*, but the full line it's embedded in
("attorneysatlaw address: # s #nd st", "a#torneysatlaw address: # s #nd st",
...) is a near-unique string almost every time, so whole-line frequency
counting never crosses the threshold. Counting word n-grams instead finds
the stable fragment regardless of what garbage surrounds it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# Top/bottom fraction of page height considered the "margin band" where
# headers/footers live. Wider than a naive first/last-2-lines window.
MARGIN_FRACTION = 0.15
# A normalized fragment appearing on at least this fraction of pages is
# treated as confirmed boilerplate.
REPEAT_THRESHOLD = 0.6
# Minimum length for a confirmed signature. Stripping uses substring
# containment (see BoilerplateDetector.strip), so an overly short/generic
# signature (e.g. a lone "#" or common short word) risks matching unrelated
# body text. Real header/footer stamps are comfortably longer than this.
MIN_SIGNATURE_LENGTH = 6
# Word n-gram size range scanned per margin line. Covers everything from a
# single distinctive token ("HomeWiseDocs") up to multi-word stamps
# ("Document not for resale", "Address: 825 S 22nd St").
NGRAM_MIN_WORDS = 1
NGRAM_MAX_WORDS = 8

_DIGIT_PATTERN = re.compile(r"\d+")


@dataclass
class Line:
    text: str
    top: float
    bottom: float
    page_height: float

    @property
    def in_margin_band(self) -> bool:
        return (
            self.top <= self.page_height * MARGIN_FRACTION
            or self.bottom >= self.page_height * (1 - MARGIN_FRACTION)
        )


def normalize_line(text: str) -> str:
    """Strip digits so 'Page 3 of 47' and 'Page 4 of 47' normalize the same."""
    return _DIGIT_PATTERN.sub("#", text.strip()).lower()


def _word_ngrams(norm_line: str) -> list[str]:
    """All contiguous word n-grams of the line, sizes NGRAM_MIN_WORDS..NGRAM_MAX_WORDS."""
    tokens = norm_line.split()
    ngrams = []
    for n in range(NGRAM_MIN_WORDS, min(NGRAM_MAX_WORDS, len(tokens)) + 1):
        for i in range(len(tokens) - n + 1):
            ngrams.append(" ".join(tokens[i : i + n]))
    return ngrams


def _keep_maximal_fragments(fragments: set[str]) -> set[str]:
    """Drop any confirmed fragment that is itself a substring of a longer
    confirmed fragment (e.g. "address: #" is redundant once "address: # s
    #nd st" is also confirmed) — keeps the boilerplate set small and readable.
    """
    by_length_desc = sorted(fragments, key=len, reverse=True)
    maximal: list[str] = []
    for frag in by_length_desc:
        if not any(frag in longer for longer in maximal):
            maximal.append(frag)
    return set(maximal)


class BoilerplateDetector:
    """Detects and strips repeated header/footer lines across a document's pages."""

    def __init__(
        self,
        margin_fraction: float = MARGIN_FRACTION,
        repeat_threshold: float = REPEAT_THRESHOLD,
    ):
        self.margin_fraction = margin_fraction
        self.repeat_threshold = repeat_threshold

    def detect(self, pages_lines: list[list[Line]]) -> set[str]:
        """Return the set of normalized boilerplate fragments (word n-grams).

        Counts word n-grams (not whole lines) so a stable recurring fragment
        is still found even when it's embedded in a line that otherwise
        renders slightly differently on every page (watermark bleed, OCR
        noise, positional merges with adjacent text — see module docstring).
        """
        total_pages = len(pages_lines)
        if total_pages == 0:
            return set()

        counter: Counter[str] = Counter()

        for lines in pages_lines:
            seen_this_page: set[str] = set()
            for line in lines:
                if not line.in_margin_band or not line.text.strip():
                    continue
                norm = normalize_line(line.text)
                for ngram in _word_ngrams(norm):
                    if ngram not in seen_this_page:
                        counter[ngram] += 1
                        seen_this_page.add(ngram)

        confirmed = {
            ngram
            for ngram, count in counter.items()
            if count / total_pages >= self.repeat_threshold
            and len(ngram) >= MIN_SIGNATURE_LENGTH
        }

        return _keep_maximal_fragments(confirmed)

    def strip(self, lines: list[Line], boilerplate: set[str]) -> list[Line]:
        """Remove lines matching a confirmed-boilerplate signature.

        Uses substring containment, not exact equality: real PDFs sometimes
        render a footer stamp overlapping or immediately adjacent to body
        text (e.g. a section heading positioned close to the footer band),
        so pdfplumber's word clustering occasionally merges them into one
        line (e.g. "Order: ZDT3W9PY5 YARD EASEMENTS ." or, with no space at
        all, "Order: ZDT3W9PY5YARD"). Exact-match stripping misses these;
        substring containment catches the confirmed boilerplate fragment
        wherever it appears, and drops the whole line it's found in.

        Applied to all lines, not just margin-band ones — once a line is
        confirmed boilerplate by frequency, strip every occurrence even if
        page-height jitter puts one instance slightly outside the margin band.
        """
        kept = []
        for line in lines:
            norm = normalize_line(line.text)
            if any(sig in norm for sig in boilerplate):
                continue
            kept.append(line)
        return kept
