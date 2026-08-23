"""Integration tests for the fast-mode answer pipeline (src/rag/query.py):
real ChromaDB retrieval + real memory wiring, with only the LLM call itself
mocked (an external network dependency, not what these tests are about).
"""

from __future__ import annotations

from tests.conftest import make_chunk


class TestAnswerQuestionFastMode:
    def test_no_chunks_found_returns_helpful_message_without_calling_llm(self, isolated_data_dir, monkeypatch):
        import src.rag.query as query

        called = []
        monkeypatch.setattr(query, "generate", lambda *a, **k: called.append(1) or "should not be called")

        result = query.answer_question("anything")

        assert called == []
        assert "couldn't find any relevant documents" in result["answer"]
        assert result["sources"] == []

    def test_real_retrieval_feeds_into_generation_prompt(self, isolated_data_dir, monkeypatch):
        import src.rag.query as query

        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Board meetings are held on the first Tuesday at 6:30 PM.")])

        captured_prompts = []

        def fake_generate(prompt, **kwargs):
            captured_prompts.append(prompt)
            return "Board meetings are on the first Tuesday at 6:30 PM [1]."

        monkeypatch.setattr(query, "generate", fake_generate)

        result = query.answer_question("When do board meetings happen?")

        assert "first Tuesday" in captured_prompts[0]  # retrieved chunk text reached the prompt
        assert result["answer"] == "Board meetings are on the first Tuesday at 6:30 PM [1]."
        assert result["sources"][0]["chunk_id"] == "doc:chunk_0"

    def test_llm_unreachable_returns_fallback_message_not_none(self, isolated_data_dir, monkeypatch):
        import src.rag.query as query

        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Some real content.")])
        monkeypatch.setattr(query, "generate", lambda *a, **k: None)

        result = query.answer_question("a question")

        assert "couldn't reach the language model" in result["answer"]

    def test_memory_included_in_prompt_when_user_id_given(self, isolated_data_dir, monkeypatch):
        import src.rag.memory as memory
        import src.rag.query as query

        monkeypatch.setattr(memory, "get_environment", lambda: "local")
        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Board meetings: first Tuesday, 6:30 PM.")])

        monkeypatch.setattr(query, "generate", lambda *a, **k: "First Tuesday at 6:30 PM.")
        query.answer_question("When are board meetings?", user_id="alice")

        captured_prompts = []
        monkeypatch.setattr(
            query, "generate", lambda prompt, **k: captured_prompts.append(prompt) or "6:30 PM."
        )
        result = query.answer_question("What time again?", user_id="alice")

        assert "earlier in this conversation" in captured_prompts[0]
        assert result["metadata"]["memories_used"] == 1

    def test_memory_not_recorded_without_user_id(self, isolated_data_dir, monkeypatch):
        import src.rag.memory as memory
        import src.rag.query as query

        monkeypatch.setattr(memory, "get_environment", lambda: "local")
        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Some content.")])
        monkeypatch.setattr(query, "generate", lambda *a, **k: "An answer.")

        query.answer_question("a question")  # no user_id

        assert memory._local_sessions == {}
