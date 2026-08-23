"""Conversation memory — Mem0 (cloud) or a plain in-process dict (local).

Matches the environment bundle design (src/config/settings.py): "local" ->
Simple in-memory session, "cloud" -> Mem0. Only meaningful when a caller
supplies a user_id (src/services/chatbot/service.py's AskRequest already
has an optional user_id field) — without one, there's no identity to key
memories by, and both backends are no-ops.

Real Mem0 API contract (verified directly against the live API, not just
docs): `add(messages, user_id=...)` takes a list of {"role", "content"}
dicts and returns immediately with {"event_id": ..., "status": "PENDING"} -
Mem0 does its own async fact-extraction from the conversation, so a memory
added this turn may not be searchable yet on the very next call (a few
seconds' lag, acceptable here since it only affects one user's next
question, not a hot path). `search(query, filters={"user_id": ...},
version="v2")` returns {"results": [{"memory": "...", "score": ...}, ...]}
— note `user_id` must go in `filters`, not as a direct kwarg (confirmed:
passing it directly raises ValueError).
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config.settings import MEM0_API_KEY, get_environment

logger = logging.getLogger(__name__)

MAX_MEMORIES_RETRIEVED = 5

# Local "simple" memory: plain in-process dict, session-only (lost on
# restart/redeploy — that's the intentional distinction from "cloud"/Mem0,
# not an oversight). Keyed by user_id, each value a list of
# {"question", "answer"} turns, most recent last.
_local_sessions: dict[str, list[dict]] = {}

_mem0_client = None


def _get_mem0_client():
    global _mem0_client
    if _mem0_client is None:
        from mem0 import MemoryClient
        _mem0_client = MemoryClient(api_key=MEM0_API_KEY)
    return _mem0_client


def get_relevant_memories(user_id: Optional[str], question: str) -> list[str]:
    """Past context relevant to this question, for the active environment's memory backend.

    Returns an empty list if user_id is None, no memory backend is
    configured, or the lookup fails — memory is an enhancement, never a
    hard dependency for answering.
    """
    if not user_id:
        return []

    if get_environment() == "cloud":
        if not MEM0_API_KEY:
            return []
        try:
            client = _get_mem0_client()
            result = client.search(question, filters={"user_id": user_id}, version="v2")
            return [r["memory"] for r in result.get("results", [])[:MAX_MEMORIES_RETRIEVED]]
        except Exception as e:
            logger.warning(f"Mem0 search failed, continuing without memory context: {e}")
            return []

    # local: simple session memory - just the recent Q&A turns, no semantic search
    turns = _local_sessions.get(user_id, [])
    return [f"Q: {t['question']}\nA: {t['answer']}" for t in turns[-MAX_MEMORIES_RETRIEVED:]]


def add_memory(user_id: Optional[str], question: str, answer: str) -> None:
    """Record a Q&A turn for future context. No-op if user_id is None."""
    if not user_id:
        return

    if get_environment() == "cloud":
        if not MEM0_API_KEY:
            return
        try:
            client = _get_mem0_client()
            client.add(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Mem0 add failed (answer already returned to user, memory just won't persist): {e}")
        return

    # local: append to the in-process session dict
    _local_sessions.setdefault(user_id, []).append({"question": question, "answer": answer})
