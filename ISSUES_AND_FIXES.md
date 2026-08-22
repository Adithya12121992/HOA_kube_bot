# Issues & Fixes Log

Running log of real bugs/gaps found during development (via local trials against real documents), what was wrong, and how each was fixed. Kept up to date as new issues are found — newest entries on top within each section.

---

## Open Issues

### 1. Header/footer stripping not implemented
**Found:** 2026-08-22, during local chunking trial on `docs/30. CC&Rs (Required Civil Code Sec. 4525).pdf`
**Status:** Open — design agreed, not yet built

**Problem:** Extracted PDF text still contains per-page boilerplate (e.g. `"HomeWiseDocs"`, `"Document not for resale"`, `"Order: ZDT3W9PY5 Address: 825 S 22nd St Order Date: 04-11-2025"`) embedded directly in the text stream. This bleeds into chunks near page boundaries, contaminating embeddings and retrieval.

**Confirmed in the prior project too** (`~/Desktop/Personal_Projects/HOA_bot`): its `pipeline.py` documents a "Stage 2: Clean (boilerplate removal)" step, but `clean.py` was never implemented — `documents.json` from that project still has the same footer text repeated 88 times (once per page) for the same CC&Rs document.

**Planned fix (see PLAN.md Phase 2):**
- Frequency-based detection: lines in the first/last ~N lines of each page that repeat across ≥60-70% of pages get flagged as boilerplate
- Normalize digits before comparing (so `"Page 3 of 47"` and `"Page 4 of 47"` are recognized as the same repeating pattern)
- Where possible, use position-aware extraction (bounding boxes) to also check that the line sits in the actual top/bottom margin band, not just line-count from the edge — this project's local trial found that a fixed 2-line margin window missed some footer lines (`"Order: ..."`, `"Address: ..."`) that repeat further from the page edge than expected. Needs a wider or position-based window.

---

## Resolved Issues

### 1. Chunk overlap bug — 18x too many chunks, near-duplicate content
**Found:** 2026-08-22, during local chunking trial on `docs/30. CC&Rs (Required Civil Code Sec. 4525).pdf`
**Fixed:** 2026-08-22, commit `2f21dcf`
**File:** `src/chunk.py` — `chunks_from_paragraphs()`

**Problem:** Ran the existing `chunk_document()` against a real 88-page, 203,573-character document. Expected roughly 63 chunks (at 3,200 chars/chunk target); got **1,160 chunks**, with consecutive chunks nearly identical in content.

**Root cause:** Overlap was computed by re-including the *entire* previous paragraph (`paragraphs[para_idx - PARAGRAPH_OVERLAP : para_idx]`), with no bound on that paragraph's size. When source text has few/large paragraphs — e.g. one paragraph per PDF page, or (worst case) the whole document as a single paragraph with no real `\n\n` breaks — the overlap-rewind re-injects almost all previously-emitted content back into the next chunk. `char_start` barely advanced between chunks (`0 → 234 → 890 → 1306 → 1699 ...`) instead of jumping forward by roughly a chunk's worth of characters.

This same bug exists verbatim in the prior project (`~/Desktop/Personal_Projects/HOA_bot/chunk.py` — byte-for-byte identical file). It went unnoticed there because that project's `documents.json` had **zero** `\n\n` breaks in the entire document (a side effect of the never-implemented "clean" stage), which happened to never trigger the overlap-rewind path — at the cost of the paragraph-aware chunking logic never actually running as designed either.

**Secondary bug found in the same function:** `current_len` was computed by summing `current_chunk_parts` **twice** (`sum(len(p) for p in current_chunk_parts) + sum(len(s) for s in current_chunk_parts if current_chunk_parts)` — the second sum's `if current_chunk_parts` condition is a no-op truthy check on the whole list, not a per-item filter). This roughly doubled the counted chunk length, triggering splits earlier than intended.

**Fix:** Replaced paragraph-count-based overlap with a bounded character budget (`OVERLAP_CHARS = 300`, ~10% of `TARGET_CHUNK_CHARS`) taken from the tail of the just-finalized chunk's sentences. This guarantees every chunk advances by at least `TARGET_CHUNK_CHARS - OVERLAP_CHARS` characters regardless of paragraph size, and behaves identically whether the input has many small paragraphs or one giant blob. Also fixed the doubled-length calculation, and removed a dead parameter (`ignore_section_start`) that was accepted by `chunks_from_paragraphs()` but never referenced in its body (the real TOC-region exclusion happens elsewhere, in `chunk_document()`, via `section_labels` filtering).

**Verification (re-ran against the same real document):**

| Metric | Before | After |
|---|---|---|
| Chunks produced | 1,160 | 73 |
| Near-identical consecutive chunk pairs | many | 0 |
| Chunk size range | 1,139 – 5,484 chars | 1,970 – 3,199 chars |

Also regression-checked: small multi-paragraph input (well under target size) still collapses into a single chunk as expected.

---

## How entries get added here

When a local trial or real usage surfaces a bug or design gap:
1. Add an entry under **Open Issues** with: what was found, how it was found (what test/doc), root cause if known, planned fix
2. Once fixed: move it to **Resolved Issues**, add the fix description, file/commit reference, and before/after verification data
3. Keep entries newest-first within each section
