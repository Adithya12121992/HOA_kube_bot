# Issues & Fixes Log

Running log of real bugs/gaps found during development (via local trials against real documents), what was wrong, and how each was fixed. Kept up to date as new issues are found — newest entries on top within each section.

---

## Open Issues

_(none currently — see Won't Fix below for the one known remaining gap)_

---

## Won't Fix (Deliberate)

### 4. Letter-spaced text on embedded exhibit pages defeats word-level n-gram matching
**Found:** 2026-08-22, re-verifying `src/rag/clean.py` after the n-gram fix (Resolved #3 below)
**Decision:** 2026-08-22 — not worth fixing at the extraction/cleaning layer

**Problem:** After fixing whole-line matching to use word n-grams (which fully solved the watermark issue below), 3 of 69 chunks (~4%) still leak the `"Order: ZDT3W9PY5"` fragment. Root cause is different from the watermark case: pages 62-88 of this document (~22 pages) are an embedded engineering/survey exhibit section (site plan drawings — text includes `"TRACT 9644"`, `"ENGINEERS"`, `"SAN JOSE CALIFORNIA"`, `"YARD EASEMENTS"`), and on some of these pages the footer stamp renders with each letter as an individually spaced token: `"O r d e r: ZDT3W9PY5"`. Word-level n-gram matching splits on whitespace, so `"O"`, `"r"`, `"d"`, `"e"`, `"r:"` become separate single-character tokens — none of which match the confirmed `"order: zdt#w#py#"` fragment (which expects the letters run together, no internal spaces).

**Scope:** Confined to the exhibit/drawing appendix at the end of the document, not the main body. Only 3 chunks affected out of 69. The leaked text is low-value noise from a drawing overlay, not meaningful prose.

**Why not fixed:** it's just stray spacing artifacts in a tiny fraction of chunks, not corrupted/wrong content — an LLM generating an answer from a chunk containing `"O r d e r: ZDT3W9PY5"` amid real surrounding text isn't meaningfully thrown off by it. Not worth the added complexity of letter-spacing detection/collapsing at the extraction layer for this little value. Revisit only if it turns out to matter in practice (e.g. shows up as a real quality issue in Phase 8 benchmarking).

---

## Resolved Issues

### 3. Watermark noise defeated exact-match boilerplate detection
**Found:** 2026-08-22, verifying `src/rag/clean.py` against `docs/30. CC&Rs (Required Civil Code Sec. 4525).pdf`
**Fixed:** 2026-08-22, `src/rag/clean.py` — switched from whole-line to word n-gram frequency detection

**Problem:** One recurring footer line — `"Address: 825 S 22nd St"` — appears on 72/88 pages (82%, comfortably above the 60% detection threshold) but was **not** detected as boilerplate. Root cause: a semi-transparent background watermark (something like "Attorneys at Law" + a street address, likely a law firm's stamp) overlaps the footer region on most pages, and text extraction picks up garbled, near-unique fragments of it alongside the real footer line each time:
```
34x  'address: # s #nd st'                          (clean, no watermark noise)
 6x  'attorneysatlaw address: # s #nd st'
 3x  'a#torneysatlaw address: # s #nd st'
 1x  'attorneysatuw address: # s #nd st'
 1x  'arrorneysatlaw address: # s #nd st'
 ... (20+ more near-unique variants, 1 occurrence each)
```
Each garbled variant is its own distinct normalized string, so the vote for the real recurring line gets split across dozens of near-duplicates — none crosses the 60% threshold individually, even though the underlying "Address:" line is clearly boilerplate to a human reading it.

**Fix:** Changed `BoilerplateDetector.detect()` from counting whole-line frequency to counting **word n-gram** frequency (contiguous word sequences, 1-8 words long, extracted from every margin-band line). A stable fragment like `"address: # s #nd st"` now gets counted on its own, independent of whatever noise surrounds it on a given page — the watermark garbage varies, but the n-gram containing just the address text is identical every time it appears cleanly, and still present as a substring even when noise is attached. Added `_keep_maximal_fragments()` to de-duplicate the confirmed set (drop shorter fragments that are substrings of a longer confirmed one, e.g. `"address: #"` once `"address: # s #nd st"` is also confirmed) so the boilerplate set stays small and readable.

**Verification (same real document):**

| Metric | Before (whole-line) | After (n-gram) |
|---|---|---|
| Boilerplate signatures detected | 4 | 5 (now includes the address fragment) |
| `Address: 825 S 22nd St` occurrences remaining | 72 | 0 |
| All 4 originally-targeted boilerplate elements | 3/4 clean | 4/4 clean |

Re-running the full pipeline (extract → clean → chunk) surfaced a **new**, narrower issue — letter-spaced text on an embedded exhibit section — documented separately as Open Issue #4 above, rather than folded into this fix.

### 2. Extraction produced one text blob per page — no real paragraph structure, boilerplate leaked into every chunk
**Found:** 2026-08-22, during local chunking trial (naive `page.extract_text()` join)
**Fixed:** 2026-08-22, `src/rag/extract.py` + `src/rag/clean.py` (new modules)

**Problem:** Neither this project nor the prior one (`~/Desktop/Personal_Projects/HOA_bot`) ever implemented real PDF extraction — the prior project's `pipeline.py` stubs out "Stage 1: Ingest" and "Stage 2: Clean" entirely (`"Status: ⚠️ Requires ingest.py module (not included in this repo)"`). Its `documents.json` turned out to be a naive per-page text join with **zero** `\n\n` breaks in the entire 392K-character document, and footer boilerplate (`"HomeWiseDocs"`, `"Document not for resale"`, `"Order: ZDT3W9PY5..."`) repeated verbatim 88 times, once per page, contaminating every chunk near a page boundary.

**Fix — two new modules:**
- **`src/rag/extract.py`**: extracts words with bounding boxes per page (via `pdfplumber`), groups them into lines, then groups lines into real paragraphs using vertical-gap detection (a gap much larger than the page's typical line spacing = paragraph break, not just wrapped text). Produces genuine `\n\n`-separated paragraph structure instead of one blob per page.
- **`src/rag/clean.py`**: `BoilerplateDetector` — detects repeated header/footer lines using two combined signals: (1) position — is the line within `MARGIN_FRACTION` (15%) of the top/bottom of the page, using actual page-height fractions rather than a fixed line count; and (2) frequency — does a digit-normalized version of the line repeat across ≥60% of pages. Stripping uses **substring containment**, not exact-line equality (see note below on why), with a minimum signature length (6 chars) to avoid false-positive stripping of short/generic text.

**A fixed-line-count margin window isn't enough:** an earlier trial using a naive "check the first/last 2 lines of each page" window missed footer lines that sat further from the page edge (`"Order: ..."`, `"Address: ..."`) — switching to a page-height-fraction check catches these regardless of how many lines are stacked in the margin.

**Exact-line matching isn't enough either — found and fixed mid-implementation:** first pass stripped by exact normalized-line equality. Verifying against the real document showed `"Order: ZDT3W9PY5"` still leaking through in 18 places, because on some pages pdfplumber's word-clustering merges the footer with an adjacent heading due to positional jitter (`"Order: ZDT3W9PY5 YARD EASEMENTS ."`, or with no space at all, `"Order: ZDT3W9PY5YARD"`, or the ID splitting onto its own line as bare `"Order:"`). Switched `strip()` to substring containment — if a confirmed boilerplate signature appears *anywhere* in a line, the whole line is dropped — which catches all of these merged/split variants. Result: `Order:` leakage went from 18 occurrences to 0.

**Verification (same real 88-page CC&Rs document):**

| Metric | Before (naive join) | After |
|---|---|---|
| Paragraphs (real `\n\n` breaks) | 1 (whole doc) | 644 |
| `HomeWiseDocs` occurrences remaining | 88 | 0 |
| `Document not for resale` occurrences remaining | 81 | 0 |
| `Order: ZDT3W9PY5` occurrences remaining | 88 | 0 |
| Chunks produced (fed into the fixed `chunk_document()`) | 1,160 (see Resolved #1) | 69 |
| Chunks still containing boilerplate | many | 0 |

The watermark-contaminated `Address:` line mentioned as an open gap at the time was resolved shortly after — see Resolved Issue #3 above.

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
3. If a deliberate call is made not to fix something (cost/benefit not worth it): move it to **Won't Fix (Deliberate)** with the reasoning, instead of leaving it open indefinitely
4. Keep entries newest-first within each section
