import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "slack-bot"))

import llm  # noqa: E402


class LLMProviderAlignmentTest(unittest.TestCase):
    def test_ollama_provider_does_not_require_openai_credentials(self):
        env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": "http://localhost:11434",
            "OLLAMA_MODEL": "qwen3:8b",
        }
        with patch.dict(os.environ, env, clear=True), \
                patch.object(llm, "is_ollama_available", return_value=True):
            self.assertEqual(llm.get_llm_provider(), "ollama")
            self.assertFalse(llm.is_openai_available())
            self.assertTrue(llm.is_llm_available())

    def test_auto_provider_without_ollama_or_openai_returns_deterministic_fallback(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "auto"}, clear=True), \
                patch.object(llm, "generate_with_ollama", side_effect=llm.LLMUnavailableError("Ollama unavailable")), \
                patch.object(llm, "generate_with_openai", side_effect=llm.LLMUnavailableError("OpenAI credentials are not configured.")):
            response = llm.generate_response("Hello Commander")

        self.assertIn("COMMANDER RUNTIME RESPONSE", response)
        self.assertIn("Runtime reason:", response)

    def test_openai_invalid_auth_is_caught(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "invalid"}, clear=True), \
                patch.object(llm, "generate_with_openai", side_effect=llm.LLMUnavailableError("OpenAI unavailable: AuthenticationError")):
            success, reason = llm.ask_commander_safe(
                system_prompt="System",
                user_prompt="Hello Commander",
            )

        self.assertFalse(success)
        self.assertIn("AuthenticationError", reason)

    def test_startup_provider_check_without_openai_key(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=True), \
                patch.object(llm, "is_ollama_available", return_value=True):
            self.assertTrue(llm.is_llm_configured())

    def test_chief_engineer_routes_to_engineer_model(self):
        with patch.dict(os.environ, {"OLLAMA_ENGINEER_MODEL": "deepseek-coder:6.7b"}, clear=True):
            model = llm.select_ollama_model(
                specialists=["Chief Engineer"],
                user_text="Review repository architecture",
            )

        self.assertEqual(model, "deepseek-coder:6.7b")

    def test_research_officer_routes_to_reasoning_model(self):
        with patch.dict(os.environ, {"OLLAMA_REASONING_MODEL": "deepseek-r1:14b"}, clear=True):
            model = llm.select_ollama_model(
                specialists=["Research Officer"],
                user_text="Perform discovery analysis",
            )

        self.assertEqual(model, "deepseek-r1:14b")

    def test_chief_of_staff_routes_to_commander_model(self):
        with patch.dict(os.environ, {"OLLAMA_COMMANDER_MODEL": "qwen3:8b"}, clear=True):
            model = llm.select_ollama_model(
                specialists=["Chief of Staff"],
                user_text="Recommend next mission",
            )

        self.assertEqual(model, "qwen3:8b")

    def test_ollama_fallback_chain_avoids_embedding_model(self):
        env = {
            "OLLAMA_COMMANDER_MODEL": "qwen3:8b",
            "OLLAMA_FAST_MODEL": "gemma3",
            "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
        }
        with patch.dict(os.environ, env, clear=True):
            chain = llm.ollama_model_fallback_chain("nomic-embed-text")

        self.assertEqual(chain, ["qwen3:8b", "gemma3"])


if __name__ == "__main__":
    unittest.main()
