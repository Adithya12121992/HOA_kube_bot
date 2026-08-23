# Top 5 Prompts Used in Development

## 1. **RabbitMQ Producer Setup**
*Create a venv, requirements.txt, and producer code that produces messages to RabbitMQ*

- Generate UUID4 doc_id
- Incremental filenames and /tmp file paths
- ISO 8601 timestamps for uploaded_at
- Message format: `{"doc_id", "original_filename", "file_path", "uploaded_at"}`
- Deploy as Kubernetes pod with concurrent message production

**Result:** `producer.py`, `requirements.txt`, producer Docker image

---

## 2. **File Upload Web UI**
*Create a simple UI that lets you upload a file, save it to the PVC, and produce a RabbitMQ message with the proper file path*

- Flask web app with drag-and-drop file upload
- Save uploaded files to mounted PVC (/data)
- Auto-generate UUID for doc_id
- Produce message to RabbitMQ with file metadata
- Display upload result with all details (doc_id, file path, timestamp)

**Result:** `web_ui.py`, `templates/index.html`, web UI Docker image, deployment manifest

---

## 3. **Multiple File Upload Support**
*Modify the UI to support multiple file uploads with concurrent processing*

- Allow selecting multiple files at once
- Display all selected files with sizes
- Upload files sequentially or in parallel
- Show individual status for each file (uploading, done, failed)
- Summary of successful and failed uploads

**Result:** Updated `templates/index.html` with multi-file support, progress tracking UI

---

## 4. **Concurrent Message Consumer**
*Create a consumer that processes a max of 3 messages concurrently, and if any one completes, picks the next message without waiting for all 3 to finish*

- ThreadPoolExecutor with max 3 workers
- `prefetch_count=3` to tell RabbitMQ send max 3 messages
- Non-blocking processing — as soon as one finishes, next one starts
- Proper error handling and thread-safe channel operations
- Auto-reconnection on stream loss

**Result:** `consumer.py` with concurrent processing, consumer Docker image, deployment manifest

---

## 5. **File Deletion on Message Processing**
*Have the consumer delete the file from the PVC after marking the message as read in RabbitMQ*

- Extract file_path from message metadata
- Check if file exists in PVC
- Delete file after successful processing
- Handle errors gracefully (warn if file not found, still acknowledge message)
- Log deletion status

**Result:** Updated `consumer.py` with file deletion logic

---

## Supporting Prompts (Implementation Details)

### Infrastructure & Documentation
- Create comprehensive README for k3d + RabbitMQ setup with K8s manifests
- Create PVC (200MB) for shared storage between producer and consumer
- Explain RabbitMQ credentials flow from Operator Secret to deployments
- Generate Dockerfiles for producer, consumer, and web UI

### Debugging & Troubleshooting
- Fix connection errors by clarifying port 5672 vs 15672
- Add thread-safe locking for concurrent RabbitMQ channel operations
- Implement reconnection logic for StreamLostError handling
- Explain why credentials changed and how to verify from K8s secrets

### Architecture Understanding
- Explain the full HOA RAG pipeline (chunk.py, store.py, pipeline.py, app.py)
- Clarify how vector embeddings enable semantic search
- Document message flow: Upload → Queue → Process → Delete

---

## Key Technologies Used

- **Messaging:** RabbitMQ (Kubernetes Operator)
- **Container Orchestration:** Kubernetes (k3d cluster, 3 nodes)
- **Web Framework:** Flask
- **Frontend:** HTML/CSS/JavaScript (modern UI)
- **Concurrency:** Python ThreadPoolExecutor
- **Storage:** PersistentVolumeClaim (local-path)
- **Containers:** Docker
- **Database:** ChromaDB (for RAG pipeline)
- **Embeddings:** BAAI/bge-small-en-v1.5

---

## Development Timeline

1. ✅ Set up venv and basic producer
2. ✅ Created comprehensive README for K3d + RabbitMQ
3. ✅ Built Flask web UI with file upload
4. ✅ Enhanced UI for multi-file uploads
5. ✅ Implemented concurrent consumer (max 3 threads)
6. ✅ Added file deletion logic
7. ✅ Created all Docker images and K8s manifests
8. ✅ Pushed to GitHub with documentation

---

## Since Week 1: RAG Pipeline, Environment Bundles, and Real Bug Fixes

The prompts above cover the original Week 1 submission (RabbitMQ pipeline scaffolding). Everything below documents the substantial work since — turning that scaffolding into an actual working RAG chatbot. Full detail with real before/after verification data for every item lives in **[ISSUES_AND_FIXES.md](ISSUES_AND_FIXES.md)**; this section is a prompt-level summary.

### 9. **Real PDF Extraction & Chunking**
*Fix the naive per-page text extraction and chunking bugs found against a real 88-page CC&Rs document*

- Replaced a naive `page.extract_text()` join with paragraph-aware extraction (word/line grouping, vertical-gap paragraph detection)
- Built n-gram-based boilerplate detection to strip repeated headers/footers, including corrupted/merged variants
- Fixed an 18x-too-many-chunks bug caused by unbounded paragraph-rewind overlap

**Result:** `src/rag/extract.py`, `src/rag/clean.py`, `src/rag/chunk.py` — see `ISSUES_AND_FIXES.md` #1-#3

### 10. **Environment Bundles: Local vs. Cloud**
*Add a toggle that switches storage, LLM, RAG framework, and memory together as one bundle, with dual-write so both can be compared on identical data*

- ChromaDB (local) + Pinecone (cloud), always dual-written on upload
- Fixed a real config-propagation bug where the toggle was frozen at import time and invisible across pods
- Wired real cloud LLM fallback (Anthropic), deliberately narrowed to Anthropic-only per explicit preference (not OpenAI, despite the key being available)

**Result:** `src/config/settings.py`, `src/rag/store.py`, `src/rag/llm.py` — see `ISSUES_AND_FIXES.md` #9-#11

### 11. **Unified FastAPI Service + Production Bug Fix**
*Consolidate the upload UI and chat UI into one service, fix a real production incident*

- Folded the separate web-ui concept into one FastAPI service (`hoa-bot`) serving both UI and REST API
- Fixed a real user-reported production bug: a blocking LLM call inside an async endpoint was starving the event loop, causing Kubernetes' liveness probe to kill the pod mid-request
- Replaced `kubectl port-forward` (idle timeout shorter than local LLM response time) with a real k3d Ingress for stable access

**Result:** `src/services/chatbot/service.py`, `k8s/hoa-bot-ingress.yaml` — see `ISSUES_AND_FIXES.md` #12

### 12. **Corrective RAG ("Thinking" Mode), Wired For Real**
*Audit a prototype LangGraph implementation, decide whether it's actually worth keeping as a graph, and wire whichever approach is real*

- Found the existing prototype hardcoded a wrong model name against the wrong LLM address, with debug artifacts left in
- Rebuilt as a plain bounded retrieve→grade→rewrite→generate loop instead of a LangGraph `StateGraph` — deliberate simplification, not a missing feature
- Verified against 3 real end-to-end scenarios (doc-type-aware grading, bounded rewrite behavior, safe refusal)

**Result:** `src/rag/thinking.py` (new), `src/rag/rag_graph.py` deleted — see `ISSUES_AND_FIXES.md` #13

### 13. **Mem0 Conversation Memory + Real LlamaIndex Integration**
*Wire the two Phase-5 features that were never actually implemented, despite being claimed in settings/docs*

- Mem0: real API (not mocked), correct `filters={"user_id":...}` contract (the naive call shape raises a real error), verified with real 2-turn conversations recalling prior context
- LlamaIndex: found it was a documentation-only label with no actual dependency; added a real `PineconeVectorStore`-backed retrieval path for the cloud bundle, using this project's own embedding call for consistency with the write path

**Result:** `src/rag/memory.py` (new), `src/rag/store.py` — see `ISSUES_AND_FIXES.md` #14-#15

### 14. **Automated Test Suite**
*Build unit + integration tests that lock in correctness, not just demo it*

- 69 tests: pure-logic unit tests (chunking, cleaning, metadata, config) + integration tests against real ChromaDB and real embeddings, with only the outbound LLM call mocked
- Found and fixed a real bug in the test harness itself along the way — a frozen-import issue where cached test modules pointed at a stale store instance across tests

**Result:** `tests/` (new) — see `ISSUES_AND_FIXES.md` #16

### 15. **Real ChromaDB Cross-Process Staleness Bug**
*Diagnose a real user-reported bug: an uploaded document's content wasn't answerable via chat, even though the upload succeeded*

- Root cause was not this project's own code but chromadb's internal `SharedSystemClient` process-level cache, which meant the long-running chat service never saw writes made by the separate consumer process without a restart
- Verified the fix with a real synchronized cross-process reproduction, then confirmed against the live deployed service with zero pod restarts

**Result:** `src/rag/store.py` — see `ISSUES_AND_FIXES.md` #17

---

## Key Technologies Added Since Week 1

- **RAG:** `pdfplumber`, `sentence-transformers` (`BAAI/bge-small-en-v1.5`), ChromaDB, Pinecone, LlamaIndex
- **LLMs:** LM Studio (local), Anthropic Claude (cloud)
- **Memory:** Mem0
- **API:** FastAPI (replacing the original Flask web-ui)
- **Testing:** pytest, FastAPI `TestClient`

