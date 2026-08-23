"""Integration tests for the corrective-RAG "thinking" pipeline
(src/rag/thinking.py): real ChromaDB retrieval, only the LLM calls
(grade/rewrite/generate) are mocked - they're external network calls, and
this suite is testing the retrieve/grade/rewrite/generate control flow
itself, not LLM output quality (see ISSUES_AND_FIXES.md #13 for the real
LLM end-to-end verification that already happened by hand).
"""

from __future__ import annotations

from tests.conftest import make_chunk


class TestThinkingModeControlFlow:
    def test_sufficient_on_first_pass_does_not_rewrite(self, isolated_data_dir, monkeypatch):
        import src.rag.thinking as thinking

        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Board meetings: first Tuesday, 6:30 PM.")])

        calls = {"grade": 0, "rewrite": 0, "generate": 0}

        def fake_generate(prompt, **kwargs):
            if "expert HOA document classifier" in prompt:
                calls["grade"] += 1
                return "[0]"
            if "Rewrite this question" in prompt:
                calls["rewrite"] += 1
                return "rewritten"
            calls["generate"] += 1
            return "Board meetings are first Tuesday at 6:30 PM."

        monkeypatch.setattr(thinking, "generate", fake_generate)

        result = thinking.answer_question_thinking("When are board meetings?")

        assert calls["rewrite"] == 0
        assert calls["generate"] == 1
        assert result["metadata"]["rewrite_count"] == 0
        assert result["metadata"]["trace"] == ["retrieve(1 chunks)", "grade(sufficient, 1 relevant)", "generate"]

    def test_insufficient_grading_triggers_bounded_rewrite(self, isolated_data_dir, monkeypatch):
        import src.rag.thinking as thinking

        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Some content unrelated to the question.")])

        calls = {"grade": 0, "rewrite": 0}

        def fake_generate(prompt, **kwargs):
            if "expert HOA document classifier" in prompt:
                calls["grade"] += 1
                return "[]"  # always insufficient
            if "Rewrite this question" in prompt:
                calls["rewrite"] += 1
                return f"rewritten-{calls['rewrite']}"
            return "The documents don't address this question."

        monkeypatch.setattr(thinking, "generate", fake_generate)

        result = thinking.answer_question_thinking("An unanswerable question?")

        assert calls["rewrite"] == thinking.MAX_REWRITES
        assert result["metadata"]["rewrite_count"] == thinking.MAX_REWRITES
        assert result["answer"] == "The documents don't address this question."

    def test_llm_unreachable_during_grading_falls_back_to_all_chunks(self, isolated_data_dir, monkeypatch):
        import src.rag.thinking as thinking

        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Some real content.")])

        monkeypatch.setattr(thinking, "generate", lambda *a, **k: None)

        result = thinking.answer_question_thinking("a question")

        assert "couldn't reach the language model" in result["answer"]
        assert result["metadata"]["chunks_relevant"] == 0
        assert len(result["sources"]) == 1  # fell back to using the retrieved chunk anyway

    def test_memory_wired_same_as_fast_mode(self, isolated_data_dir, monkeypatch):
        import src.rag.memory as memory
        import src.rag.thinking as thinking

        monkeypatch.setattr(memory, "get_environment", lambda: "local")
        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Board meetings: first Tuesday, 6:30 PM.")])

        def fake_generate(prompt, **kwargs):
            if "expert HOA document classifier" in prompt:
                return "[0]"
            return "6:30 PM."

        monkeypatch.setattr(thinking, "generate", fake_generate)

        thinking.answer_question_thinking("When are board meetings?", user_id="bob")
        result = thinking.answer_question_thinking("What time again?", user_id="bob")

        assert result["metadata"]["memories_used"] == 1
