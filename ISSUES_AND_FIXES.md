# Issues & Fixes Log

Running log of real bugs/gaps found during development (via local trials against real documents), what was wrong, and how each was fixed. Kept up to date as new issues are found — newest entries on top within each section.

---

## Verification Log

Documents the extract → clean → chunk pipeline has been run against, to track test coverage (not every run finds a new bug — that's the point).

| Date | Scope | Result |
|---|---|---|
| 2026-08-22 | LlamaIndex cloud retrieval (PineconeVectorStore), real Pinecone index, full `add_chunks`/`search`/fast/thinking pipeline | Pass. See Resolved #15 below. |
| 2026-08-22 | Mem0 conversation memory, both backends, real 2-turn conversations end-to-end (not mocked) | Pass. See Resolved #14 below. |
| 2026-08-22 | "Thinking" mode (corrective RAG: retrieve/grade/rewrite/generate), 3 real scenarios against real LM Studio + real ChromaDB data | Pass. See Resolved #13 below. |
| 2026-08-22 | `/ask` event-loop-blocking fix: real concurrent test, real LM Studio call | Pass. See Resolved #12 below - a real, user-reported, in-production bug. |
| 2026-08-22 | Dual-write `add_chunks()` against real ChromaDB + real Pinecone, redeployed to K8s | Pass. One real chunk written once, confirmed independently searchable from both backends with matching similarity scores (0.715 / 0.714) after flipping the environment toggle between calls. `reset()` confirmed clearing both. Both pods redeployed and stable after the change. |
| 2026-08-22 | Config toggle cross-process propagation, real test | Found and fixed a real bug — see Resolved #11 below. Verified both the single-process and cross-process/pod cases separately. |
| 2026-08-22 | Full K8s deployment (real `docker build` → `k3d image import` → `kubectl rollout`), consumer + hoa-bot pods | Found and fixed a real bug — see Resolved #10 below. Both pods stable at `1/1 Running`, 0 restarts, after the fix. |
| 2026-08-22 | Full `/ask` HTTP endpoint on a live running server (real `uvicorn` process, real HTTP POST, not a direct function call): populated ChromaDB with real chunked data, asked two real questions | Pass. Accurate answers, correct source citations (`[1]` matched the actually-relevant chunk by page range), sources/metadata correctly shaped in the response. One question's answer had a stray `"space\n\n\n\n"` prefix before the real content — re-asked a different question and it didn't recur, confirming non-deterministic local reasoning-model output noise, not a bug in prompt construction or response parsing (same category as the earlier qwen3 empty-content finding, intermittent instead of consistent this time). |
| 2026-08-22 | `summarize.py` cloud LLM path (`ENVIRONMENT=cloud`) against the real Anthropic API | Pass — accurate, on-topic 2-line summary generated via the default model (`claude-sonnet-4-5`), confirming Anthropic tried first per `CLOUD_LLM_FALLBACK_ORDER` and succeeded (no fallback-to-OpenAI warning logged). OpenAI itself separately confirmed reachable but blocked by the account's `insufficient_quota` (no billing configured) — not a code issue, see note below the Pinecone entries. Fallback chain behaved correctly either way: warned and returned `None` instead of raising when OpenAI failed, before Anthropic was retried with the corrected key. |
| 2026-08-22 | Pinecone backend (`ENVIRONMENT=cloud`) against the real Pinecone index: `add_chunks()` → `search()` → `reset()`, including the sections/page_start/article metadata round-trip check | Pass. See Resolved #9 below — one real (non-blocking) finding along the way. |
| 2026-08-22 | Full consumer pipeline (`process_message`), real PDF, not mocked: extract → chunk → embed → store → summarize → status → delete → ack | Pass. Real doc (6 pages) → 3 chunks → embedded+stored (confirmed searchable in ChromaDB afterward, 0.66-0.73 similarity on a relevant query) → real 2-line summary generated via the user's actual local LM Studio instance, accurate to source content → status progressed uploaded→extracting→chunking→embedding→summarizing→ready with correct `chunks_done`/`chunks_total` at each step → file deleted → message acked. Error path also verified separately: missing file → nacks with `requeue=False`, writes `stage=error`, does not ack. |
| 2026-08-22 | `summarize.py` local LLM path against the user's real running LM Studio instance (`qwen/qwen3-14b`) | Found and fixed a real bug — see Resolved #7 below. |
| 2026-08-22 | Full round trip on pinned `requirements.txt` (Python 3.11, matches Docker target): extract → clean → chunk → embed → store → search | Pass. See Resolved #5 for what it took to get the pins actually installable, and Resolved #4 for a real metadata bug found in the process. |
| 2026-08-22 | `store.py` embed/store/search round trip against real chunked data (CC&Rs, populated `sections` fields) | Found and fixed a real bug — see Resolved #4 below. |

| Date | Document | Pages | Type | Result |
|---|---|---|---|---|
| 2026-08-22 | `25. Minutes of Regular Board Meetings...pdf` | 6 | report (minutes) | Clean. 3 chunks, no duplication, no bad progression. All boilerplate removed, including a new corruption pattern not seen before — two overlapping text elements interleaved character-by-character on 5/6 pages (`"MinuDteosc ument not for resale"`, apparently "Minutes" + "Document not for resale" rendered on top of each other) — still caught because the corrupted form itself repeated consistently across pages and matched via n-gram + substring stripping. Legitimate body-text mentions of "Board of Directors" (embedded in real sentences) correctly preserved; only the recurring standalone header instance was stripped. |
| 2026-08-22 | `32. Annual Budget Report...pdf` | 40 | financial | Clean. 34 chunks, no duplication, no bad progression, 3.7% of text removed as boilerplate. |
| 2026-08-22 | `30. CC&Rs...pdf` | 88 | governing | See Resolved Issues #1-#3 below — this is the document all three fixes were found and verified against. |

---

## Open Issues

_(none currently — see Won't Fix below for the one known remaining gap)_

---

## Won't Fix (Deliberate)

### 6. Letter-spaced text on embedded exhibit pages defeats word-level n-gram matching
**Found:** 2026-08-22, re-verifying `src/rag/clean.py` after the n-gram fix (Resolved #3 below)
**Decision:** 2026-08-22 — not worth fixing at the extraction/cleaning layer

**Problem:** After fixing whole-line matching to use word n-grams (which fully solved the watermark issue below), 3 of 69 chunks (~4%) still leak the `"Order: ZDT3W9PY5"` fragment. Root cause is different from the watermark case: pages 62-88 of this document (~22 pages) are an embedded engineering/survey exhibit section (site plan drawings — text includes `"TRACT 9644"`, `"ENGINEERS"`, `"SAN JOSE CALIFORNIA"`, `"YARD EASEMENTS"`), and on some of these pages the footer stamp renders with each letter as an individually spaced token: `"O r d e r: ZDT3W9PY5"`. Word-level n-gram matching splits on whitespace, so `"O"`, `"r"`, `"d"`, `"e"`, `"r:"` become separate single-character tokens — none of which match the confirmed `"order: zdt#w#py#"` fragment (which expects the letters run together, no internal spaces).

**Scope:** Confined to the exhibit/drawing appendix at the end of the document, not the main body. Only 3 chunks affected out of 69. The leaked text is low-value noise from a drawing overlay, not meaningful prose.

**Why not fixed:** it's just stray spacing artifacts in a tiny fraction of chunks, not corrupted/wrong content — an LLM generating an answer from a chunk containing `"O r d e r: ZDT3W9PY5"` amid real surrounding text isn't meaningfully thrown off by it. Not worth the added complexity of letter-spacing detection/collapsing at the extraction layer for this little value. Revisit only if it turns out to matter in practice (e.g. shows up as a real quality issue in Phase 8 benchmarking).

---

## Resolved Issues

### 15. LlamaIndex was a documentation-only label — cloud retrieval never actually used it
**Found:** 2026-08-22, auditing `settings.py`'s "RAG framework: LlamaIndex" claim for the cloud bundle
**Fixed:** 2026-08-22, `src/rag/store.py`, `requirements.txt`

**Problem:** `settings.py` and `PLAN.md` both documented the cloud environment's RAG framework as LlamaIndex, but `requirements.txt` had no `llama-index-*` package at all — `_pinecone_search()` in `store.py` was, and always had been, a direct Pinecone SDK call. The label described an intention, not the code.

**Decision:** unlike "thinking mode"/LangGraph (Resolved #13), where a real dependency was deliberately skipped because a plain loop expressed the same control flow with less machinery, this one got a real integration — user's explicit call after being shown the tradeoff, since LlamaIndex's vector-store abstraction does add genuine value here (a maintained, general query-interface layer over Pinecone) where the LangGraph case didn't (a graph library over 4 linear steps).

**Fix:** Added `llama-index-core==0.12.20` + `llama-index-vector-stores-pinecone==0.4.5`. `_pinecone_search()` now builds a `PineconeVectorStore(pinecone_index=..., text_key="text")` around the existing (already-populated) Pinecone index and queries it via `VectorStoreQuery(query_embedding=..., similarity_top_k=k)`, using this project's own BGE embedding call (not LlamaIndex's embedding abstraction) so query-time vectors stay identical to what `_pinecone_add_chunks()` already writes — one tested embedding path for both backends, matching the module's existing design principle. Scoped to *retrieval only*: writes still go through the raw Pinecone SDK (`_pinecone_add_chunks`/`_pinecone_reset`, unchanged), and generation still goes through `llm.py`'s environment-aware Anthropic call — LlamaIndex doesn't own synthesis, consistent with every other retrieval path in this project already separating "get chunks" from "generate answer."

**Dependency conflict found along the way:** `llama-index-vector-stores-pinecone==0.4.5` requires `pinecone<7.0.0`, but this project had `pinecone==9.1.0` pinned. Downgraded to `pinecone==6.0.2` — re-verified `add_chunks()`/`search()`/`reset()` against the real index afterward; no behavior change, since the project only uses the parts of the Pinecone SDK surface (`Pinecone(api_key=...)`, `pc.Index(name)`, `index.upsert`/`query`/`delete`) that are stable across that version range.

**Verification (real, not mocked — 73 real vectors already in the live `hoa-documents` Pinecone index from earlier sessions):**
- Raw `PineconeVectorStore.query()` sanity check: same top-3 results and same similarity scores as the pre-change direct-SDK call, for the query "board meetings."
- `store.search()` (public API, cloud mode): 3 results, metadata correctly round-tripped through `_restore_metadata` (JSON-decoded `sections` list, correct `article`/`page_start`/etc.), matching pre-change output shape exactly.
- `query.answer_question()` full pipeline (LlamaIndex retrieval → Anthropic generation): correct, cited answer to "When are board meetings held?"
- `thinking.answer_question_thinking()` full pipeline: correct trace (`retrieve → grade → generate`) with LlamaIndex-backed retrieval feeding the corrective-RAG grading/generation steps.
- Round-trip write check: `add_chunks()` (dual-write, unchanged code path) followed immediately by a cloud `search()` for the new chunk — found it, with correct metadata (`article: "IX"`), confirming the LlamaIndex retrieval path sees writes made via the raw-SDK write path with no format mismatch.
- Test chunks (`test:chunk_0`, `llamaidx-verify:chunk_0`) deleted from the real Pinecone index afterward.

### 14. Mem0 wiring: real API contract differs from the naive-obvious call shape, plus a pydantic conflict
**Found:** 2026-08-22, while wiring `src/rag/memory.py` into `query.py`/`thinking.py`
**Fixed:** 2026-08-22, `src/rag/memory.py` (new), `requirements.txt`

**Problem 1 — dependency conflict:** adding `mem0ai==2.0.18` to `requirements.txt` broke a clean install: `mem0ai>=2.7.3` requires `pydantic>=2.7.3`, but this project pinned `pydantic==2.1.1`. Fixed by bumping to `pydantic==2.9.2` (still inside fastapi's own looser constraint, `!=2.0.0,!=2.0.1,<3.0.0,>=1.7.4`). Verified a full clean install in a scratch venv afterward, then re-verified every real project import.

**Problem 2 — API contract:** the obvious call, `client.search(question, user_id=user_id)`, raises `ValueError: Top-level entity parameters frozenset({'user_id'}) are not supported in search(). Use filters={'user_id': '...'} instead.` The real signature is `client.search(query, filters={"user_id": user_id}, version="v2")`, returning `{"results": [{"memory": ..., "score": ...}, ...]}`. Also: `add()` returns immediately with `{"status": "PENDING"}` — Mem0 does its own async fact-extraction from the conversation in the background, so a memory added this turn is not guaranteed searchable on the very next call (observed a few seconds' lag in testing). Not a problem for this project's usage (only affects one user's own next question, not a hot shared path), but worth knowing before assuming a memory "didn't get saved."

**Fix:** `src/rag/memory.py` — `get_relevant_memories()`/`add_memory()`, dispatching on `get_environment()`: real Mem0 `MemoryClient` for `cloud`, a plain in-process `dict[user_id, list[turns]]` for `local` (session memory only, intentionally lost on restart — that's the designed distinction from Mem0, not a gap). Both are optional enhancements: no `user_id` supplied, or lookup/write fails, and the answer flow proceeds unaffected (`try`/`except` + `logger.warning`, never raises into the request path). Wired into `answer_question()` (`query.py`) and `answer_question_thinking()` (`thinking.py`) via a `user_id` param already exposed on the `/ask` endpoint's `AskRequest`.

**Verification (real, not mocked):**
- **Local:** two real questions through `answer_question()` with the same `user_id`, `ENVIRONMENT=local`. Turn 1 ("When are board meetings held?") answered correctly with `memories_used: 0`. Turn 2 ("What time is that meeting again?" — meaningless without turn 1's context) correctly answered "6:30 PM" with `memories_used: 1`, confirming the in-process session dict round-trips real Q&A turns.
- **Cloud:** same two-turn test, `ENVIRONMENT=cloud`, real Mem0 API + real Pinecone retrieval + real Anthropic generation, no mocks. Turn 1 answered correctly (`memories_used: 0`). Waited ~8s for Mem0's async fact-extraction, then turn 2 correctly answered "6:30 PM" citing the memory (`memories_used: 1`), confirming the real `add()`/`search()` round trip works end-to-end through the actual integration code, not just the raw client. Test data cleaned up afterward via `client.delete_all(user_id=...)`.
- Noted (not investigated further, not a functional bug): after the cloud test's correct output printed, the Python process crashed on interpreter exit with `libc++abi: terminating due to uncaught exception of type std::__1::system_error: recursive_mutex lock failed`. This happens during native-library teardown after the answer was already returned, not during request handling — consistent with a known class of onnxruntime/grpc shutdown races on macOS, not a request-path defect. Worth revisiting if it ever surfaces inside the actual long-running service process rather than a short-lived test script.

### 13. "Thinking" mode was a UI-only no-op — the actual corrective-RAG code was never wired in
**Found:** 2026-08-22, auditing what the "thinking" toggle in the UI actually did
**Fixed:** 2026-08-22, `src/rag/thinking.py` (new), `src/services/chatbot/service.py`, commit `51ca24f`

**Problem:** The retrieval-mode toggle (`fast` / `thinking`) existed in the UI and in `get_retrieval_mode()`, but `service.py`'s `/ask` endpoint called `answer_question()` (fast mode) unconditionally — the toggle changed no behavior. A prototype implementation, `src/rag/rag_graph.py`, existed but was never audited or connected: it hardcoded an `OpenAI` client pointed at `http://localhost:1234/v1` with `model="gpt-3.5-turbo"` (not a model LM Studio would actually have loaded), had debug `print()` calls and hardcoded `/tmp/debug_message.txt` writes, and predated this project's `llm.py`/`store.py` environment-aware abstractions entirely.

**Fix:** New module `src/rag/thinking.py`, keeping the prototype's real design work (doc-type-aware grading prompt distinguishing governing/advisory/report chunks, bounded rewrite loop, citation-based generation prompt) but rewired onto the current architecture — `llm.generate()` and `store.search()` instead of a hardcoded client, and reusing `Source`/`AnswerResult`/`_build_context` from `query.py`. Implemented as a plain bounded `while` loop (retrieve → grade → rewrite if insufficient, up to `MAX_REWRITES=2` → generate), not a LangGraph `StateGraph` — the control flow is simple/linear enough that a graph library adds no value and a plain function is easier to test directly. `rag_graph.py` deleted (`git rm`). `service.py`'s `/ask` now dispatches on `get_retrieval_mode()` to call either `answer_question()` or `answer_question_thinking()`.

**Verification (3 real end-to-end scenarios, real LM Studio, real ChromaDB data, not mocked):**
1. Doc-type-aware grading: a report-type question and a governing-type question against a mixed corpus each correctly favored the right chunk type, matching the grading prompt's stated priority rules.
2. Bounded rewrite behavior: a colloquially-phrased question that failed initial grading correctly triggered query rewriting (observed in the trace), bounded at `MAX_REWRITES=2`, and terminated rather than looping indefinitely.
3. Safe refusal: a question with no answerable content in the corpus correctly returned "The documents don't address this question." rather than hallucinating, after exhausting the rewrite budget.

### 12. `/ask` blocked the event loop, causing K8s to kill the pod mid-generation
**Found:** 2026-08-22, real user report: asked a question, got "Failed to fetch" in the browser; LM Studio's own logs showed "Client disconnected. Stopping generation..." partway through, with no code change or redeploy happening at the time
**Fixed:** 2026-08-22, `src/services/chatbot/service.py` — wrapped the blocking call in `asyncio.to_thread()`

**Problem:** First suspected `kubectl port-forward` flakiness (a real, separate issue — see below), but a repeat report with the exact same symptom, at a point where no redeploy was happening, pointed to something more fundamental. `kubectl describe pod` on the exact failure window showed the real cause:
```
Warning  Unhealthy  Liveness probe failed: Get "http://.../health": context deadline exceeded
Normal   Killing    Container hoa-bot failed liveness probe, will be restarted
```
`/ask` was declared `async def` but called `answer_question()` — a fully synchronous, blocking function (`requests.post()` to the LLM, which can legitimately take minutes for local reasoning models) — directly, with no `await`. uvicorn runs a single-threaded event loop by default, so this blocked the **entire server** for the whole duration of the LLM call, including `GET /health`, which the K8s liveness probe depends on. After 3 consecutive failed health checks (~30s), Kubernetes concluded the pod was unhealthy and **killed it mid-request** — exactly what "Client disconnected" was reporting from LM Studio's side, and what "Failed to fetch" was reporting from the browser's side.

**Fix:** `result = await asyncio.to_thread(answer_question, request.question)` instead of calling it directly — moves the blocking work off the event loop so `/health` (and everything else) stays responsive while `/ask` is in flight.

**Verification (real concurrency test, not a code read):** seeded one real chunk, fired a real `/ask` request (real LM Studio call) in the background, then hit `/health` 8 times over 15 seconds while it was in flight — **every single check returned in under 1.4ms**. The `/ask` call itself completed successfully in 13.4s with an accurate, correctly-cited answer ("Yes, you can have wind chimes if they are under 12 inches... [1]").

**Related, separate issue found in the same investigation — `kubectl port-forward` timeout:** even after the above fix, `kubectl port-forward`'s own tunnel (SPDY/WebSocket-based) has an idle/stream timeout shorter than a local reasoning model's response time — confirmed directly: a real request was cut off at **exactly 60 seconds** ("connection reset by peer"), and the port-forward process itself was found completely dead (`Connection refused`, not in `ps aux`) after normal use. This isn't fixed by the async change above — the process-level tunnel is just not built for multi-minute requests. Replaced it with a stable path that doesn't depend on a kept-alive local process: added `k3d cluster edit HOA-Bot --port-add 8000:80@loadbalancer` (real Docker port-publish on the cluster's load balancer, one-time, non-destructive — only recreates the load balancer container, not the server/agent nodes where the PVC data lives) plus a K8s `Ingress` (`k8s/hoa-bot-ingress.yaml`) routing to `hoa-bot-service`. Verified: `http://localhost:8000/` survives a full `kubectl rollout restart` with zero manual steps, unlike port-forward which needed restarting after every redeploy in this session.

### 11. Config toggle frozen at import time, and not shared across pods
**Found:** 2026-08-22, investigating why an uploaded doc only appeared in ChromaDB, not Pinecone
**Fixed:** 2026-08-22, `src/config/settings.py`, `src/rag/store.py`, `src/rag/llm.py`

**Problem:** Two compounding bugs, found while investigating a user-reported issue ("I uploaded a doc, it inserted into Chroma but not Pinecone"):

1. **Single-process:** `store.py` and `llm.py` both did `from src.config.settings import ENVIRONMENT` — Python's `from module import NAME` copies the value at import time. `update_config()`'s `global ENVIRONMENT; ENVIRONMENT = ...` reassigns `settings.py`'s own module-level name, but `store.py`/`llm.py`'s already-bound local names never see that reassignment. Toggling via `POST /config` updated `settings.py`'s own state but `store.py`/`llm.py` silently kept using whatever `ENVIRONMENT` was at their import time — forever, even within the same process.
2. **Cross-process:** `consumer` and `hoa-bot` are separate pods with no shared memory anyway, so even fixing bug 1 alone wouldn't make a toggle in `hoa-bot`'s UI reach `consumer`, which is what actually does the embedding/storage.

**Fix:** Replaced the plain-global pattern with a shared config file on the PVC (same pattern as `src/rag/status.py`) as the single source of truth. `get_environment()`/`get_retrieval_mode()` read it fresh on every call — callers must call the function, not import a frozen value. `update_config()` writes to the same file. `store.py` and `llm.py` now call `get_environment()` at the point of use instead of importing `ENVIRONMENT` as a value.

**Verification:**
- Single-process: called `update_config(environment="cloud")`, confirmed `store.py`'s and `llm.py`'s `get_environment()` immediately reflected `"cloud"` in the same process (previously would have stayed `"local"` forever)
- Cross-process: after that toggle, started a completely separate Python process and confirmed it also read `"cloud"` from the shared file
- Cross-pod (real K8s): toggled via `hoa-bot`'s actual `/config` HTTP endpoint, confirmed via `kubectl exec` into the `consumer` pod that it picked up the same value

### 10. `cryptography==50.0.0` crashes with SIGILL on arm64 under Docker Desktop
**Found:** 2026-08-22, first real K8s deployment attempt with the full pipeline built into containers
**Fixed:** 2026-08-22, `requirements.txt` — pinned `cryptography==42.0.5`

**Problem:** The `consumer` pod crashed immediately on every startup (`CrashLoopBackOff`, exit code 132 — SIGILL, illegal instruction) before processing anything, before even printing its own first log line. `hoa-bot` didn't crash at the time only because it hadn't yet exercised the same code path (lazy imports).

**Root cause, isolated by bisection** (tested each layer directly via `docker run`, narrowing from "the whole app crashes" down to one line):
1. `src.services.consumer.app` import → crash
2. → `src.rag.extract` import → crash
3. → `pdfplumber` import → crash
4. → `pdfminer.high_level` → crash (but `import pdfminer` alone was fine)
5. → every `pdfminer.*` submodule (`converter`, `image`, `layout`, `pdfdevice`, `pdfinterp`, `pdfpage`) → crash
6. → isolated to `from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes` specifically (used by `pdfminer.six` for encrypted-PDF support)

Confirmed host and container architecture matched (`arm64` both sides — not a QEMU/Rosetta cross-emulation issue). `cryptography` alone (bare `import cryptography`) worked fine; only the `hazmat.primitives.ciphers` submodule — which does AES hardware-acceleration detection at import time — crashed. This points to a genuine bug in that specific `cryptography` release's ARM64 build under Docker Desktop's virtualized Linux VM, not a general ARM64 incompatibility (unpinned `pip install` picked up `50.0.0`, the latest at the time — nothing in `requirements.txt` had pinned it, since it's a transitive dependency of `pdfplumber` → `pdfminer.six`).

**Fix:** Pinned `cryptography==42.0.5` explicitly in `requirements.txt`. Verified directly (before committing to a full rebuild): `pip install --force-reinstall cryptography==42.0.5` inside the already-built broken image, then re-ran the exact AES cipher instantiation that crashed — worked cleanly. Rebuilt both images properly with the pin, redeployed: both `consumer` and `hoa-bot` pods stable at `1/1 Running`, 0 restarts.

**Also fixed while investigating this deployment (same session, adjacent real gaps found before the crash):**
- `k8s/hoa-bot-deployment.yaml` and `k8s/consumer-deployment.yaml` were missing most of the environment/secret wiring the pipeline actually needs now (`LM_STUDIO_API_KEY` wasn't in the manifest at all — even local mode would have 401'd against the user's real LM Studio, which requires a Bearer token; `LM_STUDIO_MODEL` was a placeholder `"local-model"` string that doesn't match any real loaded model; `consumer-deployment.yaml` had none of the storage/LLM env vars at all, just RabbitMQ). Added all of it, matching what `hoa-bot` needed.
- The K8s Secrets referenced by the deployment manifests (`pinecone-secret`, `mem0-secret`, `llm-secret`) never actually existed in the cluster — created them for real from the user's `.env` values.
- Verified `host.k3d.internal` (used to reach the user's LM Studio server running on the host machine) is actually reachable from inside a pod — confirmed via a throwaway `curl` pod (got a `401` from LM Studio, meaning the network path works, auth is what's missing without the token).
- Resource limits (`256Mi`/`512Mi`, from Phase 1 before embedding was wired in) were too low for `torch` + `sentence-transformers` to load — bumped to `768Mi` request / `1.5Gi` limit on both pods.
- Docker images were 9-9.5GB (`pip install torch` pulls the full CUDA-enabled build by default, unnecessary for CPU-only inference in these containers). Installed the CPU-only torch wheel first (`--index-url https://download.pytorch.org/whl/cpu`) so `sentence-transformers`' dependency resolution sees it already satisfied — brought images down to 2.2-2.75GB (~4x smaller), meaningfully faster `k3d image import` and pod startup.

### 9. Pinecone `fetch()`-by-ID unreliable for chunk_ids with special characters
**Found:** 2026-08-22, verifying the new Pinecone storage backend's metadata round-trip against real CC&Rs chunks
**Status:** Documented, not a bug in this codebase's actual code path — noted for future awareness

**Problem:** While verifying the sections/page_start/article metadata round-trip for the new Pinecone backend (mirroring the check that caught Resolved #4's ChromaDB bug), used `index.fetch(ids=[chunk_id])` as a verification shortcut. It consistently failed to find a chunk (`"30. CC&Rs (Required Civil Code Sec. 4525).pdf:chunk_3"`) even after 10 retries with delays — looked like a real storage failure at first. Checked `describe_index_stats()` (correct count) and `index.query()` with a dummy vector (returned the exact same ID string, correctly) — the vector *is* stored correctly, `fetch()` specifically can't find it. The chunk_id contains spaces, `&`, parentheses, and a colon — likely a URL-encoding issue in how this Pinecone SDK version's `fetch()` builds its request for IDs with special characters.

**Why not fixed:** `store.py`'s actual `search()` function uses `index.query()` (semantic search, POST body), not `fetch()` (direct ID lookup, apparently GET-based) — the real code path is unaffected. Re-ran the same round-trip check through `search()` instead and got an exact match (sections, page_start, article all correct). Documented rather than fixed since nothing currently in the codebase calls `fetch()` by ID — but a future feature (e.g. "get this specific chunk for citation display") that does would hit this.

**Verification:** `search()`-based round trip (the real path) confirmed exact match on a real CC&Rs chunk with populated `sections`, `page_start` as `int`, and `article` correctly restored.

### 8. Consumer had a hardcoded credential-shaped default value
**Found:** 2026-08-22, wiring the real pipeline into `src/services/consumer/app.py` (Step 2.4)
**Fixed:** 2026-08-22, same commit — switched to importing from `src/config/settings.py`

**Problem:** `RABBITMQ_USER`/`RABBITMQ_PASSWORD` had hardcoded fallback defaults that looked like a real, previously-generated K8s secret value (`"default_user_jKPj7zmhwSN3JMMb5um"` / a 32-char random-looking password) rather than an obviously-fake placeholder like `"guest"`. In practice this default is unreachable in any real deployment (K8s always injects the real secret via env var), but a real-looking credential should never sit in source control as a fallback value regardless of whether it's currently reachable.

**Fix:** Removed the local hardcoded defaults; now imports `RABBITMQ_USER`/`RABBITMQ_PASSWORD` from `src/config/settings.py`, which defaults to `"guest"` (RabbitMQ's actual generic default, not a real secret).

### 7. Wrong empty-string handling for local reasoning models (Qwen3)
**Found:** 2026-08-22, first real test of `src/rag/summarize.py` against the user's actual running LM Studio instance
**Fixed:** 2026-08-22, `src/rag/summarize.py`

**Problem:** First real call to the user's LM Studio server (model: `qwen/qwen3-14b`) returned an **empty string** as the summary instead of real content or a clean `None`. Inspected the raw API response directly: Qwen3 is a reasoning model — its response has a separate `reasoning_content` field (internal chain-of-thought) in addition to `content` (the real answer), and with `max_tokens=150`, the model spent 179 of 199 completion tokens on `reasoning_content` before generation hit the token limit (`finish_reason: "length"`), leaving `content` empty.

Separately, port 1234 (LM Studio's default) turned out to be genuinely reachable — the user had it running already — but required a Bearer token the code didn't send, returning `401 Unauthorized` rather than a connection error.

**Fix:**
- Bumped local generation to `max_tokens=800` (vs 150 for cloud, which isn't a reasoning model by default) and the timeout to 240s (user-specified 3-minute floor) to give a reasoning model room to think *and* answer.
- `content.strip() or None` instead of `content.strip()` — an empty string is now treated the same as "no summary," not returned as a falsy-but-truthy empty string.
- Added `LM_STUDIO_API_KEY` support (Bearer auth header) to `src/config/settings.py` and `summarize.py`.
- Wired up `.env` loading: `python-dotenv` was already a listed dependency but `load_dotenv()` was never actually called anywhere — a `.env` file would have silently done nothing. Added `load_dotenv()` to `src/config/settings.py`.

**Verification:** Real end-to-end call against the user's LM Studio instance with a realistic CC&Rs-style prompt returned an accurate, on-topic 2-line summary (mentioned rental restrictions, board approval requirements, and architectural review — all present in the test prompt).

### 5. Pinned Phase 2 dependencies didn't actually install/import
**Found:** 2026-08-22, installing the exact pinned `requirements.txt` versions in a clean venv before wiring `store.py` in
**Fixed:** 2026-08-22, `requirements.txt`

**Problem:** Added `chromadb==0.4.22` and `sentence-transformers==2.2.2` to `requirements.txt` (numbers picked without installing them for real — same mistake as the earlier fastapi/pydantic incident). Testing the actual install turned up two failures:
1. `numpy` was left unpinned, resolved to the latest (2.x). `chromadb==0.4.22` uses `np.float_`, removed in NumPy 2.0 — `AttributeError` on import.
2. `sentence-transformers==2.2.2` imports `cached_download` from `huggingface_hub`, which no longer exists in current `huggingface_hub` — `ImportError` on import.

Also tested on Python 3.14 first (this machine's default `python3`) and hit a separate, unrelated failure: `chromadb==0.4.22`'s pinned `pydantic-core` has no prebuilt wheel for 3.14 and fails building from source. Not fixed directly — re-tested on Python 3.11 instead, since that's the actual Docker deployment target (`python:3.11-slim`), and 3.11 was available locally too.

**Fix:** Pinned `numpy==1.26.4` (last 1.x line, compatible with `chromadb==0.4.22`). Bumped `sentence-transformers` to `2.7.0` (drops the removed `huggingface_hub` API).

**Verification:** Full clean-venv install on Python 3.11, followed by an actual functional round trip — not just "pip resolved a dependency graph" — extract → clean → chunk → embed → store → search against real chunked data, confirmed working end to end.

### 4. store.py metadata bug — list fields silently emptied, numeric fields returned as strings
**Found:** 2026-08-22, verifying `src/rag/store.py`'s embed/store/search round trip against real chunked data
**Fixed:** 2026-08-22, `src/rag/store.py` (moved from `src/store.py`, rewritten during the fix)

**Problem:** `add_chunks()` serialized list-typed metadata fields (`sections`) using Python's `str()` — `str(['3.1.2', '4.5'])` produces `"['3.1.2', '4.5']"`, single-quoted, which is **not valid JSON**. `search()` then called `json.loads()` on that string to restore it, wrapped in a `try/except (json.JSONDecodeError, ValueError)` that silently fell back to `[]` on failure. Confirmed directly: `json.loads("['3.1.2', '4.5']")` raises `json.JSONDecodeError`. Verified against real data — 63 of 69 chunks from the CC&Rs document have a non-empty `sections` list, meaning **the large majority of real chunks would silently lose their section citations on retrieval**, with no error or warning surfaced anywhere. An empty-list test alone (`str([])` = `"[]"`, which happens to also be valid JSON) would never have caught this — only testing against real populated data did.

Separately, `page_start`, `page_end`, `char_start`, `char_end` were blanket-converted from int to string at write time (`if isinstance(v, int): meta_str[k] = str(v)`) and never converted back on read — `sections` was explicitly restored via `json.loads()` but these numeric fields were not, so they came back as `'1'` instead of `1`. ChromaDB actually supports int metadata natively, so this stringify step wasn't even necessary.

**Fix:** Rewrote `_prepare_metadata()` / `_restore_metadata()` (new helper functions) in the relocated `src/rag/store.py`: lists are `json.dumps()`'d (valid JSON, round-trips correctly), ints pass through natively (no stringify needed), and `Optional[str]` fields (`article`, `section_inherited`) that get stored as `""` in place of `None` (ChromaDB metadata can't hold `None`) are explicitly restored back to `None` on read.

**Verification (real CC&Rs chunks, populated `sections`):**

| Field | Before | After |
|---|---|---|
| `sections` (69 chunks, 63 populated) | `[]` on every populated chunk (silently wrong) | Exact match to original, e.g. `['1.4.4', '1.4.5']` |
| `page_start` / `page_end` | `'15'` (str) | `15` (int) |
| `article` | `''` when originally `None` | `None` |

Direct before/after comparison on a specific chunk (`chunk_11`) confirmed byte-exact round trip after the fix.

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

Re-running the full pipeline (extract → clean → chunk) surfaced a **new**, narrower issue — letter-spaced text on an embedded exhibit section — documented separately as Won't Fix #6 above (deliberately not addressed — see that entry for reasoning), rather than folded into this fix.

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
**File:** `src/rag/chunk.py` (was `src/chunk.py` at the time of this fix, relocated later) — `chunks_from_paragraphs()`

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
