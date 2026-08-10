# RabbitMQ on Kubernetes (k3d) — HOA Bot Pipeline

This guide documents the complete setup of RabbitMQ on a k3d Kubernetes cluster and provides tools to produce messages for the pipeline.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│           k3d Cluster (HOA-Bot)                         │
│  ┌─ Control Plane (Server)                             │
│  ├─ Agent Node 1                                        │
│  └─ Agent Node 2                                        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Namespace: hoa-pipeline                          │  │
│  │ ┌────────────────────────────────────────────┐   │  │
│  │ │ RabbitMQ StatefulSet (1 replica)           │   │  │
│  │ │ Service: hoa-rabbitmq (ClusterIP)         │   │  │
│  │ │ PVC: hoa-rabbitmq-data (local-path)       │   │  │
│  │ │ Secret: hoa-rabbitmq-default-user         │   │  │
│  │ └────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Namespace: rabbitmq-system                       │  │
│  │ └─ RabbitMQ Cluster Operator Pod               │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Namespace: cert-manager                          │  │
│  │ └─ cert-manager for Operator TLS Certs         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Installation Steps

### 1. Create k3d Cluster

```bash
k3d cluster create HOA-Bot --servers 1 --agents 2
```

**What this does:**
- Creates a 3-node Kubernetes cluster using k3s (Lightweight Kubernetes)
- 1 control-plane (server) + 2 agent nodes
- Runs as Docker containers on your machine
- Perfect for development and testing

**Verify:**
```bash
kubectl get nodes
```

Expected output: All 3 nodes should be `Ready`

### 2. Create Project Namespace

```bash
kubectl create namespace hoa-pipeline
```

This isolates your project resources from the default Kubernetes namespace.

**Verify:**
```bash
kubectl get namespaces
```

---

### 3. Install cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
```

**Why:** The RabbitMQ Cluster Operator's webhook requires TLS certificates. cert-manager automates certificate generation and renewal.

**Verify:**
```bash
kubectl -n cert-manager get pods
```

Expected: Three pods should be running:
- `cert-manager-*` (main controller)
- `cert-manager-cainjector-*` (injects CA bundles)
- `cert-manager-webhook-*` (validates cert resources)

---

### 4. Install RabbitMQ Cluster Operator

```bash
kubectl apply -f "https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"
```

**What this does:**
- Installs the official RabbitMQ Cluster Operator
- Registers the `RabbitmqCluster` CRD (Custom Resource Definition)
- Enables declarative RabbitMQ cluster management via Kubernetes YAML

**Verify:**
```bash
kubectl -n rabbitmq-system get pods
kubectl -n rabbitmq-system get certificate
```

Expected: Both certificates should be READY: True

---

### 5. Deploy RabbitMQ Instance

Create a file `rabbitmq-cluster.yaml`:

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: hoa-rabbitmq
  namespace: hoa-pipeline
spec:
  replicas: 1
```

Apply it:
```bash
kubectl apply -f rabbitmq-cluster.yaml
```

**What this does:**
- Creates a RabbitMQ cluster with 1 replica
- Operator provisions:
  - StatefulSet (manages RabbitMQ pod)
  - Service (ClusterIP for DNS-based access)
  - PersistentVolumeClaim (data persistence)
  - Secret with auto-generated credentials

**Verify:**
```bash
kubectl -n hoa-pipeline get pods
kubectl -n hoa-pipeline get pvc
kubectl -n hoa-pipeline get svc
kubectl -n hoa-pipeline get secret
```

---

## Accessing RabbitMQ

### Get Credentials

```bash
# Extract auto-generated password
PASSWORD=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.password}" | base64 -d)
echo "Password: $PASSWORD"

# Get username (auto-generated, stored in the secret)
USERNAME=$(kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user -o jsonpath="{.data.username}" | base64 -d)
echo "Username: $USERNAME"
```

**About the username:** RabbitMQ Cluster Operator auto-generates usernames to avoid conflicts. The format is typically `default_user_<random-string>`. It's stored in the Secret `hoa-rabbitmq-default-user` under the `username` key.

### Port-Forward to Management UI

```bash
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 15672:15672
```

Then open http://localhost:15672 in your browser and log in with the credentials above.

### Port-Forward for AMQP (Producer/Consumer)

```bash
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 5672:5672
```

This exposes the AMQP port (default RabbitMQ protocol) for your applications.

---

## Using the RabbitMQ Producer

### Setup

1. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure port-forwarding is active:**
   ```bash
   kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 5672:5672
   ```
   (Run in a separate terminal or background)

### Run Producer

```bash
python producer.py
```

**Example output:**
```
✓ Message published: {
  "doc_id": "a1b2c3d4-e5f6-4890-a1b2-c3d4e5f67890",
  "original_filename": "CC&Rs_1.pdf",
  "file_path": "/tmp/CC&Rs_1.pdf",
  "uploaded_at": "2026-08-04T10:00:00Z"
}
✓ Message published: { ... }
✓ Message published: { ... }
```

### Message Schema

Each message contains:

| Field | Description | Example |
|-------|-------------|---------|
| `doc_id` | Unique identifier (UUID4) | `a1b2c3d4-e5f6-4890-a1b2-c3d4e5f67890` |
| `original_filename` | PDF filename (incremental for testing) | `CC&Rs_1.pdf` |
| `file_path` | Path to file (uses /tmp for now) | `/tmp/CC&Rs_1.pdf` |
| `uploaded_at` | ISO 8601 timestamp (UTC) | `2026-08-04T10:00:00Z` |

---

## Useful Commands

### Monitor RabbitMQ Logs

```bash
kubectl -n hoa-pipeline logs -f svc/hoa-rabbitmq
```

### Check Queue Status via CLI

```bash
# Forward management port
kubectl -n hoa-pipeline port-forward svc/hoa-rabbitmq 15672:15672

# Then use curl or visit UI at http://localhost:15672
curl -u <USERNAME>:<PASSWORD> http://localhost:15672/api/queues
```

### List All Queues

```bash
kubectl -n hoa-pipeline exec hoa-rabbitmq-0 -- rabbitmqctl list_queues
```

### Delete and Recreate RabbitMQ Cluster

```bash
kubectl delete -f rabbitmq-cluster.yaml
kubectl apply -f rabbitmq-cluster.yaml
```

### Clean Up Entire Setup

```bash
k3d cluster delete HOA-Bot
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Producer can't connect** | 1. Verify port-forward is active: `lsof -i :5672`<br>2. Check credentials: `kubectl -n hoa-pipeline get secret hoa-rabbitmq-default-user`<br>3. Verify pod is running: `kubectl -n hoa-pipeline get pods` |
| **Management UI won't load** | 1. Verify port-forward: `lsof -i :15672`<br>2. Check pod logs: `kubectl -n hoa-pipeline logs svc/hoa-rabbitmq`<br>3. Ensure RabbitMQ management plugin is enabled |
| **Operator pod not running** | Check cert-manager: `kubectl -n cert-manager get pods`<br>View operator logs: `kubectl -n rabbitmq-system logs -l app.kubernetes.io/name=rabbitmq-operator` |
| **PVC not binding** | Verify storage class: `kubectl get storageclass`<br>k3d uses `local-path` by default |

---

## Dependencies

- **Kubernetes 1.20+** (k3s handles this)
- **Docker** (to run k3d containers)
- **kubectl** (to interact with cluster)
- **Python 3.7+** (for producer code)
- **pika** (Python RabbitMQ client)

---

## Project Structure

```
Kube_HOA_bot/
├── venv/                      # Virtual environment
├── requirements.txt           # Python dependencies
├── producer.py               # RabbitMQ message producer
├── rabbitmq-cluster.yaml     # RabbitMQ cluster definition
└── README.md                 # This file
```

---

## Next Steps

1. **Create a consumer** to process messages from `test_queue`
2. **Add persistence** by increasing RabbitMQ replicas for HA
3. **Configure queue policies** for TTL, max-length, etc.
4. **Set up monitoring** with Prometheus/Grafana
5. **Scale the cluster** by adding more worker nodes

---

## References

- [k3d Documentation](https://k3d.io/)
- [RabbitMQ Cluster Operator](https://github.com/rabbitmq/cluster-operator)
- [cert-manager Documentation](https://cert-manager.io/)
- [Python pika Library](https://pika.readthedocs.io/)
- [RabbitMQ Management API](https://www.rabbitmq.com/management.html)
