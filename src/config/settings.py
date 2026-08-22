"""
Central configuration for HOA Bot
Manages all toggles and fixed settings
"""

import os
from typing import Literal

# ============================================================================
# USER-TOGGLED SETTINGS (changeable via UI)
# ============================================================================

ENVIRONMENT: Literal["local", "cloud"] = os.getenv("ENVIRONMENT", "local")
"""
Environment bundle selection. Each side is a full stack, not independent pieces:

- "local":
    Storage:        ChromaDB (on-disk, free)
    LLM:             LM Studio (local model server, OpenAI-compatible API)
    RAG framework:   LangGraph
    Memory:          Simple in-memory session

- "cloud":
    Storage:        Pinecone
    LLM:             Claude (primary) -> ChatGPT (fallback if Claude fails)
    RAG framework:   LlamaIndex
    Memory:          Mem0
"""

RETRIEVAL_MODE: Literal["fast", "thinking"] = os.getenv("RETRIEVAL_MODE", "fast")
"""
Retrieval strategy (orthogonal to ENVIRONMENT, works with either bundle):
- "fast": Direct retrieval → generate (2-5s)
- "thinking": Retrieve → grade → rewrite → generate (10-30s, corrective RAG)
"""


# ============================================================================
# FIXED CONFIGURATION (not user-toggled)
# ============================================================================

# Embedding (same for both environments — always runs locally, no API key)
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384
EMBEDDING_BATCH_SIZE = 32

# Chunking
CHUNK_SIZE = 3200
CHUNK_OVERLAP = 1
MIN_CHUNK_SIZE = 100

# --- Local environment ---
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", ".chroma_data")
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

# --- Cloud environment ---
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = "hoa-documents"
PINECONE_ENVIRONMENT = "gcp-starter"

MEM0_API_KEY = os.getenv("MEM0_API_KEY", "")

# LLM fallback chain for cloud mode: try Claude first, fall back to OpenAI
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
CLOUD_LLM_FALLBACK_ORDER = ["anthropic", "openai"]  # try in this order

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
        "environment": ENVIRONMENT,
        "retrieval_mode": RETRIEVAL_MODE,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "stack": get_stack_summary(ENVIRONMENT),
    }


def get_stack_summary(environment: str) -> dict:
    """Describe which concrete tech backs the given environment bundle"""
    if environment == "local":
        return {
            "storage": "chromadb",
            "llm": "lm_studio",
            "rag_framework": "langgraph",
            "memory": "simple",
        }
    return {
        "storage": "pinecone",
        "llm": "anthropic -> openai (fallback)",
        "rag_framework": "llamaindex",
        "memory": "mem0",
    }


def update_config(environment: str = None, retrieval_mode: str = None) -> dict:
    """
    Update user-toggled configuration (in-memory only for this session)
    In production, persist to environment or database
    """
    global ENVIRONMENT, RETRIEVAL_MODE

    if environment and environment in ["local", "cloud"]:
        ENVIRONMENT = environment

    if retrieval_mode and retrieval_mode in ["fast", "thinking"]:
        RETRIEVAL_MODE = retrieval_mode

    return get_config_dict()
