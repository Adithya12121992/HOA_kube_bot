"""Stage 3b: Vector storage — ChromaDB (local) or Pinecone (cloud).

Backend is selected by the active environment bundle (see
src/config/settings.py): "local" -> ChromaDB, "cloud" -> Pinecone. Each
environment is a complete, non-mixed stack — this module never writes to
both at once.

Embedding model: BAAI/bge-small-en-v1.5 (loaded once at module level),
used identically for both backends — embedding always runs locally
regardless of which environment is active.

Usage:
  from src.rag.store import add_chunks, search, reset

  count = add_chunks(chunks_list)   # embeds and upserts to the active backend
  results = search("query text")    # search the active backend
  reset()                           # clear the active backend's data
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
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

# Global embedding model + backend clients (loaded/connected once)
_embedding_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.PersistentClient] = None
_pinecone_index = None


def _get_embedding_model() -> SentenceTransformer:
    """Lazy-load the embedding model on first use."""
    global _embedding_model
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
    """Lazy-load ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_DATA, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            str(CHROMA_DATA),
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def _chroma_add_chunks(chunks: list[dict]) -> int:
    client = _get_chroma_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    chunk_texts = [chunk["text"] for chunk in chunks]
    embeddings = _embed_texts(chunk_texts, is_query=False)
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


def _pinecone_add_chunks(chunks: list[dict]) -> int:
    index = _get_pinecone_index()

    chunk_texts = [chunk["text"] for chunk in chunks]
    embeddings = _embed_texts(chunk_texts, is_query=False)

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


def _pinecone_search(query: str, k: int) -> list[dict]:
    index = _get_pinecone_index()
    query_embedding = _embed_texts([query], is_query=True)[0]

    result = index.query(vector=query_embedding, top_k=k, include_metadata=True)

    formatted_results = []
    for match in result.matches:
        metadata = _restore_metadata(dict(match.metadata))
        text = metadata.pop("text", "")
        formatted_results.append({
            "chunk_id": match.id,
            "text": text,
            "similarity": match.score,  # Pinecone cosine metric already returns similarity, not distance
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
    """Embed chunks and add them to the active environment's vector store.

    Args:
        chunks: List of chunk records with 'chunk_id', 'text', and metadata.

    Returns:
        Number of chunks added/updated.
    """
    if not chunks:
        return 0
    if get_environment() == "cloud":
        return _pinecone_add_chunks(chunks)
    return _chroma_add_chunks(chunks)


def search(query: str, k: int = 5) -> list[dict]:
    """Search the active environment's vector store for chunks similar to the query.

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
    """Clear the active environment's vector store."""
    if get_environment() == "cloud":
        _pinecone_reset()
    else:
        _chroma_reset()


if __name__ == "__main__":
    print("store.py is a library module. Use it via:")
    print("  from src.rag.store import add_chunks, search, reset")
