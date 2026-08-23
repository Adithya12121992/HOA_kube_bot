# Getting Started with HOA Bot

A production-grade Kubernetes RAG chatbot for HOA document Q&A.

## Quick Links

- **[README.md](README.md)** — Architecture, environment bundles, retrieval modes
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** — Directory organization
- **[ISSUES_AND_FIXES.md](ISSUES_AND_FIXES.md)** — What's actually built, tested, and fixed (source of truth)
- **[k8s/README.md](k8s/README.md)** — Kubernetes deployment guide
- **[PLAN.md](PLAN.md)** — Original phased plan (historical)

## Architecture at a Glance

```
Upload / Ask         Queue           Process
     ↓                 ↓                ↓
  hoa-bot    ──────▶ RabbitMQ ──────▶ consumer
 (FastAPI)                          extract → clean → chunk
 Port 8000                          → embed → store → summarize
     ↑                                        │
     └────────────────── shared PVC ──────────┘
        (uploaded files, ChromaDB, config.json, status/*.json)
```

**Data Flow:**
1. User uploads a PDF via **hoa-bot**'s upload UI (port 8000)
2. A message is sent to the **RabbitMQ** queue
3. **consumer** processes it: extract text → clean boilerplate → chunk → embed → dual-write to storage → summarize
4. User asks questions via **hoa-bot**'s chat UI (same port 8000)
5. The RAG pipeline retrieves relevant chunks and generates a grounded, cited answer

**Storage (dual-write on every upload):**
- ChromaDB — always written, required
- Pinecone — best-effort, only if `PINECONE_API_KEY` is configured

## Prerequisites

- Docker & k3d (for Kubernetes)
- Python 3.11 (not 3.14 — real pydantic-core build failures on newer Python, use `python3.11` explicitly)
- (Optional) LM Studio running on the host for the `local` environment's LLM
- (Optional) Pinecone / Anthropic / Mem0 API keys for the `cloud` environment

## 5-Minute Quickstart

```bash
# 1. Create K8s cluster
k3d cluster create HOA-Bot --servers 1 --agents 2

# 2. Setup & build
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

docker build -f docker/hoa-bot.dockerfile -t hoa-bot:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
k3d image import hoa-bot:latest consumer:latest -c HOA-Bot

# 3. Deploy
kubectl create namespace hoa-pipeline
kubectl apply -f k8s/rmq.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/consumer-deployment.yaml
kubectl apply -f k8s/hoa-bot-deployment.yaml

# 4. Stable access (avoids kubectl port-forward's short idle timeout)
k3d cluster edit HOA-Bot --port-add 8000:80@loadbalancer   # one-time
kubectl apply -f k8s/hoa-bot-ingress.yaml

# 5. Use
# Everything (upload + chat + API): http://localhost:8000
```

## Configuration

Toggle via the **hoa-bot UI** (http://localhost:8000) or directly:

```bash
curl -X POST http://localhost:8000/config -H "Content-Type: application/json" \
  -d '{"environment": "cloud", "retrieval_mode": "thinking"}'
```

- **`environment`**: `"local"` (ChromaDB + LM Studio + plain retrieval + in-process memory) or `"cloud"` (Pinecone + Anthropic + LlamaIndex + Mem0) — a full bundled stack switch, not four independent settings
- **`retrieval_mode`**: `"fast"` (2–5s) or `"thinking"` (10–30s, corrective RAG with query rewriting)

Centralized config: [src/config/settings.py](src/config/settings.py). Toggle state is persisted to `{DATA_DIR}/config.json` on the shared PVC so both `hoa-bot` and `consumer` see the same value — see `ISSUES_AND_FIXES.md` #11 for why this isn't a plain in-memory setting.

## Project Structure

```
docker/              hoa-bot.dockerfile, consumer.dockerfile
k8s/                 rmq.yaml, pvc.yaml, hoa-bot-deployment.yaml,
                      consumer-deployment.yaml, hoa-bot-ingress.yaml
src/
  ├─ services/       chatbot/ (FastAPI: UI + REST API), consumer/ (worker)
  ├─ rag/            extract, clean, chunk, store, llm, query, thinking,
                      memory, summarize, status
  └─ config/         settings.py (environment/retrieval-mode toggles)
tests/               unit/, integration/, conftest.py (69 tests, real
                      ChromaDB + real embeddings, LLM call mocked)
docs/                Real sample HOA documents used for verification
```

→ See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for full details

## Key Services

### hoa-bot (Port 8000)
- **Purpose:** Upload UI + chat UI + REST API, all in one FastAPI service
- **Endpoints:** `GET /` (UI), `POST /admin/upload`, `POST /ask`, `GET /config`, `POST /config`, `GET /status`, `GET /status/{doc_id}`, `GET /health`
- **Code:** [src/services/chatbot/service.py](src/services/chatbot/service.py)

### consumer (background worker, no exposed port)
- **Purpose:** Consume upload messages from RabbitMQ, run the full extract→chunk→embed→store→summarize pipeline
- **Code:** [src/services/consumer/app.py](src/services/consumer/app.py)
- Concurrent processing (ThreadPoolExecutor, prefetch_count=3), auto-reconnect on stream loss

### RAG Pipeline
- **Extraction:** paragraph-aware, via `pdfplumber` word/line grouping — not a naive page dump
- **Chunking:** ~3,200 chars, bounded 300-char overlap, section/article-aware citations
- **Embedding:** `BAAI/bge-small-en-v1.5` (384-dim), always runs locally regardless of environment
- **Storage:** ChromaDB (required) + Pinecone (best-effort), dual-write
- **Retrieval:** plain loop (local) or LlamaIndex `PineconeVectorStore` (cloud); fast or thinking mode
- **Code:** [src/rag/](src/rag/)

## Common Commands

```bash
# Build Docker images
docker build -f docker/hoa-bot.dockerfile -t hoa-bot:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .

# Import into k3d and redeploy after a code change
k3d image import hoa-bot:latest consumer:latest -c HOA-Bot
kubectl rollout restart deployment/hoa-bot deployment/consumer -n hoa-pipeline

# Check status
kubectl -n hoa-pipeline get pods
kubectl -n hoa-pipeline logs -f deployment/consumer
kubectl -n hoa-pipeline logs -f deployment/hoa-bot

# Run tests
pip install -r requirements-dev.txt
pytest tests/ -v
pytest tests/unit/ -v
pytest tests/integration/ -v

# Cleanup
kubectl delete namespace hoa-pipeline
k3d cluster delete HOA-Bot
```

## Troubleshooting

**Pod not starting?**
```bash
kubectl -n hoa-pipeline describe pod <pod-name>
```

**Ingress not responding at localhost:8000?**
```bash
# Confirm the k3d port-add was actually applied to this cluster
k3d cluster edit HOA-Bot --port-add 8000:80@loadbalancer
kubectl apply -f k8s/hoa-bot-ingress.yaml
```

**RabbitMQ not ready?**
```bash
kubectl -n hoa-pipeline get pods -l app=hoa-rabbitmq
```

**Uploaded doc not answerable via /ask right after uploading?**
See `ISSUES_AND_FIXES.md` #17 — a real ChromaDB cross-process staleness bug, fixed. If you're on an image built before that fix, restart `hoa-bot` after each upload as a workaround.

**Files not being processed?**
```bash
kubectl -n hoa-pipeline logs deployment/consumer -f
```

## Next Steps

1. **Setup:** Follow "5-Minute Quickstart" above
2. **Explore:** Read [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) and [ISSUES_AND_FIXES.md](ISSUES_AND_FIXES.md)
3. **Test:** `pytest tests/ -v`
4. **Extend:** See "Known Gaps" in [README.md](README.md) for what's genuinely still missing (OCR, an automated eval set)

---

**Ready to start? Follow the "5-Minute Quickstart" above.**
