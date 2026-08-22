"""
FastAPI Chatbot Service
REST API with HTML/JS frontend for RAG question-answering
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import time

from src.config.settings import STORAGE_MODE, RETRIEVAL_MODE, get_config_dict, update_config

app = FastAPI(title="HOA Bot Chatbot", version="1.0.0")


# ============================================================================
# DATA MODELS
# ============================================================================

class ConfigUpdate(BaseModel):
    storage_mode: Optional[str] = None
    retrieval_mode: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    user_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: list
    config_used: dict
    metadata: dict


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def serve_ui():
    """Serve the chatbot HTML interface"""
    return FileResponse("src/services/chatbot/static/index.html")


@app.get("/config")
async def get_config():
    """Get current configuration"""
    return get_config_dict()


@app.post("/config")
async def update_config_endpoint(config: ConfigUpdate):
    """Update configuration toggles"""
    new_config = update_config(
        storage_mode=config.storage_mode,
        retrieval_mode=config.retrieval_mode,
    )
    return {"status": "updated", "config": new_config}


@app.post("/ask")
async def ask_question(request: AskRequest) -> AskResponse:
    """
    Answer a question using RAG

    Flow:
    1. Load current config
    2. Instantiate RAG engine
    3. Run retrieve → [grade → rewrite if thinking] → generate
    4. Return answer + sources + metadata
    """
    start_time = time.time()

    # TODO: Import RAG engine and run pipeline
    # from src.rag.pipeline import RAGEngine
    # rag = RAGEngine(
    #     storage_mode=STORAGE_MODE,
    #     retrieval_mode=RETRIEVAL_MODE
    # )
    # answer, sources, metadata = rag.query(request.question)

    # PLACEHOLDER response
    answer = f"This is a placeholder answer to: '{request.question}'"
    sources = []
    latency_ms = (time.time() - start_time) * 1000

    return AskResponse(
        answer=answer,
        sources=sources,
        config_used=get_config_dict(),
        metadata={
            "latency_ms": round(latency_ms, 2),
            "chunks_searched": 0,
            "chunks_relevant": 0,
        },
    )


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
