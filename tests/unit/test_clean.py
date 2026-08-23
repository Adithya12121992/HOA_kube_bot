"""Unit tests for src/rag/clean.py - BoilerplateDetector, pure logic, no I/O."""

from __future__ import annotations

from src.rag.clean import BoilerplateDetector, Line, normalize_line


def make_line(text: str, in_margin: bool, page_height: float = 800.0) -> Line:
    if in_margin:
        top, bottom = 10.0, 20.0  # well within the top margin band
    else:
        top, bottom = 400.0, 410.0  # middle of the page
    return Line(text=text, top=top, bottom=bottom, page_height=page_height)


class TestNormalizeLine:
    def test_digits_normalized_to_hash(self):
        assert normalize_line("Page 3 of 47") == normalize_line("Page 4 of 47")

    def test_lowercased_and_stripped(self):
        assert normalize_line("  HomeWiseDocs  ") == "homewisedocs"


class TestBoilerplateDetectorDetect:
    def test_finds_repeated_margin_footer(self):
        pages = [
            [make_line("HomeWiseDocs", in_margin=True), make_line("Real body text here.", in_margin=False)]
            for _ in range(10)
        ]
        detector = BoilerplateDetector()
        boilerplate = detector.detect(pages)
        assert any("homewisedocs" in frag for frag in boilerplate)

    def test_ignores_non_repeating_body_text(self):
        pages = [
            [make_line(f"Unique content on page {i}", in_margin=False)]
            for i in range(10)
        ]
        detector = BoilerplateDetector()
        boilerplate = detector.detect(pages)
        assert boilerplate == set()

    def test_ignores_content_outside_margin_band_even_if_repeated(self):
        pages = [
            [make_line("Board of Directors", in_margin=False)]
            for _ in range(10)
        ]
        detector = BoilerplateDetector()
        boilerplate = detector.detect(pages)
        assert boilerplate == set()

    def test_below_repeat_threshold_not_confirmed(self):
        # Only appears on 2/10 pages - well under the 0.6 threshold
        pages = [[make_line("Rare Stamp Text Here", in_margin=True)] if i < 2 else [make_line("", in_margin=True)] for i in range(10)]
        detector = BoilerplateDetector()
        boilerplate = detector.detect(pages)
        assert not any("rare stamp" in frag for frag in boilerplate)

    def test_empty_input_returns_empty_set(self):
        assert BoilerplateDetector().detect([]) == set()


class TestBoilerplateDetectorStrip:
    def test_strips_line_containing_confirmed_fragment(self):
        lines = [Line("Order: ZDT3W9PY5 YARD EASEMENTS", 10, 20, 800), Line("Real content line", 400, 410, 800)]
        kept = BoilerplateDetector().strip(lines, {"order: zdt#w#py#"})
        assert len(kept) == 1
        assert kept[0].text == "Real content line"

    def test_catches_merged_variant_without_space(self):
        """Regression test (ISSUES_AND_FIXES #3): substring containment must catch
        footer text merged with no space, e.g. 'Order: ZDT3W9PY5YARD'."""
        lines = [Line("Order: ZDT3W9PY5YARD", 10, 20, 800)]
        kept = BoilerplateDetector().strip(lines, {"order: zdt#w#py#"})
        assert kept == []

    def test_keeps_lines_without_boilerplate(self):
        lines = [Line("Normal sentence about HOA rules.", 400, 410, 800)]
        kept = BoilerplateDetector().strip(lines, {"homewisedocs"})
        assert len(kept) == 1
