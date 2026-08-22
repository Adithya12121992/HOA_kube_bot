"""
HOA Bot - FastAPI Service
Unified interface for chatbot (Q&A) and file upload (admin)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import json
from datetime import datetime, timezone
import uuid
import pika

from src.config.settings import (
    get_config_dict, update_config,
    RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD,
    RABBITMQ_QUEUE, DATA_DIR
)
from src.rag.query import answer_question
from src.rag.status import read_status

app = FastAPI(title="HOA Bot", version="1.0.0")


# ============================================================================
# DATA MODELS
# ============================================================================

class ConfigUpdate(BaseModel):
    environment: Optional[str] = None
    retrieval_mode: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    user_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: list
    config_used: dict
    metadata: dict


class UploadResponse(BaseModel):
    status: str
    doc_id: str
    filename: str
    file_path: str
    uploaded_at: str


# ============================================================================
# ENDPOINTS - CHAT
# ============================================================================

@app.get("/")
async def serve_ui():
    """Serve the unified HTML interface (chat + upload tabs)"""
    return FileResponse("src/services/chatbot/static/index.html")


@app.get("/config")
async def get_config():
    """Get current configuration"""
    return get_config_dict()


@app.post("/config")
async def update_config_endpoint(config: ConfigUpdate):
    """Update configuration toggles"""
    new_config = update_config(
        environment=config.environment,
        retrieval_mode=config.retrieval_mode,
    )
    return {"status": "updated", "config": new_config}


@app.post("/ask")
async def ask_question(request: AskRequest) -> AskResponse:
    """
    Answer a question using RAG (fast mode — retrieve top-k, generate with citations).

    "Thinking" mode (retrieve -> grade -> rewrite -> generate) is not wired
    up yet — see src/rag/rag_graph.py's module docstring. RETRIEVAL_MODE is
    currently a no-op; both modes run fast-mode until that's built.
    """
    result = answer_question(request.question)

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        config_used=get_config_dict(),
        metadata=result["metadata"],
    )


# ============================================================================
# ENDPOINTS - FILE UPLOAD (Admin)
# ============================================================================

@app.post("/admin/upload")
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    """
    Upload a PDF file and queue it for processing

    Admin endpoint - processes file and sends message to RabbitMQ queue
    for consumer to process (chunk, embed, store)
    """
    try:
        # Ensure data directory exists
        os.makedirs(DATA_DIR, exist_ok=True)

        # Generate doc_id and file path
        doc_id = str(uuid.uuid4())
        filename = file.filename or "document.pdf"
        file_path = os.path.join(DATA_DIR, f"{doc_id}_{filename}")

        # Save file to disk
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Create RabbitMQ message
        timestamp = datetime.now(timezone.utc).isoformat()
        message = {
            "doc_id": doc_id,
            "original_filename": filename,
            "file_path": file_path,
            "uploaded_at": timestamp,
        }

        # Send to RabbitMQ queue
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    port=RABBITMQ_PORT,
                    credentials=credentials,
                    connection_attempts=3,
                    retry_delay=2,
                )
            )
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=RABBITMQ_QUEUE,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2),
            )
            connection.close()
        except Exception as e:
            # File saved but queue failed - still return success (file is persisted)
            print(f"⚠️  RabbitMQ error: {e}, but file saved to {file_path}")

        return UploadResponse(
            status="success",
            doc_id=doc_id,
            filename=filename,
            file_path=file_path,
            uploaded_at=timestamp,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/status/{doc_id}")
async def get_status(doc_id: str):
    """Poll processing status for an uploaded document (Step 2.5 design)."""
    status = read_status(doc_id)
    if status is None:
        # Not an error — the upload was accepted but the consumer hasn't
        # started processing it yet (race: message still in queue).
        raise HTTPException(status_code=404, detail="Status not found yet — processing may not have started")
    return status


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "config": get_config_dict(),
    }


# ============================================================================
# STATIC FILES
# ============================================================================

# Serve static files (CSS, JS embedded in HTML)
try:
    app.mount("/static", StaticFiles(directory="src/services/chatbot/static"), name="static")
except Exception:
    # Directory may not exist yet
    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
