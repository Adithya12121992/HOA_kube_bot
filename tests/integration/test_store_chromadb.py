"""Integration tests: real ChromaDB + real BGE embedding model, no mocks.

No API key needed (ChromaDB is on-disk, embedding runs locally) - safe to
run in CI. Pinecone/cloud-backend coverage lives in
test_store_pinecone.py, skipped without PINECONE_API_KEY.
"""

from __future__ import annotations

from tests.conftest import make_chunk


class TestChromaRoundTrip:
    def test_add_then_search_finds_relevant_chunk(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        store.add_chunks([
            make_chunk("doc:chunk_0", "Board meetings are held on the first Tuesday of each month at 6:30 PM."),
            make_chunk("doc:chunk_1", "Pool hours are 8 AM to 10 PM daily, closed Mondays for cleaning."),
        ])

        results = store.search("When does the board meet?", k=1)

        assert len(results) == 1
        assert results[0]["chunk_id"] == "doc:chunk_0"
        assert 0.0 <= results[0]["similarity"] <= 1.0

    def test_search_returns_nothing_on_empty_store(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        assert store.search("anything", k=5) == []

    def test_metadata_round_trips_through_real_backend(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        store.add_chunks([
            make_chunk(
                "doc:chunk_0",
                "Owners must maintain landscaping per Section 9.1.",
                sections=["9.1", "9.2"],
                article="IX",
                page_start=12,
                page_end=13,
            )
        ])
        results = store.search("landscaping rules", k=1)
        assert results[0]["sections"] == ["9.1", "9.2"]
        assert results[0]["article"] == "IX"
        assert results[0]["page_start"] == 12

    def test_upsert_overwrites_same_chunk_id(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Original text about pools.")])
        store.add_chunks([make_chunk("doc:chunk_0", "Updated text about tennis courts.")])

        results = store.search("tennis courts", k=1)
        assert results[0]["chunk_id"] == "doc:chunk_0"
        assert "tennis" in results[0]["text"].lower()

    def test_reset_clears_the_collection(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        store.add_chunks([make_chunk("doc:chunk_0", "Some content here.")])
        assert len(store.search("content", k=5)) == 1

        store.reset()

        assert store.search("content", k=5) == []

    def test_add_chunks_returns_count_written(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        n = store.add_chunks([
            make_chunk("doc:chunk_0", "First chunk."),
            make_chunk("doc:chunk_1", "Second chunk."),
        ])
        assert n == 2

    def test_add_empty_list_is_noop(self, isolated_data_dir):
        store = isolated_data_dir["store"]
        assert store.add_chunks([]) == 0
