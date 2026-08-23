"""Fast-mode RAG query: retrieve top-k chunks, generate a grounded answer with citations.

"Thinking" mode (retrieve -> grade -> rewrite -> generate) is a separate,
more involved corrective-RAG flow — see src/rag/thinking.py, which reuses
Source/AnswerResult/_build_context from this module. This module covers
"fast" mode only.
"""

from __future__ import annotations

import time
from typing import TypedDict

from src.rag.llm import generate
from src.rag.store import search

TOP_K = 8
ANSWER_MAX_TOKENS = 1000

_PROMPT_TEMPLATE = """You are answering a question about HOA (homeowners association) documents, using only the excerpts below. If the excerpts don't contain enough information to answer, say so — do not use outside knowledge.

Excerpts:
{context}

Question: {question}

Answer concisely, and reference sources by their [N] marker where relevant."""


class Source(TypedDict):
    chunk_id: str
    source: str
    page_start: int
    page_end: int
    similarity: float
    text_preview: str


class AnswerResult(TypedDict):
    answer: str
    sources: list[Source]
    metadata: dict


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        pages = f"p.{chunk.get('page_start')}-{chunk.get('page_end')}"
        parts.append(f"[{i}] ({chunk.get('source', 'unknown')}, {pages})\n{chunk['text']}")
    return "\n\n".join(parts)


def answer_question(question: str, k: int = TOP_K) -> AnswerResult:
    """Retrieve relevant chunks and generate a grounded answer.

    Returns an answer even if no LLM is reachable — in that case `answer`
    explains the failure rather than raising, since this is a user-facing
    request/response endpoint (unlike summarize_document, there's no
    "silently skip and continue" option — the user is waiting for a reply).
    """
    start_time = time.time()

    chunks = search(question, k=k)

    if not chunks:
        return AnswerResult(
            answer="I couldn't find any relevant documents to answer this question. Try uploading relevant HOA documents first.",
            sources=[],
            metadata={"latency_ms": round((time.time() - start_time) * 1000, 2), "chunks_searched": 0},
        )

    context = _build_context(chunks)
    prompt = _PROMPT_TEMPLATE.format(context=context, question=question)
    answer = generate(prompt, max_tokens=ANSWER_MAX_TOKENS)

    if answer is None:
        answer = "I found relevant documents, but couldn't reach the language model to generate an answer. Please try again."

    sources = [
        Source(
            chunk_id=chunk["chunk_id"],
            source=chunk.get("source", "unknown"),
            page_start=chunk.get("page_start", 0),
            page_end=chunk.get("page_end", 0),
            similarity=chunk["similarity"],
            text_preview=chunk["text"][:200],
        )
        for chunk in chunks
    ]

    latency_ms = round((time.time() - start_time) * 1000, 2)

    return AnswerResult(
        answer=answer,
        sources=sources,
        metadata={"latency_ms": latency_ms, "chunks_searched": len(chunks)},
    )
