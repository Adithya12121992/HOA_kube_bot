"""Unit tests for src/config/settings.py's shared-config toggle.

Regression coverage for ISSUES_AND_FIXES #11 (config frozen at import time,
not shared across pods) - get_environment()/get_retrieval_mode() must be
called fresh each time, and update_config() must persist to the shared
JSON file so a second "process" (a fresh module import here, standing in
for a second pod) picks up the change.
"""

from __future__ import annotations

import importlib
import sys


class TestConfigDefaults:
    def test_defaults_to_local_and_fast(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        assert settings.get_environment() == "local"
        assert settings.get_retrieval_mode() == "fast"


class TestUpdateConfig:
    def test_update_environment_persists(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        settings.update_config(environment="cloud")
        assert settings.get_environment() == "cloud"

    def test_update_retrieval_mode_persists(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        settings.update_config(retrieval_mode="thinking")
        assert settings.get_retrieval_mode() == "thinking"

    def test_invalid_environment_value_ignored(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        settings.update_config(environment="not-a-real-env")
        assert settings.get_environment() == "local"

    def test_updating_one_field_preserves_the_other(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        settings.update_config(environment="cloud")
        settings.update_config(retrieval_mode="thinking")
        assert settings.get_environment() == "cloud"
        assert settings.get_retrieval_mode() == "thinking"

    def test_visible_to_a_fresh_module_import(self, isolated_data_dir):
        """Stands in for cross-pod visibility: a second process reading the
        same DATA_DIR/config.json must see the update, not a frozen default."""
        settings = isolated_data_dir["settings"]
        settings.update_config(environment="cloud", retrieval_mode="thinking")

        sys.modules.pop("src.config.settings", None)
        settings_reloaded = importlib.import_module("src.config.settings")

        assert settings_reloaded.get_environment() == "cloud"
        assert settings_reloaded.get_retrieval_mode() == "thinking"


class TestStackSummary:
    def test_local_stack_summary(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        stack = settings.get_stack_summary("local")
        assert stack["storage"] == "chromadb"
        assert stack["rag_framework"] == "langgraph"

    def test_cloud_stack_summary(self, isolated_data_dir):
        settings = isolated_data_dir["settings"]
        stack = settings.get_stack_summary("cloud")
        assert stack["storage"] == "pinecone"
        assert stack["rag_framework"] == "llamaindex"
        assert stack["memory"] == "mem0"
