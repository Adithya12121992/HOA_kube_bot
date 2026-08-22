"""Stage 3a: Hybrid chunking strategy for RAG.

Loads documents.json and produces chunks.json with:
- Recursive splitting (paragraphs → sentences → char-limited chunks)
- Soft section boundaries (prefer splitting at section numbers like 3.1.2)
- Section/article metadata for citations
- Page mapping via character offsets
- Image caption chunks from optional captions.json

Run: python chunk.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, TypedDict

DOCUMENTS_PATH = Path("documents.json")
CHUNKS_PATH = Path("chunks.json")
CAPTIONS_PATH = Path("captions.json")

# Chunking parameters
TARGET_CHUNK_CHARS = 3200  # ~800 tokens at 4 chars/token
OVERLAP_CHARS = 300  # Bounded char-budget overlap between consecutive chunks (~10% of target)
TOC_REGION_FRACTION = 0.10  # Ignore section patterns in first 10% of doc

# Regex patterns
SECTION_PATTERN = re.compile(
    r"(?<=[.\n])\s*(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+(?=[A-Z])"
)
ARTICLE_PATTERN = re.compile(r"ARTICLE\s+([IVX]+|[0-9]+)", re.IGNORECASE)
SENTENCE_PATTERN = re.compile(r"(?<=[.!?:])\s+(?=[A-Z])|(?<=[.!?])\n+")


class ChunkRecord(TypedDict):
    chunk_id: str
    source: str
    text: str
    doc_type: str  # Classification: governing, financial, advisory, report
    sections: list[str]  # Section numbers found within this chunk
    section_inherited: Optional[str]  # Fallback: prior section if none found and within 1500 chars
    article: Optional[str]  # ARTICLE heading (inheritance appropriate for articles)
    page_start: int
    page_end: int
    char_start: int
    char_end: int


class ImageCaptionChunk(TypedDict):
    chunk_id: str
    source: str
    text: str
    page: int
    image_path: str
    type: str


# --- Chunking utilities -------------------------------------------------------


def classify_doc_type(source: str) -> str:
    """Classify document type based on filename.

    Returns: 'governing', 'financial', 'advisory', or 'report'
    """
    source_lower = source.lower()

    if any(x in source_lower for x in ["cc&rs", "bylaws", "operating rules", "articles of incorporation"]):
        return "governing"
    elif any(x in source_lower for x in ["budget", "audit", "financial", "assessment", "fees"]):
        return "financial"
    elif any(x in source_lower for x in ["advisory", "disclosure", "fair housing", "statewide", "transfer", "fraud", "representation", "market", "wildfire", "hazard", "flood", "wire"]):
        return "advisory"
    elif any(x in source_lower for x in ["inspection", "title", "report", "minutes", "minutes of"]):
        return "report"
    else:
        return "advisory"  # Default fallback


def find_sections_in_text(text: str, start_offset: int = 0) -> dict[int, str]:
    """Scan text for section numbers (e.g., "3.1.2") and return {char_pos: section_num}."""
    sections = {}
    for match in SECTION_PATTERN.finditer(text):
        sections[start_offset + match.start()] = match.group(1)
    return sections


def find_articles_in_text(text: str, start_offset: int = 0) -> dict[int, str]:
    """Scan text for ARTICLE headings and return {char_pos: article_num}."""
    articles = {}
    for match in ARTICLE_PATTERN.finditer(text):
        articles[start_offset + match.start()] = match.group(1)
    return articles


def get_most_recent_label(pos: int, labels: dict[int, str]) -> Optional[str]:
    """Find the most recent label <= pos."""
    candidates = [sec for sec_pos, sec in labels.items() if sec_pos <= pos]
    return max(candidates, default=None) if candidates else None


def split_into_sentences(paragraph: str) -> list[str]:
    """Split a paragraph into sentences, preserving whitespace context."""
    if not paragraph.strip():
        return []
    sentences = SENTENCE_PATTERN.split(paragraph)
    return [s.strip() for s in sentences if s.strip()]


def chunks_from_paragraphs(
    paragraphs: list[str],
    char_offset: int = 0,
) -> list[tuple[str, int, int]]:
    """Create chunks from paragraphs, respecting overlap and target size.

    Overlap is a bounded character budget (OVERLAP_CHARS) taken from the tail
    of the just-finalized chunk, not a whole-paragraph rewind. This guarantees
    every chunk advances by at least (TARGET_CHUNK_CHARS - OVERLAP_CHARS)
    characters, regardless of how large or small the source paragraphs are —
    a paragraph-count-based overlap could re-include an entire huge paragraph,
    causing near-duplicate chunks that barely advance (or don't advance at all
    when the whole document is a single paragraph, e.g. unstructured extracted
    text with no real \n\n breaks).

    Args:
        paragraphs: List of paragraph texts (separated by original \n\n).
        char_offset: Starting character position in the full document.

    Returns:
        List of (chunk_text, char_start, char_end) tuples.
    """
    chunks = []
    current_chunk_parts: list[str] = []
    current_char_start = char_offset
    char_pos = char_offset

    def current_len() -> int:
        if not current_chunk_parts:
            return 0
        return sum(len(s) for s in current_chunk_parts) + (len(current_chunk_parts) - 1)

    for para in paragraphs:
        if not para.strip():
            continue

        # Split paragraph into sentences for finer control.
        sentences = split_into_sentences(para)

        for sent in sentences:
            sent_len = len(sent)

            # If adding this sentence would exceed target, finalize the chunk.
            if current_chunk_parts and current_len() + 1 + sent_len > TARGET_CHUNK_CHARS:
                chunk_text = " ".join(current_chunk_parts)
                char_end = char_pos
                chunks.append((chunk_text, current_char_start, char_end))

                # Bounded tail overlap: keep only the last OVERLAP_CHARS worth
                # of sentences, not the whole preceding paragraph.
                overlap_parts: list[str] = []
                overlap_len = 0
                for s in reversed(current_chunk_parts):
                    added_len = len(s) + (1 if overlap_parts else 0)
                    if overlap_len + added_len > OVERLAP_CHARS:
                        break
                    overlap_parts.insert(0, s)
                    overlap_len += added_len

                current_chunk_parts = overlap_parts
                current_char_start = char_pos - overlap_len

            current_chunk_parts.append(sent)
            char_pos += sent_len + 1  # +1 for space

    # Finalize any remaining chunk.
    if current_chunk_parts:
        chunk_text = " ".join(current_chunk_parts)
        chunks.append((chunk_text, current_char_start, char_pos))

    return chunks


def chunk_document(
    source: str,
    full_text: str,
    page_offsets: list[dict],
    is_ccrs: bool = False,
) -> list[ChunkRecord]:
    """Chunk one document with improved section/article metadata.

    Section labeling strategy:
    1. Contained sections: scan each chunk's text for section numbers (primary citation).
    2. Inherited fallback: if chunk has no sections, use most recent prior section,
       BUT ONLY if it's within 1500 chars of chunk start. Otherwise leave empty.
    3. Articles: inherit as before (articles are large; inheritance is appropriate).

    Args:
        source: Document source filename.
        full_text: The full concatenated text.
        page_offsets: List of {page, start_char, end_char} from documents.json.
        is_ccrs: If True, skip section detection in first 10% (likely TOC).

    Returns:
        List of ChunkRecord objects.
    """
    # Classify document type
    doc_type = classify_doc_type(source)

    # Identify regions to ignore section patterns in.
    ignore_section_until = 0
    if is_ccrs:
        ignore_section_until = int(len(full_text) * TOC_REGION_FRACTION)

    # Scan for section and article markers in the full text.
    section_labels = find_sections_in_text(full_text)
    article_labels = find_articles_in_text(full_text)

    # Filter out section labels in TOC region.
    section_labels = {
        pos: sec for pos, sec in section_labels.items() if pos >= ignore_section_until
    }

    # Split on paragraphs.
    paragraphs = full_text.split("\n\n")

    # Create base chunks.
    base_chunks = chunks_from_paragraphs(
        paragraphs,
        char_offset=0,
    )

    # Build chunk records with improved metadata.
    records = []
    for chunk_idx, (chunk_text, char_start, char_end) in enumerate(base_chunks):
        chunk_id = f"{source}:chunk_{chunk_idx}"

        # PRIMARY: Scan for sections contained within this chunk's text.
        contained_sections = []
        for match in SECTION_PATTERN.finditer(chunk_text):
            contained_sections.append(match.group(1))

        # FALLBACK: If no contained sections, use most recent prior section
        # IF it's within 1500 chars of chunk start. Otherwise leave empty.
        section_inherited = None
        if not contained_sections:
            recent_section = get_most_recent_label(char_start, section_labels)
            if recent_section:
                recent_section_pos = [pos for pos, sec in section_labels.items()
                                     if pos <= char_start and sec == recent_section]
                if recent_section_pos:
                    distance = char_start - max(recent_section_pos)
                    if distance <= 1500:
                        section_inherited = recent_section

        # ARTICLE: Inherit as before (articles are large).
        article = get_most_recent_label(char_start, article_labels)

        # Map character range to page range using page_offsets.
        page_start, page_end = 1, 1
        for offset in page_offsets:
            page_num = offset["page"]
            if offset["start_char"] <= char_start < offset["end_char"]:
                page_start = page_num
            if offset["start_char"] < char_end <= offset["end_char"]:
                page_end = page_num

        records.append(
            ChunkRecord(
                chunk_id=chunk_id,
                source=source,
                text=chunk_text,
                doc_type=doc_type,
                sections=contained_sections,
                section_inherited=section_inherited,
                article=article,
                page_start=page_start,
                page_end=page_end,
                char_start=char_start,
                char_end=char_end,
            )
        )

    return records


# --- Main -------------------------------------------------------


def main() -> None:
    """Load documents, chunk them, and write chunks.json."""
    print("=== STAGE 3a: CHUNKING ===\n")

    # Load documents.
    docs = json.loads(DOCUMENTS_PATH.read_text())
    print(f"Loaded {len(docs)} documents\n")

    all_chunks: list[ChunkRecord | ImageCaptionChunk] = []
    chunk_stats = {}

    # Chunk each document.
    for doc in docs:
        source = doc["source"]
        is_ccrs = "CC&Rs" in source

        chunks = chunk_document(
            source=source,
            full_text=doc["full_text"],
            page_offsets=doc["page_offsets"],
            is_ccrs=is_ccrs,
        )
        all_chunks.extend(chunks)

        # Track stats.
        char_counts = [len(c["text"]) for c in chunks]
        chunk_stats[source] = {
            "count": len(chunks),
            "min_chars": min(char_counts),
            "median_chars": sorted(char_counts)[len(char_counts) // 2],
            "max_chars": max(char_counts),
            "with_contained_sections": sum(1 for c in chunks if c.get("sections")),
            "with_inherited_section": sum(1 for c in chunks if c.get("section_inherited")),
            "unlabeled": sum(1 for c in chunks if not c.get("sections") and not c.get("section_inherited")),
        }

    # Load captions if available.
    caption_chunks = []
    if CAPTIONS_PATH.exists():
        captions = json.loads(CAPTIONS_PATH.read_text())
        print(f"Loaded captions for {len(captions)} images\n")

        chunk_id_counter = len(all_chunks)
        for img_path, caption in captions.items():
            # Find which document owns this image.
            source = None
            page = 1
            for doc in docs:
                for img in doc.get("images", []):
                    if img["path"] == img_path:
                        source = doc["source"]
                        page = img["page"]
                        break
                if source:
                    break

            if source:
                caption_chunks.append(
                    ImageCaptionChunk(
                        chunk_id=f"caption_{chunk_id_counter}",
                        source=source,
                        text=caption,
                        page=page,
                        image_path=img_path,
                        type="image_caption",
                    )
                )
                chunk_id_counter += 1
    else:
        print("captions.json not found; skipping image captions\n")

    # Create Property Inspection collective chunk if images exist.
    inspection_doc = next((d for d in docs if "Property Inspection" in d["source"]), None)
    if inspection_doc:
        inspection_images = inspection_doc.get("images", [])
        if inspection_images:
            inspection_chunk = ImageCaptionChunk(
                chunk_id=f"property_inspection_summary",
                source=inspection_doc["source"],
                text="Property inspection report contains 47 photographs documenting roof, plumbing, electrical and structural conditions.",
                page=inspection_images[0]["page"],
                image_path="[multiple]",
                type="image_caption",
            )
            caption_chunks.append(inspection_chunk)
            print(f"Added collective chunk for Property Inspection photos\n")

    all_chunks.extend(caption_chunks)

    # Write output.
    CHUNKS_PATH.write_text(json.dumps(all_chunks, indent=2, ensure_ascii=False))
    print(f"Wrote {len(all_chunks)} chunks to {CHUNKS_PATH}\n")

    # Print summary.
    print("--- Chunking summary ---")
    print(f"Total chunks: {len(all_chunks)} ({len(caption_chunks)} image captions)")
    print()

    for source in sorted(chunk_stats.keys()):
        stats = chunk_stats[source]
        contained = stats.get("with_contained_sections", 0)
        inherited = stats.get("with_inherited_section", 0)
        unlabeled = stats.get("unlabeled", 0)
        print(
            f"{source:50s} {stats['count']:3d} chunks | "
            f"contained: {contained:3d} | inherited: {inherited:3d} | unlabeled: {unlabeled:3d}"
        )

    print()
    print("Sample chunks from CC&Rs:")
    ccrs_chunks = [c for c in all_chunks if isinstance(c, dict) and c.get("source") and "CC&Rs" in c["source"] and c.get("type") != "image_caption"]
    for i, chunk in enumerate(ccrs_chunks[:3], 1):
        print()
        print(f"  Chunk {i}: {chunk['chunk_id']}")
        sections = chunk.get('sections', [])
        section_inherited = chunk.get('section_inherited')
        article = chunk.get('article', 'N/A')

        section_str = "—"
        if sections:
            section_str = f"§§{sections[0]}–{sections[-1]}" if len(sections) > 1 else f"§{sections[0]}"
        elif section_inherited:
            section_str = f"(inherited §{section_inherited})"

        print(f"    Sections: {section_str} | Article: {article}")
        print(f"    Pages: {chunk['page_start']}-{chunk['page_end']} | Chars: {chunk['char_start']}-{chunk['char_end']}")
        print(f"    Text preview: {chunk['text'][:150]}...")


if __name__ == "__main__":
    main()
