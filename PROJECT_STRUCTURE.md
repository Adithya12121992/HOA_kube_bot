# HOA Bot - Project Structure

Current directory organization. See `ISSUES_AND_FIXES.md` for verification details on everything below.

```
Kube_HOA_bot/
├── README.md                      # Project overview, architecture, quick start
├── GETTING_STARTED.md             # Command-reference quickstart
├── PROJECT_STRUCTURE.md           # This file
├── ISSUES_AND_FIXES.md            # Source of truth: every real bug found & fixed, with verification data
├── PLAN.md                        # Original phased implementation plan (historical)
├── PROMPTS.md                     # Development prompt history
├── requirements.txt                # Production dependencies
├── requirements-dev.txt           # Test-only tooling (pytest, httpx pin) - not in Docker images
├── pytest.ini                     # Test discovery config
├── .env                           # Local dev environment variables (gitignored)
├── .gitignore
│
├── docker/
│   ├── hoa-bot.dockerfile          # FastAPI service: upload UI + chat UI + REST API
│   └── consumer.dockerfile         # Background document-processing worker
│
├── k8s/
│   ├── README.md                   # Kubernetes deployment guide
│   ├── rmq.yaml                    # RabbitMQ cluster
│   ├── pvc.yaml                    # Shared persistent volume (producer-consumer-pvc)
│   ├── hoa-bot-deployment.yaml     # hoa-bot pod + service
│   ├── consumer-deployment.yaml    # consumer pod
│   └── hoa-bot-ingress.yaml        # Stable Ingress-based access (replaces kubectl port-forward)
│
├── src/
│   ├── __init__.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   │
│   │   ├── chatbot/                # Upload UI + chat UI + REST API (one FastAPI service)
│   │   │   ├── __init__.py
│   │   │   ├── service.py          # Endpoints: /, /admin/upload, /ask, /config, /status, /health
│   │   │   └── static/
│   │   │       └── index.html      # Combined upload + chat UI (HTML/CSS/JS)
│   │   │
│   │   ├── consumer/                # Message consumer + document-processing worker
│   │   │   ├── __init__.py
│   │   │   └── app.py              # extract → chunk → embed → store → summarize → status
│   │   │
│   │   └── producer/                # Test message producer (dev/debugging only)
│   │       ├── __init__.py
│   │       └── app.py
│   │
│   ├── rag/                        # RAG (Retrieval-Augmented Generation) pipeline
│   │   ├── __init__.py
│   │   ├── extract.py              # PDF → paragraph-structured text (pdfplumber, vertical-gap detection)
│   │   ├── clean.py                # Boilerplate/header/footer stripping (word n-gram + margin detection)
│   │   ├── chunk.py                # Recursive chunking, doc-type classification, section/article metadata
│   │   ├── store.py                # ChromaDB + Pinecone dual-write, environment-toggle-aware search,
│   │   │                           #   LlamaIndex-backed cloud retrieval
│   │   ├── llm.py                  # Environment-aware LLM caller (LM Studio local, Anthropic cloud)
│   │   ├── query.py                # Fast-mode answer generation
│   │   ├── thinking.py             # Thinking-mode: corrective RAG (retrieve→grade→rewrite→generate)
│   │   ├── memory.py               # Conversation memory (Mem0 cloud, in-process dict local)
│   │   ├── summarize.py            # Per-document summary generation
│   │   └── status.py               # Shared per-document processing status (PVC-backed JSON)
│   │
│   └── config/
│       ├── __init__.py
│       └── settings.py             # Central config: environment/retrieval-mode toggles (PVC-shared JSON,
│                                    #   not frozen module-level values - see ISSUES_AND_FIXES.md #11),
│                                    #   API keys, model names, RabbitMQ connection settings
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # isolated_data_dir fixture: fresh ChromaDB + config per test,
│   │                                #   reloads the full settings→store→memory→query→thinking chain
│   │
│   ├── unit/                       # Pure logic, no I/O
│   │   ├── __init__.py
│   │   ├── test_chunk.py           # classify_doc_type, section/article detection, overlap bounds
│   │   ├── test_clean.py           # BoilerplateDetector detect/strip
│   │   ├── test_config.py          # Config toggle persistence, cross-"process" visibility
│   │   ├── test_memory_local.py    # In-process session memory backend
│   │   └── test_store_metadata.py  # Metadata encode/decode round-trip
│   │
│   ├── integration/                # Real ChromaDB + real embeddings, LLM call itself mocked
│   │   ├── __init__.py
│   │   ├── test_store_chromadb.py  # add_chunks/search/reset round trip
│   │   ├── test_query_pipeline.py  # Fast-mode answer flow
│   │   ├── test_thinking_pipeline.py  # Thinking-mode control flow (grade/rewrite/generate)
│   │   └── test_service_api.py     # FastAPI TestClient: real routing, real config toggle
│   │
│   ├── benchmarks/                 # Empty - not built (see README.md "Known Gaps")
│   ├── evals/                      # Empty - not built (see README.md "Known Gaps")
│   └── fixtures/                   # Empty - not currently used
│
├── docs/                           # Real sample HOA documents used for verification throughout
│   ├── 0. Coversheet.pdf
│   ├── 30. CC&Rs (Required Civil Code Sec. 4525).pdf
│   ├── 32. Annual Budget Report...pdf
│   ├── ... (40 real documents total: governing, financial, advisory, report types)
│   ├── api/                        # Empty
│   └── architecture/               # Empty
│
├── venv/                           # Python virtual environment (gitignored)
├── local_test_data/                # Local dev DATA_DIR: .chroma_data/, status/, config.json (gitignored)
└── .pytest_cache/                  # Test cache (gitignored)
```

---

## Notes on a Few Directories

- `web_ui` is not a separate service — `hoa-bot` (FastAPI) serves both the upload UI and the chat UI from one service.
- No standalone `pipeline.py` orchestrator — `consumer/app.py` calls the `rag/` modules directly in sequence.
- `rag_graph.py` was removed — `thinking.py` implements corrective RAG as a plain bounded loop instead (see `ISSUES_AND_FIXES.md` #13 for why).
- `scripts/` and `tests/benchmarks/`, `tests/evals/` are present but empty — not built yet (see README.md "Known Gaps").

---

## Key Files

### Configuration
- **`src/config/settings.py`** — `get_environment()` / `get_retrieval_mode()` read a shared JSON file on the PVC fresh on every call (not frozen module-level values — this was a real bug, fixed, see `ISSUES_AND_FIXES.md` #11). `update_config()` writes to it.

### Services
- **`src/services/chatbot/service.py`** — the only user-facing service. `/ask` dispatches to fast or thinking mode based on the toggle, both wrapped in `asyncio.to_thread()` (see `ISSUES_AND_FIXES.md` #12 for why that matters).
- **`src/services/consumer/app.py`** — the only thing that mutates document state. Runs entirely in the background, no HTTP surface.

### RAG Pipeline
- **`src/rag/store.py`** — the most load-bearing file: dual-write, environment-toggle search dispatch, LlamaIndex integration, and a real fix for a ChromaDB cross-process staleness bug (`ISSUES_AND_FIXES.md` #17).
- **`src/rag/thinking.py`** — corrective RAG, not a LangGraph `StateGraph`.
- **`src/rag/memory.py`** — Mem0 (cloud) or in-process dict (local), both optional enhancements keyed by `user_id`.

### Deployment
- **`docker/hoa-bot.dockerfile`**, **`docker/consumer.dockerfile`** — both install CPU-only PyTorch before `requirements.txt` (cuts image size from ~9GB to ~2.5GB).
- **`k8s/hoa-bot-ingress.yaml`** — real k3d port-published Ingress, replacing `kubectl port-forward` (whose idle timeout is shorter than a local LLM's response time).

---

## Import Examples

```python
# Configuration
from src.config.settings import get_environment, get_retrieval_mode, update_config

# RAG pipeline
from src.rag.extract import extract_document
from src.rag.chunk import chunk_document
from src.rag.store import add_chunks, search, reset
from src.rag.query import answer_question
from src.rag.thinking import answer_question_thinking
from src.rag.memory import get_relevant_memories, add_memory
```

```bash
# Tests
pytest tests/unit/          # Unit tests (46)
pytest tests/integration/   # Integration tests (23)
pytest tests/ -v            # All 69
```

---

## Development Workflow

```bash
# 1. Setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for running tests

# 2. Test locally before touching K8s
pytest tests/ -v

# 3. Build Docker images
docker build -f docker/hoa-bot.dockerfile -t hoa-bot:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .

# 4. Deploy / redeploy
k3d image import hoa-bot:latest consumer:latest -c HOA-Bot
kubectl rollout restart deployment/hoa-bot deployment/consumer -n hoa-pipeline
kubectl -n hoa-pipeline get pods   # verify Running, 0 restarts

# 5. Verify against the real deployed service
curl http://localhost:8000/health
```
