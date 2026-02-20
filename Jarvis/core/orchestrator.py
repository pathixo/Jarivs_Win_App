
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
        
        # 0. Output to console (native terminal feel)
        print(f"\n> {command_text}")

        # 1. LLM Meta-commands
        if re.search(r"^llm\b", command_text, re.IGNORECASE):
            return self._handle_llm_command(command_text)

        # 2. Native Shell Commands (Powershell/CMD)
        # Check for common shell commands or explicit "run/exec"
        shell_patterns = [
            r"^\b(cls|dir|ls|cd|pwd|ipconfig|whoami|ping|echo|mkdir|rm|del|copy|move|type|cat|get-process|start|notepad|calc|explorer)\b",
            r"^\b(git|npm|pip|python|node)\b",
            r"^(run|exec|execute)\s+(.*)"
        ]
        
        is_shell = False
        cmd_to_run = command_text
        
        for pattern in shell_patterns:
            match = re.search(pattern, command_text, re.IGNORECASE)
            if match:
                is_shell = True
                if match.groups() and len(match.groups()) >= 2:
                    # If it was "run <cmd>", extract <cmd>
                    cmd_to_run = match.group(2)
                break
        
        if is_shell:
             return self._execute_shell(cmd_to_run)
             
        elif "time" in command_text.lower():
            import datetime
            return f"Current time is {datetime.datetime.now().strftime('%H:%M:%S')}"
            
        # 3. File System Tools (Legacy wrapper, maybe keep for specific syntax)
        elif re.search(r"^read file\s+(.*)", command_text, re.IGNORECASE):
            path = re.search(r"^read file\s+(.*)", command_text, re.IGNORECASE).group(1)
            return self.tools.read_file(path.strip())
        elif re.search(r"^create file\s+(.*?)\s+with content\s+(.*)", command_text, re.IGNORECASE):
            match = re.search(r"^create file\s+(.*?)\s+with content\s+(.*)", command_text, re.IGNORECASE)
            filepath = match.group(1).strip()
            content = match.group(2)
            return self.tools.write_file(filepath, content)
            
        # 4. Complex commands route to Local Brain (Ollama)
        return self.brain.generate_response(command_text)

    def _execute_shell(self, command):
        """Run command in real subprocess and return output."""
        import subprocess
        try:
            # Use powershell for better consistency on Windows
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            output = result.stdout.strip()
            error = result.stderr.strip()
            
            final_out = ""
            if output:
                final_out += output
            if error:
                final_out += f"\nError: {error}"
            
            if not final_out:
                final_out = "Command executed."
                
            print(final_out) # Show in real terminal
            
            # Truncate for TTS if too long
            if len(final_out) > 300:
                short_out = final_out[:300] + "... (output truncated)"
                return short_out
            return final_out
            
        except Exception as e:
            return f"Shell Error: {e}"

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
