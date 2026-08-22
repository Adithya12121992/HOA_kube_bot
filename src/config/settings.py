"""
Central configuration for HOA Bot
Manages all toggles and fixed settings
"""

import os
from typing import Literal

# ============================================================================
# USER-TOGGLED SETTINGS (changeable via UI)
# ============================================================================

STORAGE_MODE: Literal["local", "hybrid"] = os.getenv("STORAGE_MODE", "local")
"""
Storage backend selection:
- "local": ChromaDB only (fast, free, local)
- "hybrid": ChromaDB + Pinecone (compare local vs cloud)
"""

RETRIEVAL_MODE: Literal["fast", "thinking"] = os.getenv("RETRIEVAL_MODE", "fast")
"""
Retrieval strategy:
- "fast": Direct retrieval → generate (2-5s)
- "thinking": Retrieve → grade → rewrite → generate (10-30s, corrective RAG)
"""


# ============================================================================
# FIXED CONFIGURATION (not user-toggled)
# ============================================================================

# Embedding
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384
EMBEDDING_BATCH_SIZE = 32

# Chunking
CHUNK_SIZE = 3200
CHUNK_OVERLAP = 1
MIN_CHUNK_SIZE = 100

# Pinecone (for hybrid mode)
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = "hoa-documents"
PINECONE_ENVIRONMENT = "gcp-starter"

# ChromaDB
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", ".chroma_data")

# RabbitMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "test_queue")

# Application
APP_NAME = "HOA Bot"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Paths
DATA_DIR = os.getenv("DATA_DIR", "/data")
CHUNKS_JSON_PATH = os.getenv("CHUNKS_JSON_PATH", "chunks.json")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_config_dict() -> dict:
    """Return current configuration as dictionary"""
    return {
        "storage_mode": STORAGE_MODE,
        "retrieval_mode": RETRIEVAL_MODE,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIMENSION,
    }


def update_config(storage_mode: str = None, retrieval_mode: str = None) -> dict:
    """
    Update user-toggled configuration (in-memory only for this session)
    In production, persist to environment or database
    """
    global STORAGE_MODE, RETRIEVAL_MODE

    if storage_mode and storage_mode in ["local", "hybrid"]:
        STORAGE_MODE = storage_mode

    if retrieval_mode and retrieval_mode in ["fast", "thinking"]:
        RETRIEVAL_MODE = retrieval_mode

    return get_config_dict()
