# Kubernetes Deployment Manifests

All Kubernetes configurations for the HOA Bot system.

## Files

- **`rmq.yaml`** — RabbitMQ cluster operator and instance
- **`pvc.yaml`** — Persistent volume claim (`producer-consumer-pvc`) — shared storage for uploaded files, ChromaDB, the config toggle, and per-document status
- **`hoa-bot-deployment.yaml`** — hoa-bot pod + service (FastAPI: upload UI + chat UI + REST API, port 8000)
- **`consumer-deployment.yaml`** — consumer pod (background document-processing worker, no exposed port)
- **`hoa-bot-ingress.yaml`** — stable Ingress-based access via k3d's Traefik, replacing `kubectl port-forward` (see below)

There is no separate `web-ui` deployment — `hoa-bot` serves both the upload UI and the chat UI from one FastAPI service.

## Deployment Order

```bash
# 1. Create namespace
kubectl create namespace hoa-pipeline

# 2. Install cert-manager (required for RabbitMQ Operator webhooks)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl -n cert-manager get pods  # wait for Ready

# 3. Install RabbitMQ Cluster Operator
kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
kubectl -n rabbitmq-system get pods  # wait for Ready

# 4. Create RabbitMQ instance
kubectl apply -f k8s/rmq.yaml
kubectl -n hoa-pipeline get pods -l app=hoa-rabbitmq  # wait for hoa-rabbitmq-server-0 Ready

# 5. Create persistent volume claim
kubectl apply -f k8s/pvc.yaml
kubectl -n hoa-pipeline get pvc  # verify bound

# 6. Build and import Docker images
docker build -f docker/hoa-bot.dockerfile -t hoa-bot:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
k3d image import hoa-bot:latest consumer:latest -c HOA-Bot

# 7. Deploy services
kubectl apply -f k8s/consumer-deployment.yaml
kubectl apply -f k8s/hoa-bot-deployment.yaml

# 8. Verify all pods running
kubectl -n hoa-pipeline get pods

# 9. Set up stable access
k3d cluster edit HOA-Bot --port-add 8000:80@loadbalancer   # one-time per cluster
kubectl apply -f k8s/hoa-bot-ingress.yaml
```

## Access

**hoa-bot (upload UI + chat UI + REST API) — recommended path, via Ingress:**
```bash
# One-time cluster setup (see step 9 above), then just:
# http://localhost:8000
```

Why Ingress instead of `kubectl port-forward`: port-forward's tunnel has an idle/stream timeout shorter than a local reasoning model's response time (confirmed: a real request was cut off at exactly 60s, "connection reset by peer"). The Ingress path goes through k3d's real Docker port-publish instead of a client-side `kubectl` process, so it survives pod restarts/redeploys with zero manual steps — verified by triggering a rollout restart and confirming `http://localhost:8000/health` kept working immediately after.

**hoa-bot — fallback via port-forward (if you haven't set up the Ingress):**
```bash
kubectl -n hoa-pipeline port-forward svc/hoa-bot-service 8000:8000
```

**RabbitMQ Management UI:**
```bash
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 15672:15672
# http://localhost:15672

RABBITMQ_USER=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.username}" | base64 -d)
RABBITMQ_PASSWORD=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.password}" | base64 -d)
```

**RabbitMQ AMQP (for running consumer locally against the cluster's queue):**
```bash
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 5672:5672
```

## Environment Variables

Both `hoa-bot` and `consumer` read the same set (they must match — both write/read the same shared store):

| Variable | Purpose | Required |
|----------|---------|----------|
| `ENVIRONMENT` | `"local"` or `"cloud"` — full bundled stack toggle | Default `"local"` |
| `RETRIEVAL_MODE` | `"fast"` or `"thinking"` (hoa-bot only) | Default `"fast"` |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` / `RABBITMQ_QUEUE` | RabbitMQ connection | Yes |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | From `hoa-rabbitmq-default-user` secret | Yes |
| `CHROMA_DB_PATH` | On-disk ChromaDB path (PVC-backed) | Yes |
| `DATA_DIR` | Shared PVC root (uploads, config.json, status/) | Yes |
| `LM_STUDIO_BASE_URL` / `LM_STUDIO_MODEL` | Local LLM (only used when `ENVIRONMENT=local`) | For local |
| `LM_STUDIO_API_KEY` | From `lmstudio-secret`, optional | Optional |
| `PINECONE_API_KEY` | From `pinecone-secret`, optional — enables the cloud vector store (and dual-write even in local mode) | For cloud |
| `ANTHROPIC_API_KEY` | From `llm-secret`, optional — cloud LLM | For cloud |
| `OPENAI_API_KEY` | From `llm-secret`, optional — declared as a cloud LLM fallback, but this project deliberately sticks to Anthropic-only (see `ISSUES_AND_FIXES.md`) | Optional |
| `MEM0_API_KEY` | From `mem0-secret`, optional — cloud conversation memory | For cloud |
| `LOG_LEVEL` | Logging level | Optional, default `INFO` |

`LM_STUDIO_BASE_URL` points at `http://host.k3d.internal:1234/v1` by default — LM Studio runs on the host machine, not inside the cluster, and this hostname is how k3d pods reach it.

## Cleanup

```bash
# Delete deployments
kubectl delete deployment hoa-bot consumer -n hoa-pipeline

# Delete Ingress
kubectl delete -f k8s/hoa-bot-ingress.yaml

# Delete PVC
kubectl delete pvc producer-consumer-pvc -n hoa-pipeline

# Delete namespace (everything in it)
kubectl delete namespace hoa-pipeline

# Full cluster teardown
k3d cluster delete HOA-Bot
```

## Troubleshooting

```bash
# Check pod status
kubectl -n hoa-pipeline get pods
kubectl -n hoa-pipeline describe pod <pod-name>

# View logs
kubectl -n hoa-pipeline logs -f deployment/hoa-bot
kubectl -n hoa-pipeline logs -f deployment/consumer

# Check PVC
kubectl -n hoa-pipeline get pvc
kubectl -n hoa-pipeline get pv

# Check RabbitMQ
kubectl -n hoa-pipeline exec hoa-rabbitmq-server-0 -- rabbitmqctl list_queues

# Redeploy after a code change (rebuild → reimport → restart)
docker build -f docker/hoa-bot.dockerfile -t hoa-bot:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
k3d image import hoa-bot:latest consumer:latest -c HOA-Bot
kubectl rollout restart deployment/hoa-bot deployment/consumer -n hoa-pipeline
```

**Uploaded a document but /ask can't find it, even though the upload succeeded?** This was a real bug — ChromaDB writes from `consumer` were invisible to `hoa-bot`'s already-running process until `hoa-bot` restarted (root cause: chromadb's own internal `SharedSystemClient` process-level cache, not this project's code). Fixed — see `ISSUES_AND_FIXES.md` #17. If you're running an image built before that fix, `kubectl rollout restart deployment/hoa-bot -n hoa-pipeline` is the workaround.
