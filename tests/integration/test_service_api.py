"""Integration tests for the FastAPI service (src/services/chatbot/service.py),
via TestClient - real routing, real config toggle, real ChromaDB retrieval.
Only the LLM boundary (src.rag.query.generate / src.rag.thinking.generate)
is mocked, same rationale as test_query_pipeline.py/test_thinking_pipeline.py.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_chunk


@pytest.fixture
def api_client(isolated_data_dir):
    for mod_name in ["src.rag.query", "src.rag.thinking", "src.rag.memory", "src.services.chatbot.service"]:
        sys.modules.pop(mod_name, None)
    service = importlib.import_module("src.services.chatbot.service")
    with TestClient(service.app) as client:
        yield client, service


class TestHealthAndConfig:
    def test_health_check(self, api_client):
        client, _ = api_client
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_get_config_returns_local_defaults(self, api_client):
        client, _ = api_client
        resp = client.get("/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["environment"] == "local"
        assert body["retrieval_mode"] == "fast"

    def test_update_config_persists(self, api_client):
        client, _ = api_client
        resp = client.post("/config", json={"environment": "cloud", "retrieval_mode": "thinking"})
        assert resp.status_code == 200
        assert resp.json()["config"]["environment"] == "cloud"

        resp2 = client.get("/config")
        assert resp2.json()["environment"] == "cloud"
        assert resp2.json()["retrieval_mode"] == "thinking"


class TestAskEndpoint:
    def test_ask_fast_mode_returns_grounded_answer(self, api_client, monkeypatch):
        client, service = api_client
        isolated_store = importlib.import_module("src.rag.store")
        isolated_store.add_chunks([make_chunk("doc:chunk_0", "Board meetings: first Tuesday, 6:30 PM.")])

        import src.rag.query as query
        monkeypatch.setattr(query, "generate", lambda *a, **k: "First Tuesday at 6:30 PM [1].")

        resp = client.post("/ask", json={"question": "When are board meetings?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "First Tuesday at 6:30 PM [1]."
        assert body["config_used"]["retrieval_mode"] == "fast"
        assert body["sources"][0]["chunk_id"] == "doc:chunk_0"

    def test_ask_dispatches_to_thinking_mode_when_toggled(self, api_client, monkeypatch):
        client, service = api_client
        isolated_store = importlib.import_module("src.rag.store")
        isolated_store.add_chunks([make_chunk("doc:chunk_0", "Pool hours: 8 AM to 10 PM.")])

        client.post("/config", json={"retrieval_mode": "thinking"})

        import src.rag.thinking as thinking

        def fake_generate(prompt, **kwargs):
            if "expert HOA document classifier" in prompt:
                return "[0]"
            return "8 AM to 10 PM."

        monkeypatch.setattr(thinking, "generate", fake_generate)

        resp = client.post("/ask", json={"question": "What are the pool hours?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "8 AM to 10 PM."
        assert "trace" in body["metadata"]  # thinking-mode-only metadata field

    def test_ask_missing_question_field_is_422(self, api_client):
        client, _ = api_client
        resp = client.post("/ask", json={})
        assert resp.status_code == 422

    def test_ask_with_no_documents_does_not_error(self, api_client):
        client, _ = api_client
        resp = client.post("/ask", json={"question": "anything at all"})
        assert resp.status_code == 200
        assert "couldn't find any relevant documents" in resp.json()["answer"]
