#!/usr/bin/env python3
"""Orchestrator for the full HOA RAG document processing pipeline.

Stages:
  1. Ingest: Extract text & images from PDFs
  2. Clean: Boilerplate removal & document concatenation
  3a. Chunk: Hybrid recursive chunking with section extraction
  3b. Store: Embed chunks and store in ChromaDB

Usage:
  python pipeline.py --stage all          # Run all stages
  python pipeline.py --stage ingest       # Run ingest only
  python pipeline.py --stage clean        # Run clean only
  python pipeline.py --stage chunk        # Run chunk only
  python pipeline.py --stage store        # Run store only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Stage modules
import chunk as chunk_module
import store as store_module


def stage_ingest():
    """Stage 1: Extract text & images from PDFs.

    Requires PDFs in ./pdfs/ directory.
    Outputs: extracted.json
    """
    print("=" * 80)
    print("STAGE 1: INGEST (Extract from PDFs)")
    print("=" * 80)
    print("Status: ⚠️ Requires ingest.py module (not included in this repo)")
    print("Action: Place extracted.json in project root, or run full ingest pipeline")
    print("        Expected format: [{'filename': 'doc.pdf', 'text': '...', 'images': [...]}]")
    print()
    return True


def stage_clean():
    """Stage 2: Clean & concatenate documents.

    Reads: extracted.json
    Outputs: documents.json
    """
    print("=" * 80)
    print("STAGE 2: CLEAN (Boilerplate removal & concatenation)")
    print("=" * 80)
    print("Status: ⚠️ Requires clean.py module (not included in this repo)")
    print("Action: Place documents.json in project root with cleaned text")
    print("        Expected format: [{'filename': 'doc.pdf', 'text': '...', 'pages': N}]")
    print()
    return True


def stage_chunk():
    """Stage 3a: Hybrid chunking with section extraction.

    Reads: documents.json
    Outputs: chunks.json
    """
    print("=" * 80)
    print("STAGE 3a: CHUNK (Hybrid recursive chunking)")
    print("=" * 80)

    try:
        chunk_module.main()
        print("✅ Chunking complete")
        return True
    except Exception as e:
        print(f"❌ Chunking failed: {e}")
        return False


def stage_store():
    """Stage 3b: Embed chunks and store in ChromaDB.

    Reads: chunks.json
    Outputs: .chroma_data/
    """
    print("=" * 80)
    print("STAGE 3b: STORE (Embed & vectorize)")
    print("=" * 80)

    try:
        chunks_path = Path("chunks.json")
        if not chunks_path.exists():
            print(f"❌ chunks.json not found. Run stage chunk first.")
            return False

        with open(chunks_path) as f:
            chunks = json.load(f)

        count = store_module.add_chunks(chunks)
        print(f"✅ Stored {count} chunks in ChromaDB")
        return True
    except Exception as e:
        print(f"❌ Storage failed: {e}")
        return False


def main():
    """Parse args and run requested stages."""
    parser = argparse.ArgumentParser(
        description="HOA RAG pipeline orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py --stage all       # Full pipeline
  python pipeline.py --stage chunk     # Skip to chunking
  python pipeline.py --stage store     # Only vectorization
        """
    )
    parser.add_argument(
        "--stage",
        choices=["all", "ingest", "clean", "chunk", "store"],
        default="all",
        help="Pipeline stage(s) to run (default: all)"
    )

    args = parser.parse_args()

    stages_to_run = []
    if args.stage == "all":
        stages_to_run = ["ingest", "clean", "chunk", "store"]
    else:
        stages_to_run = [args.stage]

    print(f"\n{'='*80}")
    print(f"HOA RAG PIPELINE")
    print(f"{'='*80}\n")

    results = {}

    # Run requested stages
    for stage in stages_to_run:
        if stage == "ingest":
            results["ingest"] = stage_ingest()
        elif stage == "clean":
            results["clean"] = stage_clean()
        elif stage == "chunk":
            results["chunk"] = stage_chunk()
        elif stage == "store":
            results["store"] = stage_store()

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    for stage, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{stage:12} {status}")

    all_passed = all(results.values())
    print(f"{'='*80}\n")

    if all_passed:
        print("✅ Pipeline complete! System ready for queries.")
        print("   Run: streamlit run app.py")
    else:
        print("⚠️  Some stages failed. Check messages above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
