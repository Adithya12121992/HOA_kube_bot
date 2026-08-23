"""Unit tests for src/rag/chunk.py - pure functions, no I/O."""

from __future__ import annotations

from src.rag.chunk import (
    OVERLAP_CHARS,
    TARGET_CHUNK_CHARS,
    chunk_document,
    chunks_from_paragraphs,
    classify_doc_type,
    find_articles_in_text,
    find_sections_in_text,
    split_into_sentences,
)


class TestClassifyDocType:
    def test_governing(self):
        assert classify_doc_type("30. CC&Rs (Required Civil Code).pdf") == "governing"
        assert classify_doc_type("Bylaws.pdf") == "governing"

    def test_financial(self):
        assert classify_doc_type("Annual Budget Report.pdf") == "financial"

    def test_report(self):
        assert classify_doc_type("Property Inspection Report.pdf") == "report"
        assert classify_doc_type("Minutes of Regular Board Meeting.pdf") == "report"

    def test_advisory_default_fallback(self):
        assert classify_doc_type("Some Unrecognized Document.pdf") == "advisory"


class TestFindSectionsAndArticles:
    def test_finds_section_numbers(self):
        # SECTION_PATTERN requires a preceding ". " or newline and a following
        # capitalized word - matches how real CC&Rs number their clauses
        # ("Rules apply. 3.1.2 Owners must..."), not an inline "Section 3.1.2" mention.
        text = "Rules apply. 3.1.2 Detailed rule text here. More text.\n4.5 Another Rule applies."
        found = find_sections_in_text(text)
        assert "3.1.2" in found.values()
        assert "4.5" in found.values()

    def test_offset_applied_to_positions(self):
        text = "Intro text.\n3.1 Rules Apply Here."
        found_no_offset = find_sections_in_text(text, start_offset=0)
        found_with_offset = find_sections_in_text(text, start_offset=100)
        assert list(found_with_offset.keys())[0] == list(found_no_offset.keys())[0] + 100

    def test_finds_article_headings(self):
        text = "ARTICLE IV Governance. ARTICLE 12 Something."
        found = find_articles_in_text(text)
        assert "IV" in found.values()
        assert "12" in found.values()


class TestSplitIntoSentences:
    def test_splits_on_sentence_boundaries(self):
        result = split_into_sentences("First sentence. Second sentence! Third one?")
        assert len(result) == 3

    def test_empty_paragraph_returns_empty(self):
        assert split_into_sentences("   ") == []


class TestChunksFromParagraphs:
    def test_small_input_collapses_to_one_chunk(self):
        paragraphs = ["Short paragraph one.", "Short paragraph two."]
        chunks = chunks_from_paragraphs(paragraphs)
        assert len(chunks) == 1

    def test_advances_past_overlap_budget_each_chunk(self):
        """Regression test for the 18x-too-many-chunks bug (ISSUES_AND_FIXES #1):
        char_start must advance by at least (TARGET_CHUNK_CHARS - OVERLAP_CHARS)
        between consecutive chunks, not just by a few hundred characters."""
        big_paragraph = "Sentence about HOA rules and regulations. " * 400  # ~17,600 chars
        chunks = chunks_from_paragraphs([big_paragraph])
        assert len(chunks) > 1

        min_advance = TARGET_CHUNK_CHARS - OVERLAP_CHARS
        for (text_a, start_a, _), (text_b, start_b, _) in zip(chunks, chunks[1:]):
            assert start_b - start_a >= min_advance * 0.5  # allow sentence-boundary slack

    def test_no_near_duplicate_consecutive_chunks(self):
        sentences = [
            f"Section {i}: owners of Lot {i} must comply with rule number {i} regarding common area use."
            for i in range(400)
        ]
        big_paragraph = " ".join(sentences)
        chunks = chunks_from_paragraphs([big_paragraph])
        texts = [c[0] for c in chunks]
        assert len(chunks) > 1
        for a, b in zip(texts, texts[1:]):
            overlap_ratio = len(set(a.split()) & set(b.split())) / max(len(set(a.split())), 1)
            assert overlap_ratio < 0.9  # some overlap is expected/intended, but not near-total duplication

    def test_chunk_size_stays_near_target(self):
        big_paragraph = "Owners must comply with all governing documents. " * 500
        chunks = chunks_from_paragraphs([big_paragraph])
        for text, _, _ in chunks[:-1]:  # last chunk is allowed to be shorter
            assert len(text) <= TARGET_CHUNK_CHARS * 1.5


class TestChunkDocument:
    def test_produces_records_with_correct_page_mapping(self):
        full_text = "Page one content here.\n\nPage two content here."
        page_offsets = [
            {"page": 1, "start_char": 0, "end_char": 24},
            {"page": 2, "start_char": 24, "end_char": 48},
        ]
        records = chunk_document("test.pdf", full_text, page_offsets)
        assert len(records) >= 1
        assert all(r["source"] == "test.pdf" for r in records)
        assert all(r["chunk_id"].startswith("test.pdf:chunk_") for r in records)

    def test_toc_region_section_not_used_for_inherited_fallback(self):
        """TOC-region filtering (is_ccrs=True) only affects the *inherited*
        fallback label (a chunk with no section number of its own borrowing
        the most recent one) - a section number literally printed inside a
        chunk's own text is still picked up regardless of position, since
        that's real content, not a TOC artifact."""
        toc_like = "1.1 Table of contents entry. " * 50
        # No section number of its own - must fall back to inheritance, or none.
        no_section_content = "\n\n" + "This paragraph mentions no section numbers at all whatsoever here. " * 50
        full_text = toc_like + no_section_content
        records = chunk_document("ccrs.pdf", full_text, [], is_ccrs=True)

        second_chunk = next((r for r in records if not r["sections"]), None)
        assert second_chunk is not None
        # TOC-region "1.1" must not be borrowed as an inherited label.
        assert second_chunk["section_inherited"] != "1.1"
