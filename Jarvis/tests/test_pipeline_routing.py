"""
Pipeline Routing Tests — Three-Tier Auto-Select
=================================================
Verifies that the Brain's _select_model_for_query() correctly routes
queries to the appropriate model tier and falls back gracefully.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _make_mock_persona(name="witty", display_name="Witty JARVIS",
                       description="British wit", voice="en-GB-RyanNeural",
                       tts_rate="+10%", system_prompt="You are Jarvis"):
    """Create a mock PersonaProfile."""
    mock = MagicMock()
    mock.name = name
    mock.display_name = display_name
    mock.description = description
    mock.voice = voice
    mock.tts_rate = tts_rate
    mock.system_prompt = system_prompt
    return mock


class TestPipelineRouting(unittest.TestCase):
    """Test the three-tier auto-select pipeline in Brain."""

    @patch("Jarvis.core.brain.OLLAMA_AUTO_SELECT", True)
    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    @patch("Jarvis.core.brain.OLLAMA_LOGIC_MODEL", "llama3.2:3b")
    @patch("Jarvis.core.brain.OLLAMA_CLOUD_FALLBACK", False)
    @patch("Jarvis.core.brain.PersonaManager")
    def setUp(self, MockPM):
        """Set up a Brain instance with mocked backends."""
        mock_pm = MockPM.return_value
        mock_pm.get_active.return_value = _make_mock_persona()
        mock_pm.get_active_name.return_value = "witty"

        with patch("Jarvis.core.brain._OllamaBackend"), \
             patch("Jarvis.core.brain._GeminiBackend"), \
             patch("Jarvis.core.brain._GroqBackend"), \
             patch("Jarvis.core.brain._GrokBackend"):
            from Jarvis.core.brain import Brain
            self.brain = Brain(provider="ollama")

        # Default: all models available
        self.brain._is_model_available = MagicMock(return_value=True)

    # ── Tier 1 (Action) Tests ───────────────────────────────────────────────

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_open_chrome(self):
        """'open chrome' should route to Tier 1 (Action model)."""
        result = self.brain._select_model_for_query("open chrome")
        self.assertEqual(result, "jarvis-action")

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_launch_spotify(self):
        """'launch spotify' should route to Tier 1."""
        result = self.brain._select_model_for_query("launch spotify")
        self.assertEqual(result, "jarvis-action")

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_create_folder(self):
        """'create a folder named test' should route to Tier 1."""
        result = self.brain._select_model_for_query("create a folder named test")
        self.assertEqual(result, "jarvis-action")

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_open_url(self):
        """'open youtube' should route to Tier 1."""
        result = self.brain._select_model_for_query("open youtube")
        self.assertEqual(result, "jarvis-action")

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_screenshot(self):
        """'take a screenshot' should route to Tier 1."""
        result = self.brain._select_model_for_query("take a screenshot")
        self.assertEqual(result, "jarvis-action")

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_play_music(self):
        """'play music' should route to Tier 1 (new pattern)."""
        result = self.brain._select_model_for_query("play some music")
        self.assertEqual(result, "jarvis-action")

    # ── Tier 1 Fallback ─────────────────────────────────────────────────────

    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_action_fallback_to_fast(self):
        """If action model unavailable, fall back to fast model."""
        def model_check(name):
            return name != "jarvis-action"  # action model missing
        self.brain._is_model_available = MagicMock(side_effect=model_check)

        result = self.brain._select_model_for_query("open chrome")
        self.assertEqual(result, "gemma:2b")

    # ── Tier 2 (General) Tests ──────────────────────────────────────────────

    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_general_hello(self):
        """Simple greeting should route to Tier 2 (fast model)."""
        result = self.brain._select_model_for_query("hello")
        self.assertEqual(result, "gemma:2b")

    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_general_how_are_you(self):
        """'how are you' should route to Tier 2."""
        result = self.brain._select_model_for_query("how are you doing today")
        self.assertEqual(result, "gemma:2b")

    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_general_joke(self):
        """'tell me a joke' should route to Tier 2."""
        result = self.brain._select_model_for_query("tell me a joke")
        self.assertEqual(result, "gemma:2b")

    # ── Tier 3 (Logic) Tests ────────────────────────────────────────────────

    @patch("Jarvis.core.brain.OLLAMA_LOGIC_MODEL", "llama3.2:3b")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_logic_explain_algorithm(self):
        """'explain the binary search algorithm' should route to Tier 3."""
        result = self.brain._select_model_for_query("explain the binary search algorithm step by step")
        self.assertEqual(result, "llama3.2:3b")

    @patch("Jarvis.core.brain.OLLAMA_LOGIC_MODEL", "llama3.2:3b")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_logic_write_code(self):
        """'write a function to sort a list' should route to Tier 3."""
        result = self.brain._select_model_for_query("write a function to sort a list using merge sort")
        self.assertEqual(result, "llama3.2:3b")

    @patch("Jarvis.core.brain.OLLAMA_LOGIC_MODEL", "llama3.2:3b")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_logic_long_query(self):
        """Long queries (20+ words) should route to Tier 3."""
        long_query = " ".join(["word"] * 25)
        result = self.brain._select_model_for_query(long_query)
        self.assertEqual(result, "llama3.2:3b")

    @patch("Jarvis.core.brain.OLLAMA_LOGIC_MODEL", "llama3.2:3b")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    def test_logic_fallback_to_fast(self):
        """If logic model unavailable, fall back to fast model."""
        def model_check(name):
            return name != "llama3.2:3b"  # logic model missing
        self.brain._is_model_available = MagicMock(side_effect=model_check)

        result = self.brain._select_model_for_query("explain how TCP works in detail")
        self.assertEqual(result, "gemma:2b")

    # ── Pipeline Status ─────────────────────────────────────────────────────

    @patch("Jarvis.core.brain.OLLAMA_AUTO_SELECT", True)
    @patch("Jarvis.core.brain.OLLAMA_CLOUD_FALLBACK", True)
    @patch("Jarvis.core.brain.OLLAMA_ACTION_MODEL", "jarvis-action")
    @patch("Jarvis.core.brain.OLLAMA_FAST_MODEL", "gemma:2b")
    @patch("Jarvis.core.brain.OLLAMA_LOGIC_MODEL", "llama3.2:3b")
    def test_pipeline_status(self):
        """get_pipeline_status() should return all tier info."""
        status = self.brain.get_pipeline_status()
        self.assertTrue(status["auto_select"])
        self.assertTrue(status["cloud_fallback"])
        self.assertEqual(status["action_model"], "jarvis-action")
        self.assertEqual(status["fast_model"], "gemma:2b")
        self.assertEqual(status["logic_model"], "llama3.2:3b")
        self.assertIn("current_provider", status)
        self.assertIn("current_model", status)


class TestPipelineOrchestratorCommand(unittest.TestCase):
    """Test the llm pipeline meta-commands in the Orchestrator."""

    @patch("Jarvis.core.brain.PersonaManager")
    def setUp(self, MockPM):
        mock_pm = MockPM.return_value
        mock_pm.get_active.return_value = _make_mock_persona()
        mock_pm.get_active_name.return_value = "witty"

        with patch("Jarvis.core.brain._OllamaBackend"), \
             patch("Jarvis.core.brain._GeminiBackend"), \
             patch("Jarvis.core.brain._GroqBackend"), \
             patch("Jarvis.core.brain._GrokBackend"), \
             patch("Jarvis.core.system.get_backend") as mock_backend:
            mock_backend.return_value = MagicMock()
            from Jarvis.core.orchestrator import Orchestrator
            self.orch = Orchestrator()
            self.orch.brain._is_model_available = MagicMock(return_value=True)

    def test_pipeline_status_command(self):
        """'llm pipeline' should return pipeline status info."""
        result = self.orch.process_command("llm pipeline")
        self.assertIn("Three-Tier Pipeline", result)
        self.assertIn("Auto-Select", result)
        self.assertIn("Tier 1", result)
        self.assertIn("Tier 2", result)
        self.assertIn("Tier 3", result)

    @patch("Jarvis.config.OLLAMA_AUTO_SELECT", True)
    def test_pipeline_toggle_off(self):
        """'llm pipeline off' should disable auto-select."""
        result = self.orch.process_command("llm pipeline off")
        self.assertIn("disabled", result)

    @patch("Jarvis.config.OLLAMA_AUTO_SELECT", False)
    def test_pipeline_toggle_on(self):
        """'llm pipeline on' should enable auto-select."""
        result = self.orch.process_command("llm pipeline on")
        self.assertIn("enabled", result)


if __name__ == '__main__':
    unittest.main()
