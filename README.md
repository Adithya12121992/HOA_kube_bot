# HOA Bot — Kubernetes Async Pipeline with RabbitMQ

A complete Kubernetes-based async pipeline for processing HOA documents. Upload files via web UI → Queue messages in RabbitMQ → Process concurrently → Feed into RAG chatbot.

---

## 📋 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    k3d Cluster (HOA-Bot)                            │
│              1 Control Plane + 2 Agent Nodes                        │
│                                                                     │
│  ┌──────────────────────── hoa-pipeline namespace ──────────────┐  │
│  │                                                              │  │
│  │  ┌──────────────┐      ┌──────────────┐                    │  │
│  │  │   Web UI     │      │  RabbitMQ    │                    │  │
│  │  │  (Flask)     │      │  Broker      │                    │  │
│  │  │  :5000       │      │  (1 replica) │                    │  │
│  │  └──────┬───────┘      └──────┬───────┘                    │  │
│  │         │                     │                            │  │
│  │         └─────────────────────┼──────────────┐            │  │
│  │                               │              │            │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │         PVC: producer-consumer-pvc (250MB)         │  │  │
│  │  │     (Stores uploaded documents temporarily)        │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │         ▲                     ▲              ▼             │  │
│  │         │                     │              │             │  │
│  │    Upload files       Produces messages  Consumes &     │  │
│  │                                           Deletes files  │  │
│  │  ┌──────────────┐                  ┌──────────────┐      │  │
│  │  │  Producer    │                  │  Consumer    │      │  │
│  │  │  (Optional)  │                  │  (Max 3      │      │  │
│  │  │              │                  │   threads)   │      │  │
│  │  └──────────────┘                  └──────────────┘      │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────── rabbitmq-system namespace ────────────┐  │
│  │  RabbitMQ Cluster Operator                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────── cert-manager namespace ────────────────┐  │
│  │  TLS Certificates for Operator Webhooks                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Docker
- k3d (`k3d --version`)
- kubectl (`kubectl version`)
- Python 3.11+

### 2. Create Kubernetes Cluster

```bash
k3d cluster create HOA-Bot --servers 1 --agents 2
kubectl get nodes  # Verify 3 nodes Ready
```

### 3. Install Infrastructure

```bash
# Create namespace
kubectl create namespace hoa-pipeline

# Install cert-manager (for RabbitMQ Operator TLS)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl -n cert-manager get pods  # Wait for Ready

# Install RabbitMQ Cluster Operator
kubectl apply -f "https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"
kubectl -n rabbitmq-system get pods  # Wait for Ready

# Create RabbitMQ instance
kubectl apply -f rmq.yaml  # Or your RabbitMQ manifest
kubectl -n hoa-pipeline get pods  # Wait for hoa-rabbitmq-server-0 Ready

# Create PVC for file storage
kubectl apply -f producer_consumer_PVC.yaml
```

### 4. Deploy Applications

```bash
# Build and import Docker images
docker build -f Web_UI_dockerfile -t web-ui:latest .
docker build -f Consumer_dockerfile -t consumer:latest .
k3d image import web-ui:latest consumer:latest -c HOA-Bot

# Deploy to Kubernetes
kubectl apply -f web-ui-deployment.yaml
kubectl apply -f consumer-deployment.yaml

# Verify deployments
kubectl -n hoa-pipeline get pods
```

### 5. Access Applications

**Web UI (File Upload):**
```bash
# Port-forward to web UI
kubectl -n hoa-pipeline port-forward svc/web-ui-service 5000:5000

# Open browser
# http://localhost:5000
```

**RabbitMQ Management:**
```bash
# Port-forward to management UI
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 15672:15672

# Get credentials
RABBITMQ_USER=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.username}" | base64 -d)
RABBITMQ_PASSWORD=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.password}" | base64 -d)

# Open browser
# http://localhost:15672
# Login with credentials above
```

---

## 📁 Project Structure

```
Kube_HOA_bot/
├── venv/                           # Python virtual environment
├── requirements.txt                # Python dependencies
│
├── Web Components
├── web_ui.py                       # Flask file upload app
├── templates/
│   └── index.html                  # Web UI with drag-drop
├── Web_UI_dockerfile               # Web UI container image
├── web-ui-deployment.yaml          # Web UI K8s deployment + service
│
├── Producer (Test Messages)
├── producer.py                     # Test message producer
├── Producer_dockerfile             # Producer container image
├── producer-deployment.yaml        # Producer K8s deployment (optional)
│
├── Consumer (Message Processor)
├── consumer.py                     # Concurrent message consumer
├── Consumer_dockerfile             # Consumer container image
├── consumer-deployment.yaml        # Consumer K8s deployment
│
├── Infrastructure
├── rmq.yaml                        # RabbitMQ cluster definition
├── producer_consumer_PVC.yaml      # Persistent volume for file storage
│
├── RAG Pipeline (Document Processing)
├── src/
│   ├── chunk.py                    # Hybrid document chunking
│   ├── pipeline.py                 # Pipeline orchestrator
│   ├── store.py                    # Vector DB storage
│   └── rag_graph.py                # RAG graph for Q&A
├── app.py                          # Streamlit chat interface
│
├── Documentation
├── README.md                       # This file
└── PROMPTS.md                      # Top 5 development prompts
```

---

## 🔧 Component Details

### Web UI (web_ui.py)

**Purpose:** Upload files and produce RabbitMQ messages

**Features:**
- ✅ Drag-and-drop multi-file upload
- ✅ File size validation (100MB max)
- ✅ Automatic UUID doc_id generation
- ✅ Save to PVC (/data)
- ✅ Produce message with file metadata
- ✅ Real-time upload progress
- ✅ Source citations and timestamps

**Access:**
```bash
kubectl -n hoa-pipeline port-forward svc/web-ui-service 5000:5000
# http://localhost:5000
```

**Message Format:**
```json
{
  "doc_id": "a1b2c3d4-e5f6-4890-a1b2-c3d4e5f67890",
  "original_filename": "CC&Rs.pdf",
  "file_path": "/data/a1b2c3d4-e5f6-4890-a1b2-c3d4e5f67890_CC&Rs.pdf",
  "uploaded_at": "2026-08-15T10:30:45.123456Z"
}
```

---

### Consumer (consumer.py)

**Purpose:** Process messages from RabbitMQ queue with file deletion

**Features:**
- ✅ Concurrent processing (max 3 threads via ThreadPoolExecutor)
- ✅ prefetch_count=3 tells RabbitMQ to send 3 messages max
- ✅ Non-blocking — as soon as one finishes, next one starts
- ✅ Extracts file_path from message
- ✅ Deletes file from PVC after processing
- ✅ Thread-safe channel operations with locks
- ✅ Auto-reconnection on connection loss (5 retries)

**Logs:**
```bash
kubectl -n hoa-pipeline logs -f deployment/consumer

# Example output:
# 📊 Current messages in queue 'test_queue': 5
# 🎧 Concurrent Consumer Active
# 📨 Message 1 received, queued for processing
# ⏳ [Thread-0] Processing message 1...
# 🗑️  Deleted file: /data/xxxxx.pdf
# ✓ [Thread-0] Message 1 processed successfully
```

**Processing Flow:**
```
Message received from queue
    ↓
Extract file_path from JSON
    ↓
Submit to thread pool
    ↓
[In background thread]
    - [TODO] Add your processing logic here
    - Delete file from PVC
    - Acknowledge message (mark as read)
    ↓
[Main thread] Gets next message from queue
```

---

### RabbitMQ Cluster

**Setup:**
```bash
kubectl apply -f rmq.yaml
```

**Get Credentials:**
```bash
RABBITMQ_USER=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.username}" | base64 -d)
RABBITMQ_PASSWORD=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.password}" | base64 -d)

echo "User: $RABBITMQ_USER"
echo "Password: $RABBITMQ_PASSWORD"
```

**Connection Details:**
- **Inside cluster:** `amqp://hoa-rabbitmq:5672`
- **From localhost:** `amqp://localhost:5672` (with port-forward)
- **Management UI:** `http://localhost:15672` (port-forward 15672)

**Queue:** `test_queue` (durable, auto-created)

---

### PVC (Persistent Storage)

**Spec:**
- Size: 250MB
- Type: local-path (k3d default)
- Mount: `/data`
- Accessible by: web-ui, producer, consumer pods

**Create:**
```bash
kubectl apply -f producer_consumer_PVC.yaml
```

**Verify:**
```bash
kubectl -n hoa-pipeline get pvc
kubectl -n hoa-pipeline get pv
```

**Access from Pod:**
```bash
kubectl -n hoa-pipeline exec -it <pod-name> -- ls -la /data/
```

---

## 🧪 Local Development

### Setup Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### Run Consumer Locally

```bash
# Start port-forward (in another terminal)
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 5672:5672

# Run consumer
python consumer.py

# Expected output:
# 📊 Current messages in queue 'test_queue': 3
# 🎧 Concurrent Consumer Active
# ⚙️  Max concurrent messages: 3
# (waits for messages...)
```

### Upload Files & Test

```bash
# In browser:
# http://localhost:5000

# Upload PDFs → they appear in RabbitMQ queue
# Consumer processes them → files deleted from PVC
```

---

## 📊 Message Flow Example

```
1. User uploads "CC&Rs.pdf" via web UI
   └─ Saved to: /data/{uuid}_CC&Rs.pdf

2. Message produced to RabbitMQ:
   {
     "doc_id": "a1b2c3d4-e5f6-4890-a1b2-c3d4e5f67890",
     "original_filename": "CC&Rs.pdf",
     "file_path": "/data/a1b2c3d4-e5f6-4890-a1b2-c3d4e5f67890_CC&Rs.pdf",
     "uploaded_at": "2026-08-15T10:30:45.123456Z"
   }

3. Consumer picks up message (max 3 concurrent)
   └─ Opens /data/a1b2c3d4.../CC&Rs.pdf
   └─ [TODO] Process file (extract text, chunk, embed, etc.)
   └─ Delete /data/a1b2c3d4.../CC&Rs.pdf
   └─ Mark message as read in RabbitMQ

4. Next message is picked up automatically
```

---

## 🔍 Debugging Commands

### Check Cluster Status

```bash
# Cluster info
kubectl cluster-info
kubectl get nodes

# Namespace info
kubectl get namespace
kubectl -n hoa-pipeline get all

# Pods
kubectl -n hoa-pipeline get pods
kubectl -n hoa-pipeline describe pod <pod-name>
kubectl -n hoa-pipeline logs <pod-name>
```

### RabbitMQ Debugging

```bash
# Check RabbitMQ pod
kubectl -n hoa-pipeline get pods -l app=hoa-rabbitmq

# Get credentials
kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o yaml

# Access management CLI
kubectl -n hoa-pipeline exec hoa-rabbitmq-0 -- rabbitmqctl list_queues
kubectl -n hoa-pipeline exec hoa-rabbitmq-0 -- rabbitmqctl list_connections
```

### Consumer Debugging

```bash
# Watch logs in real-time
kubectl -n hoa-pipeline logs -f deployment/consumer

# Check if consuming (should show prefetch_count=3)
kubectl -n hoa-pipeline exec deployment/consumer -- python consumer.py

# Check files in PVC
kubectl -n hoa-pipeline exec deployment/consumer -- ls -la /data/
```

### Port-Forward Status

```bash
# List active port-forwards
lsof -i :5000  # Web UI
lsof -i :5672  # RabbitMQ AMQP
lsof -i :15672 # RabbitMQ Management
```

---

## ⚠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| **Pod not starting** | `kubectl -n hoa-pipeline describe pod <name>` — check Events section |
| **Connection refused** | Check port-forward is running: `lsof -i :<port>` |
| **Queue not receiving messages** | Verify web-ui pod is running: `kubectl -n hoa-pipeline logs deployment/web-ui` |
| **Consumer not processing** | Check consumer logs: `kubectl -n hoa-pipeline logs -f deployment/consumer` |
| **File not deleted** | Check PVC mount: `kubectl -n hoa-pipeline exec deployment/consumer -- ls -la /data/` |
| **RabbitMQ pod stuck** | Delete and recreate: `kubectl delete pod hoa-rabbitmq-0 -n hoa-pipeline` |

---

## 🧠 RAG Pipeline (bonus)

The system includes a complete RAG (Retrieval-Augmented Generation) pipeline:

1. **chunk.py** — Breaks documents into 3200-char chunks with section metadata
2. **store.py** — Embeds chunks using BGE model → stores in ChromaDB
3. **pipeline.py** — Orchestrates all stages
4. **app.py** — Streamlit chat interface for Q&A

**Usage:**
```bash
# Requires LM Studio running locally (or update for other LLM provider)
streamlit run app.py

# Ask questions like: "What are the Board's powers?"
# Returns: Answer + source citations + retrieval trace + images
```

---

## 📦 Dependencies

**Python:**
- pika==1.3.2 (RabbitMQ client)
- Flask==3.0.0 (Web framework)
- Werkzeug==3.0.1 (WSGI utilities)

**Kubernetes:**
- k3d (local K8s)
- cert-manager (TLS)
- RabbitMQ Cluster Operator

**Docker:**
- python:3.11-alpine (base image)

---

## 🤝 Development

See [PROMPTS.md](PROMPTS.md) for the top 5 development prompts that shaped this system.

---

## 📄 License

Open source — feel free to modify and extend.

---

## 🔗 Useful Links

- [k3d Documentation](https://k3d.io/)
- [RabbitMQ Cluster Operator](https://github.com/rabbitmq/cluster-operator)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [ChromaDB Documentation](https://docs.trychroma.com/)

---

**Last Updated:** 2026-08-15  
**Status:** ✅ Production Ready
