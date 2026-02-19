
import re
from Jarvis.core.brain import Brain
from Jarvis.core.tools import Tools

class Orchestrator:
    def __init__(self):
        self.brain = Brain()
        self.tools = Tools()

    def process_command(self, command_text):
        """
        Takes user input and decides whether to handle locally or route to cloud brain.
        """
        # Simple regex based routing for demonstration
        if re.search(r"^\b(cls|dir|ls|cd|pwd)\b", command_text, re.IGNORECASE):
            return self.tools.execute_terminal_command(command_text)
        elif re.search(r"^(run|execute)\s+(.*)", command_text, re.IGNORECASE):
            cmd = re.search(r"^(run|execute)\s+(.*)", command_text, re.IGNORECASE).group(2)
            return self.tools.execute_terminal_command(cmd)
        elif "time" in command_text.lower():
            import datetime
            return f"Current time is {datetime.datetime.now().strftime('%H:%M:%S')}"
        
        # Complex commands route to Gemini
        return self.brain.generate_response(command_text)
