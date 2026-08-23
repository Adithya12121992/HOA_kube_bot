""""Thinking" mode: corrective RAG (retrieve -> grade -> rewrite -> generate).

Adapted from the original src/rag/rag_graph.py prototype (real, well-designed
grading/generation prompts — doc_type-aware routing, section citations,
bounded rewrite loop), rewired to use this project's environment-aware
llm.py/store.py instead of a hardcoded OpenAI client pointed at LM Studio's
address with a model name ("gpt-3.5-turbo") that doesn't match anything
actually loaded there.

Design choice: implemented as a plain bounded loop, not a LangGraph
StateGraph. The control flow is simple and linear (retrieve, grade, maybe
rewrite up to twice, generate) — it doesn't need a graph library's branching
machinery to express, and a plain function is easier to test directly (see
the real end-to-end verification this module was built with, in
ISSUES_AND_FIXES.md). "Thinking mode" describes the retrieval strategy, not
a commitment to a specific orchestration library.
"""

from __future__ import annotations

import json
import re
import time
from typing import TypedDict

from src.rag.llm import generate
from src.rag.query import Source, AnswerResult, _build_context
from src.rag.store import search

TOP_K = 8
MAX_REWRITES = 2
GRADE_MAX_TOKENS = 300
REWRITE_MAX_TOKENS = 150
ANSWER_MAX_TOKENS = 1000

GRADING_PROMPT = """You are an expert HOA document classifier. Given a question and a list of chunks,
decide which chunks are relevant to answering the question.

CRITICAL GUIDANCE:
- Governing chunks (CC&Rs, Bylaws, Operating Rules) are AUTHORITATIVE for rules about what owners
  may or may not do. These are the primary source for operational/conduct questions.
  EXAMPLE: "Can I run a business?" requires governing chunks that discuss business restrictions.
- Advisory chunks describe general California law or market trends, NOT this association's specific
  rules. They are relevant only if the question asks about state law or broader context.
- Report chunks (Property Inspection, Pest, Roof, Title, etc.) describe property condition, findings,
  defects, or state of repair. They are ESSENTIAL for questions about inspection results, condition,
  defects, or repairs.

DECISION RULES:
1. If the question mentions "inspection", "findings", "condition", "defects", "damage", or "repair" ->
   PRIORITIZE report chunks, even if advisory chunks rank higher semantically.
2. If the question asks about owner rules or restrictions -> prioritize governing chunks.
3. If multiple chunks are relevant, include them ALL to maximize answer completeness.

Return ONLY a JSON array of 0-indexed chunk indices (no markdown, no explanation): [0, 2, 4]
Or empty array if no chunks are relevant: []

Question: {question}

Chunks:
{chunks_block}"""

REWRITE_PROMPT = """Rewrite this question using formal HOA/legal document vocabulary. \
Use terms like: lease, rental, assessment, Owner, Lot, Common Area, Bylaws, CC&Rs, \
covenant, restriction, Board, member. Return ONLY the rewritten query, no explanation.

Question: {question}"""

GENERATE_SYSTEM_PROMPT = """You are an HOA document assistant. Answer questions ONLY using the provided context.

For every claim, cite the source: (document name, pages). Example: "According to the CC&Rs (pages 30-31), owners must..."

Choose ONE of these:
1. If the documents contain relevant information, provide a direct answer citing sources.
2. If the documents do NOT contain relevant information, respond with ONLY: "The documents don't address this question."

Do NOT mix both. Do not speculate or use external knowledge. Stay strictly within the provided chunks."""


class ThinkingTrace(TypedDict):
    steps: list[str]
    rewrite_count: int


def _strip_think_tags(text: str) -> str:
    """Local reasoning models sometimes leak <think>...</think> blocks into content
    even outside the dedicated reasoning_content field (model-dependent quirk)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _parse_grade_response(text: str) -> list[int]:
    text = _strip_think_tags(text)
    if text.startswith("```"):
        text = re.sub(r"```json?\n?", "", text)
        text = re.sub(r"\n?```", "", text)
    text = text.strip()
    try:
        indices = json.loads(text)
        return indices if isinstance(indices, list) else []
    except json.JSONDecodeError:
        return []


def _grade_chunks(question: str, chunks: list[dict]) -> list[int]:
    """Ask the LLM which retrieved chunks are actually relevant. Returns their indices."""
    if not chunks:
        return []

    chunk_descs = []
    for i, chunk in enumerate(chunks):
        source = chunk.get("source", "Unknown")
        doc_type = chunk.get("doc_type", "-")
        pages = f"{chunk.get('page_start', '?')}-{chunk.get('page_end', '?')}"
        chunk_descs.append(f"[{i}] {source} [{doc_type}] (p{pages})\n    {chunk.get('text', '')}")

    prompt = GRADING_PROMPT.format(question=question, chunks_block="\n\n".join(chunk_descs))
    response = generate(prompt, max_tokens=GRADE_MAX_TOKENS, temperature=0)
    if response is None:
        return []  # no LLM reachable - treat as "nothing gradeable", generate() will fall back to all chunks
    return _parse_grade_response(response)


def _rewrite_query(question: str) -> str:
    """Rewrite the question using formal HOA vocabulary, for better retrieval on the next pass."""
    prompt = REWRITE_PROMPT.format(question=question)
    response = generate(prompt, max_tokens=REWRITE_MAX_TOKENS, temperature=0)
    if response is None:
        return question  # no LLM reachable - keep searching with the original question
    return _strip_think_tags(response)


def _generate_answer(original_question: str, chunks: list[dict], relevant_indices: list[int]) -> str:
    if relevant_indices:
        relevant_chunks = [chunks[i] for i in relevant_indices if i < len(chunks)]
    else:
        relevant_chunks = chunks  # fallback: use everything retrieved, let the model judge

    context = _build_context(relevant_chunks) if relevant_chunks else "(no documents retrieved)"
    prompt = f"{GENERATE_SYSTEM_PROMPT}\n\n{context}\n\nQuestion: {original_question}"

    answer = generate(prompt, max_tokens=ANSWER_MAX_TOKENS, temperature=0)
    if answer is None:
        return "I found relevant documents, but couldn't reach the language model to generate an answer. Please try again."
    return _strip_think_tags(answer)


def answer_question_thinking(question: str, k: int = TOP_K) -> AnswerResult:
    """Corrective RAG: retrieve -> grade -> rewrite (up to MAX_REWRITES) -> generate.

    Unlike fast mode (src/rag/query.py), this grades retrieved chunks for
    relevance before generating, and reformulates the query and re-retrieves
    if grading found nothing sufficient - trading latency for higher
    precision on ambiguous or colloquially-phrased questions.
    """
    start_time = time.time()
    trace: list[str] = []

    current_question = question
    chunks: list[dict] = []
    relevant_indices: list[int] = []
    rewrite_count = 0

    while True:
        chunks = search(current_question, k=k)
        trace.append(f"retrieve({len(chunks)} chunks)")

        relevant_indices = _grade_chunks(question, chunks)  # grade against the ORIGINAL question, not the rewritten one
        sufficient = len(relevant_indices) > 0
        trace.append(f"grade({'sufficient' if sufficient else 'insufficient'}, {len(relevant_indices)} relevant)")

        if sufficient or rewrite_count >= MAX_REWRITES:
            break

        current_question = _rewrite_query(current_question)
        rewrite_count += 1
        trace.append(f"rewrite({rewrite_count}): {current_question!r}")

    answer = _generate_answer(question, chunks, relevant_indices)
    trace.append("generate")

    used_chunks = [chunks[i] for i in relevant_indices if i < len(chunks)] if relevant_indices else chunks
    sources = [
        Source(
            chunk_id=chunk["chunk_id"],
            source=chunk.get("source", "unknown"),
            page_start=chunk.get("page_start", 0),
            page_end=chunk.get("page_end", 0),
            similarity=chunk["similarity"],
            text_preview=chunk["text"][:200],
        )
        for chunk in used_chunks
    ]

    latency_ms = round((time.time() - start_time) * 1000, 2)

    return AnswerResult(
        answer=answer,
        sources=sources,
        metadata={
            "latency_ms": latency_ms,
            "chunks_searched": len(chunks),
            "chunks_relevant": len(relevant_indices),
            "rewrite_count": rewrite_count,
            "trace": trace,
        },
    )
