# Getting Started with HOA Bot

A production-grade Kubernetes async pipeline with RAG chatbot for HOA document Q&A.

## Quick Links

- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** — Directory organization
- **[PLAN.md](PLAN.md)** — 10-phase implementation plan
- **[README.md](README.md)** — Original project overview
- **[k8s/README.md](k8s/README.md)** — Kubernetes deployment guide
- **[docs/](docs/)** — Documentation, samples, benchmarks

## Architecture at a Glance

```
Upload File       Process Messages      Answer Questions
    ↓                   ↓                      ↓
 Web UI      →      Consumer      →       Chatbot
(Flask)           (RabbitMQ)            (FastAPI)
Port 5000         Chunking              Port 8000
              Embedding
              Storage
```

**Data Flow:**
1. User uploads PDF via **Web UI** (port 5000)
2. Message sent to **RabbitMQ** queue
3. **Consumer** processes: extracts text → chunks → embeds → stores
4. User asks questions via **Chatbot** (port 8000)
5. **RAG Pipeline** retrieves relevant chunks → generates answer

**Storage:**
- Local: ChromaDB (free, fast, for development)
- Cloud: Pinecone (optional, for benchmarking)

## Prerequisites

- Docker & k3d (for Kubernetes)
- Python 3.11+
- ~2GB disk space

## 5-Minute Quickstart

```bash
# 1. Create K8s cluster
k3d cluster create HOA-Bot --servers 1 --agents 2

# 2. Setup & build
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

docker build -f docker/web-ui.dockerfile -t web-ui:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
docker build -f docker/chatbot.dockerfile -t chatbot:latest .
k3d image import web-ui:latest consumer:latest chatbot:latest -c HOA-Bot

# 3. Deploy
kubectl create namespace hoa-pipeline
kubectl apply -f k8s/rmq.yaml k8s/pvc.yaml k8s/web-ui-deployment.yaml \
              k8s/consumer-deployment.yaml k8s/chatbot-deployment.yaml

# 4. Access
kubectl -n hoa-pipeline port-forward svc/web-ui-service 5000:5000
kubectl -n hoa-pipeline port-forward svc/chatbot-service 8000:8000

# 5. Use
# Upload: http://localhost:5000
# Chat:   http://localhost:8000
```

## Configuration

Edit toggles via **Chatbot UI** (port 8000):

- **Storage Mode:** Local (ChromaDB) or Hybrid (ChromaDB + Pinecone)
- **Retrieval Mode:** Fast (2-5s) or Thinking (10-30s with corrections)

Centralized config: **[src/config/settings.py](src/config/settings.py)**

## Project Structure

```
docker/              All Docker images
k8s/                 Kubernetes manifests
src/
  ├─ services/       Microservices (web-ui, producer, consumer, chatbot)
  ├─ rag/            RAG pipeline (chunking, embedding, retrieval)
  └─ config/         Configuration management
tests/               Test suite (unit, integration, benchmarks, evals)
docs/
  ├─ samples/        Sample PDFs for testing
  ├─ benchmarks/     Performance results
  └─ architecture/   Design documentation
scripts/             Utility scripts
```

→ See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for full details

## Development Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Docker + Tesseract | Plan ready |
| 2 | Chunking + Embedding | Plan ready |
| 3 | Dual Storage (Local + Cloud) | Plan ready |
| 4 | Sample Data | Plan ready |
| 5 | REST API + Chatbot UI | Plan ready |
| 6 | Test Suite | Planned |
| 7 | Benchmarking Framework | Planned |
| 8 | Run Benchmarks | Planned |
| 9 | Analysis & Report | Planned |
| 10 | Documentation | Planned |

→ See [PLAN.md](PLAN.md) for detailed steps

## Key Services

### Web UI (Port 5000)
- **Purpose:** Upload PDFs
- **Tech:** Flask
- **Code:** [src/services/web_ui/](src/services/web_ui/)

### Consumer (Kubernetes)
- **Purpose:** Process messages, chunk, embed, store
- **Tech:** Python + RabbitMQ
- **Code:** [src/services/consumer/](src/services/consumer/)

### Chatbot (Port 8000)
- **Purpose:** Answer questions with RAG
- **Tech:** FastAPI + HTML/JS
- **Code:** [src/services/chatbot/](src/services/chatbot/)
- **Config Toggles:** Storage & Retrieval mode

### RAG Pipeline
- **Chunking:** Section-aware, semantic chunks
- **Embedding:** BAAI/bge-small-en-v1.5 (384-dim)
- **Storage:** ChromaDB (local) + Pinecone (cloud)
- **Retrieval:** LangGraph with optional corrective loop
- **Code:** [src/rag/](src/rag/)

## Common Commands

```bash
# Build Docker images
docker build -f docker/web-ui.dockerfile -t web-ui:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
docker build -f docker/chatbot.dockerfile -t chatbot:latest .

# Deploy to Kubernetes
kubectl apply -f k8s/

# Check status
kubectl -n hoa-pipeline get pods
kubectl -n hoa-pipeline logs deployment/consumer

# Port forward
kubectl -n hoa-pipeline port-forward svc/web-ui-service 5000:5000
kubectl -n hoa-pipeline port-forward svc/chatbot-service 8000:8000

# Run tests
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/benchmarks/ -v

# Cleanup
kubectl delete namespace hoa-pipeline
k3d cluster delete HOA-Bot
```

## Testing

```bash
# Unit tests (components)
pytest tests/unit/

# Integration tests (workflows)
pytest tests/integration/

# Benchmarks (performance)
pytest tests/benchmarks/

# Evaluation (quality)
pytest tests/evals/

# All tests
pytest tests/ -v
```

## Benchmarking

After Phase 8, compare local vs cloud:

```bash
pytest tests/benchmarks/benchmark_latency.py -v
pytest tests/evals/eval_retrieval.py -v
pytest tests/evals/eval_answer_quality.py -v

# Results in: docs/benchmarks/
```

## Troubleshooting

**Pod not starting?**
```bash
kubectl -n hoa-pipeline describe pod <pod-name>
```

**Connection refused?**
```bash
# Verify port forward is running
lsof -i :5000
lsof -i :8000
```

**RabbitMQ not ready?**
```bash
kubectl -n hoa-pipeline get pods -l app=hoa-rabbitmq
```

**Files not being processed?**
```bash
# Check consumer logs
kubectl -n hoa-pipeline logs deployment/consumer -f
```

## Next Steps

1. **Setup:** Follow "5-Minute Quickstart" above
2. **Explore:** Read [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
3. **Implement:** Follow [PLAN.md](PLAN.md) phases 1-10
4. **Benchmark:** Compare local vs cloud performance
5. **Deploy:** Run in production Kubernetes

## Support

- **Architecture Questions:** → [docs/architecture/](docs/architecture/)
- **API Documentation:** → [docs/api/](docs/api/)
- **Implementation Plan:** → [PLAN.md](PLAN.md)
- **Development Prompts:** → [PROMPTS.md](PROMPTS.md)

---

**Ready to start? Begin with [PLAN.md Phase 1](PLAN.md#phase-1).**
