"""
Central configuration for HOA Bot
Manages all toggles and fixed settings
"""

import json
import os
from pathlib import Path
from typing import Literal, Optional, TypedDict

from dotenv import load_dotenv

# Loads .env into the process environment if present (local dev only — in
# K8s, real env vars/secrets are already set and this is a no-op since
# load_dotenv() doesn't override existing env vars by default).
load_dotenv()

# ============================================================================
# USER-TOGGLED SETTINGS (changeable via UI)
# ============================================================================
#
# IMPORTANT: these are NOT plain module-level constants. consumer and
# hoa-bot run as separate processes/pods with no shared memory, so a plain
# `ENVIRONMENT = "local"` global — even mutated via `global ENVIRONMENT` in
# one process — would never be visible to the other. Worse, even *within* a
# single process, `from src.config.settings import ENVIRONMENT` copies the
# value at import time; reassigning the module-level name later (e.g. via
# update_config()) does NOT update that copy — every module that imported
# it that way keeps seeing the stale value forever. Confirmed this exact bug
# in store.py and llm.py before this fix (see ISSUES_AND_FIXES.md).
#
# Fix: a shared config file on the PVC (same pattern as src/rag/status.py)
# is the single source of truth. get_environment()/get_retrieval_mode()
# read it fresh every call — callers must call the function, not import a
# frozen value. update_config() writes to the same file, so a toggle made
# in hoa-bot is immediately visible to consumer's next message too.

Environment = Literal["local", "cloud"]
RetrievalMode = Literal["fast", "thinking"]

_DEFAULT_ENVIRONMENT: Environment = os.getenv("ENVIRONMENT", "local")
_DEFAULT_RETRIEVAL_MODE: RetrievalMode = os.getenv("RETRIEVAL_MODE", "fast")
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

Retrieval strategy (orthogonal to environment, works with either bundle):
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
LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "")  # LM Studio can require a Bearer token

# --- Cloud environment ---
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = "hoa-documents"
# Note: no PINECONE_ENVIRONMENT setting — that was the old Pinecone v2 API
# concept (e.g. "gcp-starter"). The modern client (matching "pcsk_..." key
# format) resolves the index host from name + API key directly; serverless
# cloud/region is set once at index-creation time, not per-request.

MEM0_API_KEY = os.getenv("MEM0_API_KEY", "")

LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "")  # LlamaIndex (cloud rag_framework)

# Cloud LLM: Anthropic only (verified working end-to-end). OPENAI_API_KEY
# is still read if set, but not in the active fallback chain — that
# account hit insufficient_quota (no billing configured), and the user
# opted to stick with Anthropic rather than fix that account. Add "openai"
# back to CLOUD_LLM_FALLBACK_ORDER if that changes.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
CLOUD_LLM_FALLBACK_ORDER = ["anthropic"]

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

_SHARED_CONFIG_PATH = Path(DATA_DIR) / "config.json"


# ============================================================================
# SHARED CONFIG (toggle state — source of truth, see comment above)
# ============================================================================


class _ToggleState(TypedDict):
    environment: Environment
    retrieval_mode: RetrievalMode


def _read_shared_config() -> Optional[_ToggleState]:
    if not _SHARED_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(_SHARED_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_shared_config(state: _ToggleState) -> None:
    _SHARED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _SHARED_CONFIG_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(state, indent=2))
    os.replace(tmp_path, _SHARED_CONFIG_PATH)  # atomic on POSIX


def get_environment() -> Environment:
    """Current environment toggle. Call this, don't import ENVIRONMENT as a value."""
    state = _read_shared_config()
    return state["environment"] if state else _DEFAULT_ENVIRONMENT


def get_retrieval_mode() -> RetrievalMode:
    """Current retrieval mode toggle. Call this, don't import RETRIEVAL_MODE as a value."""
    state = _read_shared_config()
    return state["retrieval_mode"] if state else _DEFAULT_RETRIEVAL_MODE


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_config_dict() -> dict:
    """Return current configuration as dictionary"""
    environment = get_environment()
    return {
        "environment": environment,
        "retrieval_mode": get_retrieval_mode(),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimension": EMBEDDING_DIMENSION,
        "stack": get_stack_summary(environment),
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
    Update user-toggled configuration. Persisted to the shared config file
    on the PVC — visible to every process/pod reading via get_environment()/
    get_retrieval_mode(), not just this one.
    """
    new_state: _ToggleState = {
        "environment": get_environment(),
        "retrieval_mode": get_retrieval_mode(),
    }

    if environment and environment in ("local", "cloud"):
        new_state["environment"] = environment

    if retrieval_mode and retrieval_mode in ("fast", "thinking"):
        new_state["retrieval_mode"] = retrieval_mode

    _write_shared_config(new_state)
    return get_config_dict()
