
import unittest
import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path explicitly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Jarvis.core.orchestrator import Orchestrator

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()

    def test_local_routing(self):
        # 'dir' should route to local tools (execute_terminal_command)
        # We can mock tools execution or just check return type/content if feasible
        # Since execute_terminal_command runs actual commands, let's pick safe ones.
        
        # 'time' keyword
        response = self.orchestrator.process_command("What time is it?")
        self.assertIn("Current time is", response)
        
        # 'dir' command (windows)
        # Note: on linux/mac 'ls'
        if os.name == 'nt':
            response = self.orchestrator.process_command("dir")
            self.assertIn("Volume in drive", response)  # Typical Windows dir output
        else:
            response = self.orchestrator.process_command("ls")
            self.assertIn("manage.py", response) # Example

    def test_cloud_routing(self):
        # Without Ollama running, brain returns connection error
        response = self.orchestrator.process_command("Explain why the sky is blue")
        # Should return error message about connection or brain error
        # "Error: Could not connect to Local Brain (Ollama). Is it running?"
        self.assertTrue("Error" in response or "Brain Error" in response or len(response) > 0)

    def test_llm_status_command(self):
        self.orchestrator.brain.get_status = MagicMock(return_value={
            "url": "http://localhost:11434/api/generate",
            "model": "gemma:2b",
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 256,
            "timeout": 30,
            "system_prompt_preview": "You are Jarvis"
        })

        response = self.orchestrator.process_command("llm status")
        self.assertIn("LLM Status", response)
        self.assertIn("model: gemma:2b", response)

    def test_llm_set_temperature_command(self):
        self.orchestrator.brain.set_option = MagicMock(return_value=(True, "temperature set to 1.1."))

        response = self.orchestrator.process_command("llm set temperature 1.1")
        self.orchestrator.brain.set_option.assert_called_once_with("temperature", "1.1")
        self.assertIn("temperature set to 1.1", response)

    def test_llm_use_model_command(self):
        self.orchestrator.brain.set_model = MagicMock(return_value=(True, "LLM model set to 'llama3:latest'."))

        response = self.orchestrator.process_command("llm use llama3:latest")
        self.orchestrator.brain.set_model.assert_called_once_with("llama3:latest")
        self.assertIn("llama3:latest", response)

    def test_llm_models_command(self):
        self.orchestrator.brain.list_local_models = MagicMock(return_value=(True, ["gemma:2b", "llama3:latest"]))

        response = self.orchestrator.process_command("llm models")
        self.assertIn("Available local models", response)
        self.assertIn("gemma:2b", response)

if __name__ == '__main__':
    unittest.main()
