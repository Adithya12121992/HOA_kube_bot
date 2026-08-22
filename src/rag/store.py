"""Stage 3b: Vector storage via ChromaDB.

Thin wrapper around ChromaDB for persistent embedding storage and retrieval.
Embedding model: BAAI/bge-small-en-v1.5 (loaded once at module level).

Usage:
  from src.rag.store import add_chunks, search, reset

  count = add_chunks(chunks_list)   # embeds and upserts to vector DB
  results = search("query text")    # search for similar chunks
  reset()                           # clear the database
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from src.config.settings import CHROMA_DB_PATH, EMBEDDING_MODEL

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

# Metadata fields that must be restored to int on retrieval (ChromaDB
# metadata values must be str/int/float/bool at write time in this code's
# convention below, but round-tripping needs the type back for anything
# downstream that sorts/compares/formats page or char positions).
_INT_FIELDS = {"page_start", "page_end", "char_start", "char_end"}
# Fields stored as "" in place of None (ChromaDB metadata can't hold None),
# restored back to None on read so downstream code doesn't need to treat
# an empty string as meaningfully different from "no value".
_NULLABLE_STR_FIELDS = {"article", "section_inherited"}

# Global embedding model (loaded once)
_embedding_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.PersistentClient] = None


def _get_embedding_model() -> SentenceTransformer:
    """Lazy-load the embedding model on first use."""
    global _embedding_model
    if _embedding_model is None:
        print(f"Loading embedding model {EMBEDDING_MODEL} (first time only)...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_chroma_client() -> chromadb.PersistentClient:
    """Lazy-load ChromaDB client.

    Telemetry disabled: chromadb's bundled posthog client version mismatch
    causes noisy "Failed to send telemetry event" warnings on every call in
    this environment (capture() signature mismatch) — would spam pod logs
    in production for no functional benefit.
    """
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_DATA, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            str(CHROMA_DATA),
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
    return _chroma_client


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


def _prepare_metadata(chunk: dict) -> dict:
    """Convert a chunk record into ChromaDB-compatible metadata (str/int/float/bool only).

    - Lists (e.g. `sections`) are JSON-encoded, not Python-`str()`-encoded —
      `str(['3.1.2'])` produces `"['3.1.2']"` (single-quoted), which is not
      valid JSON and fails `json.loads()` on every chunk with a non-empty
      list field. Verified this breaks retrieval for the majority of real
      chunks (most have populated `sections`) before this fix.
    - Optional[str] fields (`article`, `section_inherited`) become "" since
      ChromaDB metadata can't store None; restored back to None on read.
    - int fields pass through as int (ChromaDB supports int metadata
      natively) so no stringify/int() round-trip is needed for those.
    """
    meta: dict = {}
    for k, v in chunk.items():
        if k in ("text", "chunk_id"):
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


def add_chunks(chunks: list[dict]) -> int:
    """Embed chunks and add them to ChromaDB.

    Args:
        chunks: List of chunk records with 'chunk_id', 'text', and metadata.

    Returns:
        Number of chunks added/updated.
    """
    if not chunks:
        return 0

    client = _get_chroma_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    chunk_texts = [chunk["text"] for chunk in chunks]
    embeddings = _embed_texts(chunk_texts, is_query=False)
    metadatas = [_prepare_metadata(chunk) for chunk in chunks]
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]

    collection.upsert(
        ids=chunk_ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=chunk_texts,
    )

    return len(chunks)


def search(query: str, k: int = 5) -> list[dict]:
    """Search for chunks similar to the query.

    Args:
        query: Search query (plain text; BGE prefix is added internally).
        k: Number of results to return.

    Returns:
        List of chunks with metadata and similarity score, ranked by similarity.
    """
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


def reset() -> None:
    """Clear the vector database (delete collection)."""
    client = _get_chroma_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Deleted collection '{COLLECTION_NAME}'")
    except Exception as e:
        print(f"Could not delete collection: {e}")


if __name__ == "__main__":
    print("store.py is a library module. Use it via:")
    print("  from src.rag.store import add_chunks, search, reset")
