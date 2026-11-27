"""The Telegram cloud tier reads OLLAMA_CLOUD_* only; the capture worker is local and reads neither."""
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from telegram_bots import llm

LOCAL = {"OLLAMA_BASE_URL": "http://localhost:11434", "OLLAMA_MODEL": "gemma4:12b"}


class TelegramLlmCloudEnvTests(unittest.TestCase):
    def test_local_settings_do_not_leak_into_the_cloud_tier(self):
        with patch.dict(os.environ, LOCAL, clear=False):
            for k in ("OLLAMA_CLOUD_BASE_URL", "OLLAMA_CLOUD_MODEL"):
                os.environ.pop(k, None)
            self.assertEqual(llm._cloud_base_url(), "https://ollama.com")
            self.assertEqual(llm._cloud_model(), "glm-5.2")

    def test_cloud_settings_override_the_defaults(self):
        env = {**LOCAL, "OLLAMA_CLOUD_BASE_URL": "https://cloud.example/", "OLLAMA_CLOUD_MODEL": "glm-9"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(llm._cloud_base_url(), "https://cloud.example")
            self.assertEqual(llm._cloud_model(), "glm-9")


class EnrichmentWorkerLocalOnlyTests(unittest.TestCase):
    """Captured text is private: the worker reads the local settings and ignores the cloud ones."""

    def test_cloud_settings_are_ignored(self):
        env = {**LOCAL, "OLLAMA_CLOUD_BASE_URL": "https://cloud.example", "OLLAMA_CLOUD_MODEL": "glm-9"}
        with patch.dict(os.environ, env, clear=False):
            sys.modules.pop("core.capture.enrichment_worker", None)
            mod = importlib.import_module("core.capture.enrichment_worker")
        self.assertEqual(mod.OLLAMA_BASE, "http://localhost:11434")
        self.assertEqual(mod.OLLAMA_MODEL, "gemma4:12b")


if __name__ == "__main__":
    unittest.main()
