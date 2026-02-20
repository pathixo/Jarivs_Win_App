
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
        command_text = command_text.strip()

        if re.search(r"^llm\b", command_text, re.IGNORECASE):
            return self._handle_llm_command(command_text)

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

    def _handle_llm_command(self, command_text):
        help_text = (
            "LLM Controls:\n"
            "- llm status\n"
            "- llm models\n"
            "- llm use <model_name>\n"
            "- llm set temperature <0..2>\n"
            "- llm set top_p <0..1>\n"
            "- llm set max_tokens <int>\n"
            "- llm set timeout <seconds>\n"
            "- llm prompt show\n"
            "- llm prompt set <text>\n"
            "- llm reset"
        )

        if re.search(r"^llm\s+help$", command_text, re.IGNORECASE):
            return help_text

        if re.search(r"^llm\s+status$", command_text, re.IGNORECASE):
            status = self.brain.get_status()
            return (
                "LLM Status:\n"
                f"- url: {status['url']}\n"
                f"- model: {status['model']}\n"
                f"- temperature: {status['temperature']}\n"
                f"- top_p: {status['top_p']}\n"
                f"- max_tokens: {status['max_tokens']}\n"
                f"- timeout: {status['timeout']}s\n"
                f"- system_prompt_preview: {status['system_prompt_preview']}"
            )

        if re.search(r"^llm\s+models$", command_text, re.IGNORECASE):
            ok, result = self.brain.list_local_models()
            if not ok:
                return result
            if not result:
                return "No local Ollama models found."
            return "Available local models:\n- " + "\n- ".join(result)

        use_match = re.search(r"^llm\s+use\s+(.+)$", command_text, re.IGNORECASE)
        if use_match:
            model_name = use_match.group(1).strip()
            ok, message = self.brain.set_model(model_name)
            return message

        set_match = re.search(r"^llm\s+set\s+(temperature|top_p|max_tokens|timeout)\s+(.+)$", command_text, re.IGNORECASE)
        if set_match:
            option_name = set_match.group(1).strip().lower()
            raw_value = set_match.group(2).strip()
            ok, message = self.brain.set_option(option_name, raw_value)
            return message

        if re.search(r"^llm\s+prompt\s+show$", command_text, re.IGNORECASE):
            return self.brain.system_prompt

        prompt_set_match = re.search(r"^llm\s+prompt\s+set\s+(.+)$", command_text, re.IGNORECASE)
        if prompt_set_match:
            prompt_text = prompt_set_match.group(1)
            ok, message = self.brain.set_system_prompt(prompt_text)
            return message

        if re.search(r"^llm\s+reset$", command_text, re.IGNORECASE):
            return self.brain.reset_settings()

        return help_text
