"""Unit tests for src/rag/memory.py's local (in-process session) backend.

The Mem0/cloud path needs a real API key and network - see
tests/integration/test_memory_mem0.py (skipped without MEM0_API_KEY).
"""

from __future__ import annotations

import pytest

import src.rag.memory as memory


@pytest.fixture(autouse=True)
def local_environment(monkeypatch):
    """Force the "local" branch regardless of the ambient/shared config
    toggle, so this test doesn't depend on what environment some other
    process last left in DATA_DIR/config.json."""
    monkeypatch.setattr(memory, "get_environment", lambda: "local")
    memory._local_sessions.clear()


class TestLocalMemory:
    def test_no_user_id_is_a_noop(self):
        assert memory.get_relevant_memories(None, "any question") == []
        memory.add_memory(None, "q", "a")  # must not raise
        assert memory._local_sessions == {}

    def test_no_memories_before_any_turn(self):
        assert memory.get_relevant_memories("user-1", "first question") == []

    def test_recalls_prior_turn(self):
        memory.add_memory("user-1", "When are board meetings?", "First Tuesday at 6:30 PM.")
        recalled = memory.get_relevant_memories("user-1", "What time again?")
        assert len(recalled) == 1
        assert "First Tuesday at 6:30 PM" in recalled[0]

    def test_sessions_isolated_per_user(self):
        memory.add_memory("user-1", "q1", "a1")
        memory.add_memory("user-2", "q2", "a2")
        assert len(memory.get_relevant_memories("user-1", "x")) == 1
        assert "a1" in memory.get_relevant_memories("user-1", "x")[0]
        assert "a2" in memory.get_relevant_memories("user-2", "x")[0]

    def test_only_last_n_turns_returned(self):
        for i in range(memory.MAX_MEMORIES_RETRIEVED + 5):
            memory.add_memory("user-1", f"q{i}", f"a{i}")
        recalled = memory.get_relevant_memories("user-1", "latest")
        assert len(recalled) == memory.MAX_MEMORIES_RETRIEVED
        # most recent turns, not the earliest
        assert f"a{memory.MAX_MEMORIES_RETRIEVED + 4}" in recalled[-1]
