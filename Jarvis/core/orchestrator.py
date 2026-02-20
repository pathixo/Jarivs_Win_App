
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
        
        # File System Tools
        elif re.search(r"^(list files|ls|dir)\s+(.*)", command_text, re.IGNORECASE):
            path = re.search(r"^(list files|ls|dir)\s+(.*)", command_text, re.IGNORECASE).group(2)
            return self.tools.list_files(path.strip())
        elif re.search(r"^read file\s+(.*)", command_text, re.IGNORECASE):
            path = re.search(r"^read file\s+(.*)", command_text, re.IGNORECASE).group(1)
            return self.tools.read_file(path.strip())
        elif re.search(r"^create file\s+(.*?)\s+with content\s+(.*)", command_text, re.IGNORECASE):
            match = re.search(r"^create file\s+(.*?)\s+with content\s+(.*)", command_text, re.IGNORECASE)
            filepath = match.group(1).strip()
            content = match.group(2)
            return self.tools.write_file(filepath, content)
            
        # Complex commands route to Local Brain (Ollama)
        return self.brain.generate_response(command_text)
