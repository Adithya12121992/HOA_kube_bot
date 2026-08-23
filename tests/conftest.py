"""Shared pytest fixtures.

Tests that touch DATA_DIR/CHROMA_DB_PATH-backed state (config toggle,
ChromaDB) use `isolated_data_dir` so runs never read/write the real
project's /data or .chroma_data - each test gets its own throwaway
directory and a fresh settings/store module import (both cache clients
and config paths at import time in a couple of places, so a plain
monkeypatch.setenv after import wouldn't be picked up).
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    chroma_dir = tmp_path / "chroma"
    data_dir.mkdir()
    chroma_dir.mkdir()

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CHROMA_DB_PATH", str(chroma_dir))
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("RETRIEVAL_MODE", "fast")

    # query.py/thinking.py/memory.py do `from src.rag.store import search` /
    # `from src.config.settings import get_environment` - name bindings frozen
    # to whatever module instance existed at first import. In a real
    # deployment each process imports once, so this never matters - but
    # across tests in one process, a cached query/thinking module would keep
    # pointing at a previous test's (different-tmp-path) store instance.
    # Reload the whole dependency chain together so every test gets a
    # consistent, freshly-wired set of modules.
    reload_order = [
        "src.config.settings",
        "src.rag.store",
        "src.rag.memory",
        "src.rag.query",
        "src.rag.thinking",
    ]
    for mod_name in reload_order:
        sys.modules.pop(mod_name, None)

    settings = importlib.import_module("src.config.settings")
    store = importlib.import_module("src.rag.store")
    importlib.import_module("src.rag.memory")
    importlib.import_module("src.rag.query")
    importlib.import_module("src.rag.thinking")

    yield {"data_dir": data_dir, "chroma_dir": chroma_dir, "settings": settings, "store": store}

    for mod_name in reload_order:
        sys.modules.pop(mod_name, None)


def make_chunk(chunk_id: str, text: str, **overrides) -> dict:
    chunk = {
        "chunk_id": chunk_id,
        "text": text,
        "source": overrides.pop("source", "test_doc.pdf"),
        "doc_type": overrides.pop("doc_type", "governing"),
        "sections": overrides.pop("sections", []),
        "section_inherited": overrides.pop("section_inherited", None),
        "article": overrides.pop("article", None),
        "page_start": overrides.pop("page_start", 1),
        "page_end": overrides.pop("page_end", 1),
        "char_start": overrides.pop("char_start", 0),
        "char_end": overrides.pop("char_end", len(text)),
    }
    chunk.update(overrides)
    return chunk
