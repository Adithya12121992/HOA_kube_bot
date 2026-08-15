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

