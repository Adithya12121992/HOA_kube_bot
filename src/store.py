"""Stage 3b: Vector storage via ChromaDB.

Thin wrapper around ChromaDB for persistent embedding storage and retrieval.
Embedding model: BAAI/bge-small-en-v1.5 (loaded once at module level).

Usage:
  from store import add_chunks, search, reset

  # Add chunks (embeds and upserts to vector DB)
  count = add_chunks(chunks_list)

  # Search for similar chunks
  results = search("query text")

  # Clear the database
  reset()

Run: import and call functions; or use search_test.py for CLI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Paths and config
CHROMA_DATA = Path("./chroma_data")
COLLECTION_NAME = "hoa_chunks"

# BGE query prefix (per model documentation)
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Global embedding model (loaded once)
_embedding_model: Optional[SentenceTransformer] = None
_chroma_client: Optional[chromadb.PersistentClient] = None


def _get_embedding_model() -> SentenceTransformer:
    """Lazy-load the embedding model on first use."""
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model BAAI/bge-small-en-v1.5 (first time only)...")
        _embedding_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _embedding_model


def _get_chroma_client() -> chromadb.PersistentClient:
    """Lazy-load ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_DATA, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(str(CHROMA_DATA))
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

    # Embed all chunk texts.
    chunk_texts = [chunk["text"] for chunk in chunks]
    embeddings = _embed_texts(chunk_texts, is_query=False)

    # Prepare metadata: exclude 'text' and 'chunk_id' from metadata.
    metadatas = []
    for chunk in chunks:
        meta = {k: v for k, v in chunk.items() if k not in ["text", "chunk_id", "embeddings"]}
        # Convert non-string values to strings for ChromaDB compatibility.
        meta_str = {}
        for k, v in meta.items():
            if isinstance(v, int):
                meta_str[k] = str(v)
            elif isinstance(v, (str, type(None))):
                meta_str[k] = v or ""
            else:
                meta_str[k] = str(v)
        metadatas.append(meta_str)

    # Upsert into collection.
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

    # Embed the query with BGE prefix.
    query_embedding = _embed_texts([query], is_query=True)[0]

    # Search.
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    # Format results: convert distances to similarity scores (cosine distance → similarity).
    # ChromaDB returns distances; for cosine, similarity = 1 - distance.
    formatted_results = []
    if results["ids"] and len(results["ids"]) > 0:
        for i, chunk_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            similarity = 1 - distance  # Convert cosine distance to similarity.
            text = results["documents"][0][i]
            metadata = results["metadatas"][0][i]

            # Restore list fields that were stringified for ChromaDB storage
            if "sections" in metadata and isinstance(metadata["sections"], str):
                try:
                    metadata["sections"] = json.loads(metadata["sections"])
                except (json.JSONDecodeError, ValueError):
                    metadata["sections"] = []

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
    print("  from store import add_chunks, search, reset")
