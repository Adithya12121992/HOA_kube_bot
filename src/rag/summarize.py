"""Best-effort 2-line document summary, generated via whichever LLM the
active environment bundle points at (src/rag/llm.py).

A missing summary must never block marking a document "ready" for search
(see PLAN.md Step 2.4) — llm.generate() already returns None on any
failure rather than raising, so this module just supplies the prompt.
"""

from __future__ import annotations

from typing import Optional

from src.rag.llm import generate

MAX_SOURCE_CHARS = 2000  # first ~2000 chars of the doc's text is enough context for a 2-line summary
SUMMARY_MAX_TOKENS = 800  # generous budget — local reasoning models spend most of it on internal reasoning, not the final answer (see llm.py)

_PROMPT_TEMPLATE = (
    "Summarize this {doc_type} document in exactly 2 lines. "
    "Be concise and specific about what it covers.\n\n{text}"
)


def summarize_document(doc_type: str, full_text: str) -> Optional[str]:
    """Generate a 2-line summary, or None if no LLM is reachable/configured."""
    text_sample = full_text[:MAX_SOURCE_CHARS]
    prompt = _PROMPT_TEMPLATE.format(doc_type=doc_type or "HOA", text=text_sample)
    return generate(prompt, max_tokens=SUMMARY_MAX_TOKENS)
