# HOA Bot — Kubernetes-Deployed RAG Chatbot for HOA Documents

A production-grade, Kubernetes-deployed RAG (Retrieval-Augmented Generation) chatbot for HOA (homeowners association) document Q&A. Upload PDFs → async extraction/chunking/embedding pipeline → ask questions and get grounded, cited answers.

Runs as two services on a real k3d/Kubernetes cluster, communicating via RabbitMQ and a shared PVC — not a local script or notebook demo.

---

## 📋 System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       k3d Cluster (HOA-Bot)                              │
│                 1 Control Plane + 2 Agent Nodes                          │
│                                                                          │
│  ┌────────────────────── hoa-pipeline namespace ──────────────────────┐ │
│  │                                                                    │ │
│  │   http://localhost:8000  (stable, via k3d Ingress/Traefik)         │ │
│  │            │                                                       │ │
│  │            ▼                                                       │ │
│  │   ┌────────────────┐        produces         ┌──────────────┐     │ │
│  │   │    hoa-bot      │ ───────messages───────▶ │  RabbitMQ    │     │ │
│  │   │   (FastAPI)     │                         │   Cluster    │     │ │
│  │   │  Upload UI +    │                         └──────┬───────┘     │ │
│  │   │  Chat UI +      │                                │ consumes    │ │
│  │   │  /ask, /config, │                                ▼             │ │
│  │   │  /status API    │                        ┌────────────────┐    │ │
│  │   └───────┬────────┘                         │   consumer     │    │ │
│  │           │                                   │ extract→clean  │    │ │
│  │           │  reads/writes                     │ →chunk→embed   │    │ │
│  │           ▼                                   │ →store→summ.   │    │ │
│  │   ┌─────────────────────────────────────┐    └────────┬───────┘    │ │
│  │   │   PVC: producer-consumer-pvc          │◀───────────┘            │ │
│  │   │   /data — uploaded files, ChromaDB,   │                        │ │
│  │   │   config.json toggle, status/*.json   │                        │ │
│  │   └─────────────────────────────────────┘                        │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│   External (only when environment=cloud):                              │
│   Pinecone (vector store) · Anthropic Claude (LLM) · Mem0 (memory)      │
│   Local (environment=local): ChromaDB · LM Studio (on host machine)     │
└──────────────────────────────────────────────────────────────────────────┘
```

`hoa-bot` is one FastAPI service that serves both the upload UI and the chat UI (no separate web-ui service). `consumer` is a background worker pod that does all document processing. Both share config/state through the PVC, since they're separate K8s pods with no shared memory.

---

## 🧠 How It Works

### Environment bundles (not independent settings)

A single toggle switches **four** things at once — storage, LLM, RAG framework, and memory move together as a bundle, not separately:

| | **local** | **cloud** |
|---|---|---|
| Vector store | ChromaDB (on-disk) | Pinecone |
| LLM | LM Studio (local model) | Anthropic Claude |
| RAG framework | Plain retrieval loop | LlamaIndex (`PineconeVectorStore`) |
| Memory | In-process session dict | Mem0 (real semantic memory API) |

Every upload dual-writes to **both** ChromaDB and Pinecone (Chroma required, Pinecone best-effort) so you can flip the toggle and compare local vs. cloud retrieval on identical data without re-uploading.

### Retrieval modes (independent of environment)

- **fast** — retrieve top-k chunks → generate answer directly (2–5s)
- **thinking** — corrective RAG: retrieve → LLM grades chunk relevance → if insufficient, rewrite the query and re-retrieve (bounded to 2 rewrites) → generate (10–30s, higher precision on ambiguous/colloquial questions)

### Pipeline stages (`src/rag/`)

1. **`extract.py`** — real paragraph-structured PDF extraction via `pdfplumber` (word/line grouping + vertical-gap paragraph detection), not a naive per-page text dump
2. **`clean.py`** — boilerplate/header/footer stripping via word n-gram frequency + margin-position detection
3. **`chunk.py`** — recursive paragraph→sentence→char-limited chunking (~3,200 chars, bounded 300-char overlap), with doc-type classification and section/article citation metadata
4. **`store.py`** — embeds once (`BAAI/bge-small-en-v1.5`, runs locally either way), dual-writes to ChromaDB + Pinecone, environment-toggle-aware search
5. **`query.py`** / **`thinking.py`** — fast-mode and thinking-mode answer generation
6. **`memory.py`** — conversation memory (Mem0 for cloud, in-process dict for local)
7. **`summarize.py`** — per-document summary generated after processing

---

## 🚀 Quick Start

### 1. Prerequisites
- Docker, k3d, kubectl
- Python 3.11 (not 3.14 — real dependency conflicts, see `ISSUES_AND_FIXES.md`)
- (Optional, for `local` environment) LM Studio running on the host machine
- (Optional, for `cloud` environment) Pinecone / Anthropic / Mem0 API keys

### 2. Create the cluster

```bash
k3d cluster create HOA-Bot --servers 1 --agents 2
kubectl get nodes  # verify 3 nodes Ready
```

### 3. Install infrastructure

```bash
kubectl create namespace hoa-pipeline

kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl -n cert-manager get pods  # wait for Ready

kubectl apply -f "https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"
kubectl -n rabbitmq-system get pods  # wait for Ready

kubectl apply -f k8s/rmq.yaml
kubectl -n hoa-pipeline get pods -l app=hoa-rabbitmq  # wait for hoa-rabbitmq-server-0 Ready

kubectl apply -f k8s/pvc.yaml
```

### 4. Build, import, and deploy

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

docker build -f docker/hoa-bot.dockerfile -t hoa-bot:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
k3d image import hoa-bot:latest consumer:latest -c HOA-Bot

kubectl apply -f k8s/consumer-deployment.yaml
kubectl apply -f k8s/hoa-bot-deployment.yaml

kubectl -n hoa-pipeline get pods  # verify Running
```

### 5. Stable access via Ingress

`kubectl port-forward` has an idle timeout shorter than a local reasoning model's response time (confirmed: cut off at exactly 60s). This project uses a real k3d port-published Ingress instead, which survives pod restarts:

```bash
k3d cluster edit HOA-Bot --port-add 8000:80@loadbalancer   # one-time
kubectl apply -f k8s/hoa-bot-ingress.yaml
```

Then just open **http://localhost:8000** — same URL for uploads, chat, and the REST API, no manual port-forward process to babysit.

---

## 📁 Project Structure

```
Kube_HOA_bot/
├── docker/
│   ├── hoa-bot.dockerfile          # FastAPI service (upload UI + chat UI + REST API)
│   └── consumer.dockerfile         # Background document-processing worker
│
├── k8s/
│   ├── rmq.yaml                    # RabbitMQ cluster
│   ├── pvc.yaml                    # Shared persistent volume
│   ├── hoa-bot-deployment.yaml     # hoa-bot pod + service
│   ├── consumer-deployment.yaml    # consumer pod
│   └── hoa-bot-ingress.yaml        # Stable Ingress-based access (see Quick Start #5)
│
├── src/
│   ├── services/
│   │   ├── chatbot/service.py      # FastAPI app: /ask, /config, /status, /admin/upload
│   │   └── consumer/app.py         # RabbitMQ consumer: extract→chunk→embed→store→summarize
│   ├── rag/                        # extract, clean, chunk, store, llm, query, thinking, memory, summarize, status
│   └── config/settings.py          # Central config: environment/retrieval-mode toggles
│
├── tests/
│   ├── conftest.py                 # Shared fixtures (isolated ChromaDB/config per test)
│   ├── unit/                       # Pure-logic tests: chunking, cleaning, metadata, config
│   └── integration/                # Real ChromaDB + real embeddings + FastAPI TestClient
│
├── docs/                           # Real sample HOA documents used for verification
├── ISSUES_AND_FIXES.md             # Running log of every real bug found & fixed, with verification data
├── PLAN.md                         # Original phased implementation plan (historical)
├── PROMPTS.md                      # Development prompt history
└── GETTING_STARTED.md              # Command-reference quickstart
```

---

## 🧪 Testing

69 automated tests (unit + integration) — real ChromaDB, real BGE embeddings, real FastAPI routing; only the outbound LLM network call is mocked.

```bash
pip install -r requirements-dev.txt   # test-only tooling, not in Docker images
pytest tests/ -v
```

See `ISSUES_AND_FIXES.md` #16 for what's covered and a real bug the test suite itself surfaced while being built.

---

## ⚠️ Known Gaps

- **No OCR** — scanned/image-only PDF pages extract as empty text with no error (silent, not a crash). Only born-digital PDFs are supported today. See `ISSUES_AND_FIXES.md` for the reproduction.
- **No automated eval set** — real question/answer quality has been manually verified against real documents (documented throughout `ISSUES_AND_FIXES.md`), but there's no repeatable, labeled success/failure eval suite yet.
- Minor: ~4% of chunks in an exhibit/drawing appendix of one test document leak stray letter-spaced footer text — deliberately not fixed, see `ISSUES_AND_FIXES.md` Won't-Fix #6.

---

## 📖 Further Reading

- **`ISSUES_AND_FIXES.md`** — the actual source of truth for what's been built, tested, and fixed, with real before/after verification data for every entry. Start here if you want to know what actually works.
- **`GETTING_STARTED.md`** — command-reference quickstart and common operations
- **`PLAN.md`** — the original phased plan this project started from
- **`PROMPTS.md`** — development prompt history, from the original Week-1 submission through later phases

---

## 🔗 Useful Links

- [k3d Documentation](https://k3d.io/)
- [RabbitMQ Cluster Operator](https://github.com/rabbitmq/cluster-operator)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [LlamaIndex Documentation](https://docs.llamaindex.ai/)
- [Mem0 Documentation](https://docs.mem0.ai/)

---

**Last Updated:** 2026-08-23
