
import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to sys.path explicitly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Jarvis.core.orchestrator import Orchestrator


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        # Patch Brain to avoid real LLM calls during tests
        with patch("Jarvis.core.orchestrator.Brain"):
            self.orchestrator = Orchestrator()
            # Set up mock brain with sensible defaults
            self.orchestrator.brain = MagicMock()
            self.orchestrator.brain.settings = MagicMock()
            self.orchestrator.brain.settings.system_prompt = "You are Jarvis"

    def test_empty_command(self):
        response = self.orchestrator.process_command("")
        self.assertEqual(response, "")

    def test_shell_command_routing(self):
        """'dir' should route directly to shell execution."""
        if os.name == 'nt':
            response = self.orchestrator.process_command("dir")
            # Should contain some output (not route to LLM)
            self.assertTrue(len(response) > 0)

    def test_llm_routing(self):
        """Natural language should route to Brain."""
        self.orchestrator.brain.generate_response = MagicMock(
            return_value="The sky is blue because of Rayleigh scattering."
        )
        response = self.orchestrator.process_command("Explain why the sky is blue")
        self.orchestrator.brain.generate_response.assert_called_once()
        self.assertIn("Rayleigh scattering", response)

    def test_llm_with_shell_tags(self):
        """LLM response with [SHELL] tags should trigger execution."""
        self.orchestrator.brain.generate_response = MagicMock(
            return_value="Here you go.\n[SHELL]echo hello[/SHELL]"
        )
        response = self.orchestrator.process_command("say hello in console")
        self.assertIn("Here you go", response)

    def test_llm_status_command(self):
        self.orchestrator.brain.get_status = MagicMock(return_value={
            "provider": "ollama",
            "model": "gemma:2b",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 512,
            "timeout": 60,
            "system_prompt_preview": "You are Jarvis",
            "memory_messages": 0,
            "health": "connected",
        })

        response = self.orchestrator.process_command("llm status")
        self.assertIn("Brain Status", response)
        self.assertIn("gemma:2b", response)
        self.assertIn("connected", response)

    def test_llm_set_temperature_command(self):
        self.orchestrator.brain.set_option = MagicMock(
            return_value=(True, "temperature set to 1.1.")
        )
        response = self.orchestrator.process_command("llm set temperature 1.1")
        self.orchestrator.brain.set_option.assert_called_once_with("temperature", "1.1")
        self.assertIn("temperature set to 1.1", response)

    def test_llm_use_model_command(self):
        self.orchestrator.brain.set_model = MagicMock(
            return_value=(True, "Model set to 'llama3:latest'.")
        )
        response = self.orchestrator.process_command("llm use llama3:latest")
        self.orchestrator.brain.set_model.assert_called_once_with("llama3:latest")
        self.assertIn("llama3:latest", response)

    def test_llm_models_command(self):
        self.orchestrator.brain.list_local_models = MagicMock(
            return_value=(True, ["gemma:2b", "llama3:latest"])
        )
        response = self.orchestrator.process_command("llm models")
        self.assertIn("Available models", response)
        self.assertIn("gemma:2b", response)

    def test_provider_switch_command(self):
        self.orchestrator.brain.set_provider = MagicMock(
            return_value=(True, "Provider switched to 'gemini'.")
        )
        response = self.orchestrator.process_command("llm provider gemini")
        self.orchestrator.brain.set_provider.assert_called_once_with("gemini")
        self.assertIn("gemini", response)

    def test_llm_reset_command(self):
        self.orchestrator.brain.reset_settings = MagicMock(
            return_value="Brain settings and memory reset to defaults."
        )
        response = self.orchestrator.process_command("llm reset")
        self.assertIn("reset", response.lower())

    def test_clear_memory_command(self):
        self.orchestrator.brain.clear_memory = MagicMock(
            return_value="Conversation memory cleared."
        )
        response = self.orchestrator.process_command("clear memory")
        self.assertIn("memory cleared", response.lower())

    def test_dangerous_command_blocked(self):
        """Dangerous commands from LLM should be blocked."""
        self.orchestrator.brain.generate_response = MagicMock(
            return_value="Formatting drive.\n[SHELL]format c:[/SHELL]"
        )
        response = self.orchestrator.process_command("format my drive")
        self.assertIn("Blocked", response)

    def test_brain_alias_works(self):
        """'brain status' should work the same as 'llm status'."""
        self.orchestrator.brain.get_status = MagicMock(return_value={
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 512,
            "timeout": 60,
            "system_prompt_preview": "You are Jarvis",
            "memory_messages": 5,
            "health": "connected",
        })
        response = self.orchestrator.process_command("brain status")
        self.assertIn("Brain Status", response)


if __name__ == '__main__':
    unittest.main()
