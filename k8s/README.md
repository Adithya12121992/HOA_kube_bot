# Kubernetes Deployment Manifests

All Kubernetes configurations for the HOA Bot system.

## Files

- **`rmq.yaml`** — RabbitMQ cluster operator and instance
- **`pvc.yaml`** — Persistent volume claim (shared storage for documents)
- **`web-ui-deployment.yaml`** — Web UI service (file upload)
- **`consumer-deployment.yaml`** — Consumer service (message processor)
- **`chatbot-deployment.yaml`** — Chatbot service (REST API + HTML interface) [Phase 5]

## Deployment Order

```bash
# 1. Create namespace
kubectl create namespace hoa-pipeline

# 2. Install cert-manager (required for RabbitMQ)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl -n cert-manager get pods  # Wait for Ready

# 3. Install RabbitMQ Cluster Operator
kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
kubectl -n rabbitmq-system get pods  # Wait for Ready

# 4. Create RabbitMQ instance
kubectl apply -f k8s/rmq.yaml
kubectl -n hoa-pipeline get pods -l app=hoa-rabbitmq  # Wait for hoa-rabbitmq-server-0 Ready

# 5. Create persistent volume claim
kubectl apply -f k8s/pvc.yaml
kubectl -n hoa-pipeline get pvc  # Verify bound

# 6. Build and import Docker images
docker build -f docker/web-ui.dockerfile -t web-ui:latest .
docker build -f docker/consumer.dockerfile -t consumer:latest .
docker build -f docker/chatbot.dockerfile -t chatbot:latest .
k3d image import web-ui:latest consumer:latest chatbot:latest -c HOA-Bot

# 7. Deploy services
kubectl apply -f k8s/web-ui-deployment.yaml
kubectl apply -f k8s/consumer-deployment.yaml
kubectl apply -f k8s/chatbot-deployment.yaml

# 8. Verify all pods running
kubectl -n hoa-pipeline get pods
```

## Port Forwarding

```bash
# Web UI (file upload)
kubectl -n hoa-pipeline port-forward svc/web-ui-service 5000:5000
# Access: http://localhost:5000

# Chatbot (REST API + HTML)
kubectl -n hoa-pipeline port-forward svc/chatbot-service 8000:8000
# Access: http://localhost:8000

# RabbitMQ Management
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 15672:15672
# Access: http://localhost:15672

# RabbitMQ AMQP (for local consumer)
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 5672:5672
```

## Environment Variables

Services read config from environment variables:

| Variable | Service | Purpose |
|----------|---------|---------|
| `RABBITMQ_HOST` | web-ui, consumer | RabbitMQ host |
| `RABBITMQ_PORT` | web-ui, consumer | RabbitMQ port |
| `RABBITMQ_USER` | web-ui, consumer | RabbitMQ username (from K8s secret) |
| `RABBITMQ_PASSWORD` | web-ui, consumer | RabbitMQ password (from K8s secret) |
| `STORAGE_MODE` | chatbot | Storage backend: "local" or "hybrid" |
| `RETRIEVAL_MODE` | chatbot | Retrieval strategy: "fast" or "thinking" |
| `PINECONE_API_KEY` | consumer, chatbot | Pinecone API key (if hybrid mode) |
| `LOG_LEVEL` | all | Logging level: "INFO", "DEBUG", etc |

## Cleanup

```bash
# Delete all deployments
kubectl delete deployment web-ui consumer chatbot -n hoa-pipeline

# Delete PVC
kubectl delete pvc producer-consumer-pvc -n hoa-pipeline

# Delete namespace
kubectl delete namespace hoa-pipeline
```

## Troubleshooting

```bash
# Check pod status
kubectl -n hoa-pipeline get pods
kubectl -n hoa-pipeline describe pod <pod-name>

# View logs
kubectl -n hoa-pipeline logs deployment/web-ui
kubectl -n hoa-pipeline logs deployment/consumer
kubectl -n hoa-pipeline logs deployment/chatbot

# Check PVC
kubectl -n hoa-pipeline get pvc
kubectl -n hoa-pipeline get pv

# Check RabbitMQ
kubectl -n hoa-pipeline exec hoa-rabbitmq-0 -- rabbitmqctl list_queues
```
