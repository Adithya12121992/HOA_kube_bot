"""Stage 3b: Vector storage — dual-write ChromaDB + Pinecone, toggle-read.

Cloud retrieval goes through LlamaIndex's PineconeVectorStore (see
_pinecone_search below), matching the RAG-framework-per-bundle design in
PLAN.md/settings.py (local: plain retrieve loop, cloud: LlamaIndex).
Writes still use the raw Pinecone SDK directly - only retrieval needed the
framework, and reusing the same write path for both backends keeps one
tested code path instead of two.

Chunking and embedding happen once per document regardless of environment,
and get written to BOTH ChromaDB and Pinecone — a single upload populates
both stores, so local vs cloud retrieval can be compared on identical data
without re-uploading. The environment toggle (src/config/settings.py)
controls which backend actually gets QUERIED (search()), not which one
gets written to.

ChromaDB writes are treated as required (always attempted; failure
propagates to the caller — it's local disk with no API key, the backend
Phase 1-2 always assumed would work). Pinecone writes are
best-effort: if PINECONE_API_KEY isn't configured or the write fails, it's
logged and skipped rather than failing the whole document — same
graceful-degradation pattern as summarize.py, so a document is still
searchable locally even if the cloud write didn't happen.

Embedding model: BAAI/bge-small-en-v1.5 (loaded once at module level),
used identically for both backends — embedding always runs locally
regardless of which environment is active, and is computed once per
add_chunks() call and reused for both writes (not recomputed twice).

Usage:
  from src.rag.store import add_chunks, search, reset

  add_chunks(chunks_list)   # embeds once, writes to Chroma + Pinecone (if configured)
  results = search("query text")    # searches whichever backend the toggle points at
  reset()                           # clears both backends, keeping them in sync
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import chromadb
from llama_index.core.vector_stores.types import VectorStoreQuery
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

from src.config.settings import (
    CHROMA_DB_PATH,
    EMBEDDING_MODEL,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    get_environment,
)

# Suppress chromadb's posthog telemetry errors. anonymized_telemetry=False
# (set below) doesn't actually prevent these in this chromadb version — the
# capture() call still fires and fails on a posthog API signature mismatch,
# logged at ERROR level (logger.error(...) in chromadb's posthog.py), so
# setting the logger's level *to* ERROR doesn't suppress it; needs CRITICAL.
# Functionally harmless (confirmed: storage/search work fine either way),
# but would spam pod logs in production otherwise.
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)

CHROMA_DATA = Path(CHROMA_DB_PATH)
COLLECTION_NAME = "hoa_chunks"

# BGE query prefix (per model documentation)
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Metadata fields that must be restored to int on retrieval. Both backends'
# metadata systems are string/number/bool-only (no nested types), so list
# fields get JSON-encoded at write time regardless of backend — Pinecone
# natively supports list-of-string metadata, but using the same encoding
# for both keeps one tested code path instead of two.
_INT_FIELDS = {"page_start", "page_end", "char_start", "char_end"}
# Fields stored as "" in place of None (neither backend's metadata can hold
# None), restored back to None on read.
_NULLABLE_STR_FIELDS = {"article", "section_inherited"}

# Global embedding model + backend clients (loaded/connected once).
# ChromaDB is deliberately NOT cached here - see _get_chroma_client().
_embedding_model: Optional[SentenceTransformer] = None
_embedding_model_lock = threading.Lock()
_pinecone_index = None
_llama_vector_store: Optional[PineconeVectorStore] = None


def _get_embedding_model() -> SentenceTransformer:
    """Lazy-load the embedding model on first use.

    Locked: consumer processes documents with multiple concurrent worker
    threads, and an unsynchronized "if None: construct" check here let two
    threads both see None and race to build SentenceTransformer(...)
    concurrently - confirmed as a real bug (RuntimeError: "Cannot copy out
    of meta tensor; no data!") the first time two documents happened to hit
    this cold-start path at the same moment. The double-checked lock avoids
    holding the lock (and blocking every embed call) once the model is
    already loaded.
    """
    global _embedding_model
    if _embedding_model is None:
        with _embedding_model_lock:
            if _embedding_model is None:
                print(f"Loading embedding model {EMBEDDING_MODEL} (first time only)...")
                _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """Embed a list of texts using the BGE model.

    Args:
        texts: List of text strings to embed.
        is_query: If True, prefix each text with the BGE query prefix.

    Returns:
        List of embeddings (each a list of floats).
    """
    model = _get_embedding_model()

    if is_query:
        texts = [BGE_QUERY_PREFIX + text for text in texts]

    embeddings = model.encode(texts, convert_to_numpy=False)
    return [emb.tolist() for emb in embeddings]


def _prepare_metadata(chunk: dict, include_text: bool) -> dict:
    """Convert a chunk record into flat string/int/float/bool-only metadata.

    - Lists (e.g. `sections`) are JSON-encoded, not Python-`str()`-encoded —
      `str(['3.1.2'])` produces `"['3.1.2']"` (single-quoted), which is not
      valid JSON and fails `json.loads()` on every chunk with a non-empty
      list field. Verified this breaks retrieval for the majority of real
      chunks (most have populated `sections`) before this fix.
    - Optional[str] fields (`article`, `section_inherited`) become "" since
      neither backend's metadata can store None; restored back to None on read.
    - int fields pass through as int (both backends support int metadata
      natively) so no stringify/int() round-trip is needed for those.

    Args:
        include_text: ChromaDB stores document text separately from
            metadata; Pinecone has no separate text field, so text must be
            included in metadata there.
    """
    meta: dict = {}
    for k, v in chunk.items():
        if k == "chunk_id":
            continue
        if k == "text" and not include_text:
            continue
        if isinstance(v, list):
            meta[k] = json.dumps(v)
        elif isinstance(v, bool):
            meta[k] = v
        elif isinstance(v, int):
            meta[k] = v
        elif v is None:
            meta[k] = ""
        elif isinstance(v, str):
            meta[k] = v
        else:
            meta[k] = str(v)
    return meta


def _restore_metadata(meta: dict) -> dict:
    """Reverse `_prepare_metadata`'s encoding for a retrieved record."""
    restored = dict(meta)

    if "sections" in restored and isinstance(restored["sections"], str):
        try:
            restored["sections"] = json.loads(restored["sections"])
        except (json.JSONDecodeError, ValueError):
            restored["sections"] = []

    for field in _INT_FIELDS:
        if field in restored and isinstance(restored[field], str):
            try:
                restored[field] = int(restored[field])
            except ValueError:
                pass

    for field in _NULLABLE_STR_FIELDS:
        if restored.get(field) == "":
            restored[field] = None

    return restored


# ============================================================================
# ChromaDB backend (local environment)
# ============================================================================


def _get_chroma_client() -> chromadb.PersistentClient:
    """Open a fresh ChromaDB client on every call.

    consumer and hoa-bot are separate long-running processes/pods both
    pointed at the same on-disk ChromaDB path on the shared PVC. Confirmed
    as a real bug: hoa-bot kept returning 0 search results for a document
    consumer had already written (independently confirmed present via a
    fresh one-off process), until hoa-bot's pod restarted.

    Root cause is NOT this project's own client caching (removing that
    alone did not fix it - verified) but chromadb's own internal
    chromadb.api.client.SharedSystemClient._identifer_to_system: a
    class-level (i.e. process-global) dict caching the underlying System
    object per persist_directory, reused by every `PersistentClient(path)`
    call within the same process regardless of on-disk changes made by a
    different process in the meantime. Evicting that cache entry before
    each open forces a true reread from disk - confirmed with a real
    synchronized cross-process test (writer process writes and exits or
    stays alive; a separate long-lived "reader" process, without evicting,
    still saw 0 results after the write; with eviction, saw the write
    immediately, no restart needed).
    """
    from chromadb.api.client import SharedSystemClient

    os.makedirs(CHROMA_DATA, exist_ok=True)
    SharedSystemClient._identifer_to_system.pop(str(CHROMA_DATA), None)
    return chromadb.PersistentClient(
        str(CHROMA_DATA),
        settings=chromadb.Settings(anonymized_telemetry=False),
    )


def _chroma_add_chunks(chunks: list[dict], embeddings: list[list[float]]) -> int:
    client = _get_chroma_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    chunk_texts = [chunk["text"] for chunk in chunks]
    metadatas = [_prepare_metadata(chunk, include_text=False) for chunk in chunks]
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]

    collection.upsert(
        ids=chunk_ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=chunk_texts,
    )
    return len(chunks)


def _chroma_search(query: str, k: int) -> list[dict]:
    client = _get_chroma_client()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    query_embedding = _embed_texts([query], is_query=True)[0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    formatted_results = []
    if results["ids"] and len(results["ids"]) > 0:
        for i, chunk_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            similarity = 1 - distance  # cosine distance -> similarity
            text = results["documents"][0][i]
            metadata = _restore_metadata(results["metadatas"][0][i])

            formatted_results.append({
                "chunk_id": chunk_id,
                "text": text,
                "similarity": similarity,
                **metadata,
            })
    return formatted_results


def _chroma_reset() -> None:
    client = _get_chroma_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Deleted collection '{COLLECTION_NAME}'")
    except Exception as e:
        print(f"Could not delete collection: {e}")


# ============================================================================
# Pinecone backend (cloud environment)
# ============================================================================


def _get_pinecone_index():
    """Lazy-connect to the Pinecone index."""
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def _pinecone_add_chunks(chunks: list[dict], embeddings: list[list[float]]) -> int:
    index = _get_pinecone_index()

    vectors = [
        {
            "id": chunk["chunk_id"],
            "values": embedding,
            "metadata": _prepare_metadata(chunk, include_text=True),
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]

    index.upsert(vectors=vectors)
    return len(chunks)


def _get_llama_vector_store() -> PineconeVectorStore:
    """Lazy-build the LlamaIndex wrapper around the existing Pinecone index.

    Retrieval only (not a full VectorStoreIndex/query engine) - generation
    still goes through llm.py's environment-aware Anthropic call, same as
    every other retrieval path in this project, so there's no reason to let
    LlamaIndex own synthesis too. text_key="text" matches how
    _prepare_metadata already stores chunk text in Pinecone metadata (writes
    still go through the raw Pinecone SDK in _pinecone_add_chunks - only the
    cloud *retrieval* path is LlamaIndex, per the project's stated RAG
    framework mapping in settings.py/PLAN.md).
    """
    global _llama_vector_store
    if _llama_vector_store is None:
        _llama_vector_store = PineconeVectorStore(pinecone_index=_get_pinecone_index(), text_key="text")
    return _llama_vector_store


def _pinecone_search(query: str, k: int) -> list[dict]:
    """Cloud retrieval via LlamaIndex's PineconeVectorStore, using this
    project's own BGE embedding (not LlamaIndex's embedding abstraction) so
    query-time vectors stay identical to what _pinecone_add_chunks wrote -
    same embedding call, same tested code path, for both backends.
    """
    vector_store = _get_llama_vector_store()
    query_embedding = _embed_texts([query], is_query=True)[0]

    result = vector_store.query(VectorStoreQuery(query_embedding=query_embedding, similarity_top_k=k))

    formatted_results = []
    for node, similarity, chunk_id in zip(result.nodes, result.similarities, result.ids):
        metadata = _restore_metadata(dict(node.metadata))
        formatted_results.append({
            "chunk_id": chunk_id,
            "text": node.get_content(),
            "similarity": similarity,  # Pinecone cosine metric already returns similarity, not distance
            **metadata,
        })
    return formatted_results


def _pinecone_reset() -> None:
    index = _get_pinecone_index()
    try:
        index.delete(delete_all=True)
        print(f"Deleted all vectors from Pinecone index '{PINECONE_INDEX_NAME}'")
    except Exception as e:
        print(f"Could not clear Pinecone index: {e}")


# ============================================================================
# Public API — dispatches to the active environment's backend
# ============================================================================


def add_chunks(chunks: list[dict]) -> int:
    """Embed chunks once, write to ChromaDB (required) and Pinecone (best-effort).

    A single call populates both backends, keeping them in sync so
    local vs cloud retrieval can be compared later without re-uploading.
    ChromaDB failures propagate (it's local disk, no reason for it to be
    flaky) — Pinecone failures/missing config are logged and skipped, same
    graceful-degradation pattern as summarize.py.

    Args:
        chunks: List of chunk records with 'chunk_id', 'text', and metadata.

    Returns:
        Number of chunks written to ChromaDB (the always-required backend).
    """
    if not chunks:
        return 0

    chunk_texts = [chunk["text"] for chunk in chunks]
    embeddings = _embed_texts(chunk_texts, is_query=False)

    count = _chroma_add_chunks(chunks, embeddings)

    if PINECONE_API_KEY:
        try:
            _pinecone_add_chunks(chunks, embeddings)
        except Exception as e:
            logger.warning(f"Pinecone write failed (chunks still searchable via ChromaDB): {e}")
    else:
        logger.info("PINECONE_API_KEY not configured — skipping cloud write, chunks stored locally only")

    return count


def search(query: str, k: int = 5) -> list[dict]:
    """Search whichever backend the environment toggle currently points at.

    Args:
        query: Search query (plain text; BGE prefix is added internally).
        k: Number of results to return.

    Returns:
        List of chunks with metadata and similarity score, ranked by similarity.
    """
    if get_environment() == "cloud":
        return _pinecone_search(query, k)
    return _chroma_search(query, k)


def reset() -> None:
    """Clear both backends, so they don't drift out of sync with each other."""
    _chroma_reset()
    if PINECONE_API_KEY:
        _pinecone_reset()


if __name__ == "__main__":
    print("store.py is a library module. Use it via:")
    print("  from src.rag.store import add_chunks, search, reset")
