# HOA Bot - Project Structure

Production-grade directory organization for Kubernetes async pipeline with RAG chatbot.

```
Kube_HOA_bot/
├── README.md                      # Project overview
├── PLAN.md                        # Implementation plan (10 phases)
├── PROMPTS.md                     # Key development prompts
├── PROJECT_STRUCTURE.md           # This file
├── requirements.txt               # Python dependencies
├── .gitignore
│
├── docker/                        # All Docker-related files
│   ├── web-ui.dockerfile          # Web UI upload service
│   ├── consumer.dockerfile        # Consumer: processes messages
│   └── chatbot.dockerfile         # (Phase 5) REST API + HTML chatbot
│
├── k8s/                           # All Kubernetes manifests
│   ├── rmq.yaml                   # RabbitMQ cluster
│   ├── pvc.yaml                   # Persistent volume (shared storage)
│   ├── web-ui-deployment.yaml     # Web UI pod + service
│   ├── consumer-deployment.yaml   # Consumer pod
│   ├── chatbot-deployment.yaml    # (Phase 5) Chatbot pod + service
│   └── namespace.yaml             # (Future) K8s namespace config
│
├── src/                           # Source code
│   ├── __init__.py
│   │
│   ├── services/                  # Microservices
│   │   ├── __init__.py
│   │   │
│   │   ├── web_ui/                # File upload web interface
│   │   │   ├── __init__.py
│   │   │   ├── app.py             # Flask application
│   │   │   └── templates/
│   │   │       └── index.html     # Upload UI template
│   │   │
│   │   ├── producer/              # Test message producer
│   │   │   ├── __init__.py
│   │   │   └── app.py             # RabbitMQ test producer
│   │   │
│   │   ├── consumer/              # Message consumer + processor
│   │   │   ├── __init__.py
│   │   │   ├── app.py             # Main consumer logic
│   │   │   └── worker.py          # Document processing worker (Phase 2)
│   │   │
│   │   └── chatbot/               # REST API + HTML chatbot (Phase 5)
│   │       ├── __init__.py
│   │       ├── service.py         # FastAPI application
│   │       └── static/
│   │           └── index.html     # Chat UI (HTML + CSS + JS)
│   │
│   ├── rag/                       # RAG (Retrieval-Augmented Generation) pipeline
│   │   ├── __init__.py
│   │   ├── chunk.py               # Document chunking (semantic, section-aware)
│   │   ├── store.py               # Vector DB abstraction (ChromaDB + Pinecone)
│   │   ├── pipeline.py            # RAG pipeline orchestrator
│   │   ├── rag_graph.py           # LangGraph: retrieve → grade → rewrite → generate
│   │   └── utils.py               # Shared utilities
│   │
│   └── config/                    # Configuration management
│       ├── __init__.py
│       └── settings.py            # Central config (toggles + fixed settings)
│
├── tests/                         # Test suite (Phase 6+)
│   ├── __init__.py
│   │
│   ├── unit/                      # Unit tests (individual components)
│   │   ├── test_chunking.py
│   │   ├── test_embedding.py
│   │   ├── test_vector_db.py
│   │   └── test_rag.py
│   │
│   ├── integration/               # Integration tests (workflows)
│   │   ├── test_pdf_to_chunks.py
│   │   ├── test_dual_storage.py
│   │   ├── test_consumer_pipeline.py
│   │   └── test_query_pipeline.py
│   │
│   ├── benchmarks/                # Performance benchmarks
│   │   ├── benchmark_latency.py
│   │   ├── benchmark_accuracy.py
│   │   └── benchmark_throughput.py
│   │
│   ├── evals/                     # Evaluation tests (quality)
│   │   ├── eval_retrieval.py
│   │   └── eval_answer_quality.py
│   │
│   ├── fixtures/                  # Test data & fixtures
│   │   ├── sample_chunks.json
│   │   ├── expected_embeddings.json
│   │   └── benchmark_queries.json
│   │
│   └── conftest.py                # Pytest configuration
│
├── docs/                          # Documentation
│   ├── README.md                  # Getting started
│   │
│   ├── samples/                   # Sample PDFs for testing
│   │   ├── README.md
│   │   ├── Sample_Governing_Rules.pdf
│   │   ├── Sample_Financial_Report.pdf
│   │   ├── Sample_Inspection_Report.pdf
│   │   ├── Sample_Disclosure_Document.pdf
│   │   └── Sample_Meeting_Minutes.pdf
│   │
│   ├── benchmarks/                # Benchmark results
│   │   ├── benchmark-comparison.md
│   │   ├── benchmark_results.json
│   │   ├── eval_results.json
│   │   ├── eval_answer_results.json
│   │   └── comparison_report.json
│   │
│   ├── architecture/              # Design documentation
│   │   ├── chatbot_architecture.md
│   │   ├── vector_db_architecture.md
│   │   └── config_structure.md
│   │
│   └── api/                       # API documentation
│       └── endpoints.md
│
├── scripts/                       # Utility scripts
│   ├── setup_cluster.sh           # Create k3d cluster
│   ├── deploy.sh                  # Deploy to Kubernetes
│   ├── generate_sample_pdfs.py    # Generate test data
│   └── run_benchmarks.sh          # Run benchmark suite
│
├── .venv/                         # Python virtual environment (gitignored)
├── .chroma_data/                  # Local ChromaDB data (gitignored)
└── chunks.json                    # Generated chunks (gitignored)
```

---

## Directory Purpose Summary

| Directory | Purpose | Phase |
|-----------|---------|-------|
| `docker/` | Container images for all services | Phase 1 |
| `k8s/` | Kubernetes manifests for deployment | Phase 1 |
| `src/services/web_ui/` | File upload interface | Phase 0 (existing) |
| `src/services/producer/` | Test message producer | Phase 0 (existing) |
| `src/services/consumer/` | Message processor + document ingestion | Phase 2 |
| `src/services/chatbot/` | REST API + HTML chatbot UI | Phase 5 |
| `src/rag/` | RAG pipeline (chunking, embedding, retrieval) | Phase 2-3 |
| `src/config/` | Centralized configuration management | Phase 3-5 |
| `tests/` | Comprehensive test suite | Phase 6+ |
| `docs/samples/` | Sample PDFs for testing | Phase 4 |
| `docs/benchmarks/` | Benchmark results & analysis | Phase 8-9 |
| `docs/architecture/` | Design & architecture docs | Ongoing |
| `scripts/` | Utility scripts for setup & deployment | Ongoing |

---

## Key Files

### Configuration
- **`src/config/settings.py`** — Central config with:
  - User toggles: `storage_mode` (local/hybrid), `retrieval_mode` (fast/thinking)
  - Fixed config: embedding model, chunk size, Pinecone API, RabbitMQ, etc.

### Services
- **`src/services/web_ui/app.py`** — Flask app for uploading files
- **`src/services/producer/app.py`** — Test producer (optional, for development)
- **`src/services/consumer/app.py`** — Main message processor
- **`src/services/chatbot/service.py`** — FastAPI for REST API + HTML chatbot

### RAG Pipeline
- **`src/rag/chunk.py`** — Document chunking
- **`src/rag/store.py`** — Vector DB abstraction
- **`src/rag/pipeline.py`** — Orchestrator
- **`src/rag/rag_graph.py`** — LangGraph implementation

### Deployment
- **`docker/web-ui.dockerfile`** — Web UI container
- **`docker/consumer.dockerfile`** — Consumer container
- **`docker/chatbot.dockerfile`** — Chatbot service container
- **`k8s/web-ui-deployment.yaml`** — Web UI deployment
- **`k8s/consumer-deployment.yaml`** — Consumer deployment
- **`k8s/chatbot-deployment.yaml`** — Chatbot deployment (Phase 5)

---

## Import Examples

```python
# Get configuration
from src.config.settings import STORAGE_MODE, RETRIEVAL_MODE, get_config_dict

# Use RAG pipeline
from src.rag.pipeline import RAGEngine
from src.rag.chunk import chunk_document
from src.rag.store import VectorStore

# Run tests
pytest tests/unit/          # Unit tests
pytest tests/integration/   # Integration tests
pytest tests/benchmarks/    # Performance benchmarks
pytest tests/evals/         # Quality evaluation
```

---

## Development Workflow

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Build Docker images
docker build -f docker/web-ui.dockerfile -t web-ui:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
docker build -f docker/chatbot.dockerfile -t chatbot:latest .

# 3. Deploy to K8s
k3d cluster create HOA-Bot --servers 1 --agents 2
kubectl create namespace hoa-pipeline
kubectl apply -f k8s/rmq.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/web-ui-deployment.yaml
kubectl apply -f k8s/consumer-deployment.yaml

# 4. Test
pytest tests/unit/ -v
pytest tests/integration/ -v

# 5. Benchmark (Phase 8)
pytest tests/benchmarks/ -v
```

---

## Phase Integration

This structure supports the 10-phase implementation plan:

- **Phase 1:** Docker migration → Use `docker/` files
- **Phase 2:** Chunking & embedding → Implement `src/rag/chunk.py`, update `src/services/consumer/`
- **Phase 3:** Dual storage → Enhance `src/rag/store.py`, update `src/config/settings.py`
- **Phase 4:** Sample data → Place PDFs in `docs/samples/`
- **Phase 5:** REST API + chatbot → Implement `src/services/chatbot/`
- **Phase 6:** Tests → Add to `tests/` directories
- **Phase 7-9:** Benchmarking → Results in `docs/benchmarks/`
- **Phase 10:** Documentation → All docs in `docs/`

---

**Structure is production-ready. Each directory has a single responsibility.**
