"""Unit tests for src/rag/store.py's metadata encode/decode helpers.

Pure functions, no ChromaDB/Pinecone connection needed - see
tests/integration/test_store_chromadb.py for the real backend round trip.
"""

from __future__ import annotations

from tests.conftest import make_chunk


class TestPrepareAndRestoreMetadata:
    def test_list_field_json_encoded_not_python_str(self, isolated_data_dir):
        """Regression test (ISSUES_AND_FIXES #4): str(['3.1.2']) produces
        single-quoted output that isn't valid JSON. Must use json.dumps."""
        store = isolated_data_dir["store"]
        chunk = make_chunk("c1", "text", sections=["3.1.2", "4.5"])
        meta = store._prepare_metadata(chunk, include_text=False)
        assert meta["sections"] == '["3.1.2", "4.5"]'

    def test_round_trip_restores_list(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        chunk = make_chunk("c1", "text", sections=["3.1.2", "4.5"])
        meta = store._prepare_metadata(chunk, include_text=False)
        restored = store._restore_metadata(meta)
        assert restored["sections"] == ["3.1.2", "4.5"]

    def test_none_fields_become_empty_string_then_restore_to_none(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        chunk = make_chunk("c1", "text", article=None, section_inherited=None)
        meta = store._prepare_metadata(chunk, include_text=False)
        assert meta["article"] == ""
        restored = store._restore_metadata(meta)
        assert restored["article"] is None
        assert restored["section_inherited"] is None

    def test_int_fields_stay_int(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        chunk = make_chunk("c1", "text", page_start=5, page_end=7, char_start=0, char_end=100)
        meta = store._prepare_metadata(chunk, include_text=False)
        assert meta["page_start"] == 5
        assert isinstance(meta["page_start"], int)

    def test_int_fields_restored_from_string_when_backend_stringifies(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        restored = store._restore_metadata({"page_start": "5", "page_end": "7"})
        assert restored["page_start"] == 5
        assert restored["page_end"] == 7

    def test_chunk_id_excluded_from_metadata(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        chunk = make_chunk("c1", "text")
        meta = store._prepare_metadata(chunk, include_text=False)
        assert "chunk_id" not in meta

    def test_text_included_only_when_requested(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        chunk = make_chunk("c1", "hello world")
        assert "text" not in store._prepare_metadata(chunk, include_text=False)
        assert store._prepare_metadata(chunk, include_text=True)["text"] == "hello world"

    def test_malformed_sections_json_restores_to_empty_list(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        restored = store._restore_metadata({"sections": "not valid json"})
        assert restored["sections"] == []
