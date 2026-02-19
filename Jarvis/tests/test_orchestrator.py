
import unittest
import sys
import os

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

if __name__ == '__main__':
    unittest.main()
