"""
Orchestrator Module — Command Router & Execution Engine
========================================================
Central coordinator that receives user input and decides how to handle it:

  1. Meta-commands (llm/brain control)  →  Internal settings management
  2. Direct shell patterns              →  PowerShell subprocess execution  
  3. Natural language                   →  Brain (LLM) processing
     └─ LLM may return [SHELL] tags    →  Extracted and executed safely

Features:
  - Structured intent classification
  - Safety-aware shell execution with sandboxing
  - Conversation context awareness
  - Proper error handling and logging
  - Colorized terminal output
  - Output formatting for TTS compatibility
"""

import logging
import re
import subprocess
import time
from typing import Optional

from Jarvis.core.brain import Brain, Provider
from Jarvis.core.tools import Tools
from Jarvis.core import colors as clr

logger = logging.getLogger("jarvis.orchestrator")


# ─────────────────────────── Constants ──────────────────────────────────────

# Commands that are safe to run directly (no LLM needed)
DIRECT_SHELL_PATTERNS = [
    # Common shell builtins / utilities (must START with the command)
    r"^(cls|dir|ls|cd|pwd|ipconfig|whoami|ping|echo|mkdir|rm|rmdir|del|copy|"
    r"move|type|cat|ren|rename|attrib|tree|find|findstr|sort|more|fc|comp|xcopy|"
    r"tasklist|taskkill|systeminfo|hostname|netstat|nslookup|tracert|shutdown|"
    r"get-process|get-service|get-childitem|set-location|get-content|"
    r"select-object|where-object|format-table|format-list|out-file|"
    r"start-process|stop-process|restart-service|get-date)\b",
    # Dev tools
    r"^(git|npm|npx|pip|python|node|docker|cargo|go|rustc|javac|java|dotnet)\b",
    # App launchers
    r"^(notepad|calc|explorer|code|chrome|firefox|edge|mspaint|cmd|powershell)\b",
]

# Dangerous commands that need extra caution
DANGEROUS_PATTERNS = [
    r"format\s+[a-z]:",
    r"remove-item\s+.*-recurse",
    r"rm\s+-rf",
    r"del\s+/[sS]",
    r"shutdown\s+/[sSpP]",
    r"reg\s+delete",
    r"diskpart",
    r"bcdedit",
]

# Maximum output length before truncation (for TTS)
MAX_OUTPUT_LENGTH = 500
MAX_TTS_LENGTH = 300


class Orchestrator:
    """
    Central command router. Owns Brain + Tools and handles all user input.
    """

    def __init__(self, worker=None):
        self.brain = Brain()
        self.tools = Tools()
        self.worker = worker
        logger.info("Orchestrator initialized")

    # ── Main Entry Point ────────────────────────────────────────────────────

    def process_command(self, command_text: str) -> str:
        """
        Main entry: classify intent → route → execute → format response.
        
        Returns a string suitable for both terminal display and TTS.
        """
        command_text = (command_text or "").strip()
        if not command_text:
            return ""

        logger.info("Processing command: %s", command_text[:80])
        print()
        print(clr.divider())
        clr.print_user(command_text)

        try:
            # 1. Meta-commands: "llm ..." or "brain ..."
            if re.search(r"^(llm|brain)\b", command_text, re.IGNORECASE):
                result = self._handle_meta_command(command_text)
                print(clr.info(result))
                return result

            # 2. Memory commands
            if re.search(r"^(clear memory|forget|reset memory)$", command_text, re.IGNORECASE):
                result = self.brain.clear_memory()
                print(clr.info(result))
                return result

            # 3. Direct shell command detection
            shell_cmd = self._detect_shell_command(command_text)
            if shell_cmd:
                clr.print_shell(shell_cmd)
                result = self._execute_shell(shell_cmd)
                return result

            # 4. Route to Brain (LLM) for everything else
            return self._process_with_llm(command_text)

        except Exception as e:
            logger.error("Command processing failed: %s", e, exc_info=True)
            clr.print_error(str(e))
            return f"Error processing command: {e}"

    # ── Intent Detection ────────────────────────────────────────────────────

    def _detect_shell_command(self, text: str) -> Optional[str]:
        """
        Check if the input is a direct shell command.
        Returns the command to run, or None if it should go to the LLM.
        """
        for pattern in DIRECT_SHELL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return text
        return None

    # ── LLM Processing ──────────────────────────────────────────────────────

    def _process_with_llm(self, command_text: str) -> str:
        """
        Send to Brain, parse response, execute any [SHELL] commands found.
        """
        t0 = time.time()
        clr.print_debug(f"  Thinking...")
        llm_response = self.brain.generate_response(command_text)
        elapsed = time.time() - t0
        clr.print_debug(f"  Response in {elapsed:.2f}s")

        logger.info("LLM responded in %.2fs (%d chars)", elapsed, len(llm_response))

        if not llm_response:
            clr.print_error("No response received.")
            return "I didn't get a response. Please try again."

        # Check for [SHELL] commands in the response
        shell_commands = re.findall(r'\[SHELL\](.*?)\[/SHELL\]', llm_response, re.DOTALL)

        if not shell_commands:
            # Pure conversational response
            clr.print_ai(llm_response)
            return llm_response

        # Extract the conversational part (text outside [SHELL] tags)
        clean_text = re.sub(r'\[SHELL\].*?\[/SHELL\]', '', llm_response, flags=re.DOTALL).strip()

        results = []
        if clean_text:
            clr.print_ai(clean_text)
            results.append(clean_text)

        for cmd in shell_commands:
            cmd = cmd.strip()
            if not cmd:
                continue

            # Safety check
            if self._is_dangerous_command(cmd):
                logger.warning("Dangerous command blocked: %s", cmd)
                msg = f"Blocked dangerous command: `{cmd}`. Please run manually if intended."
                clr.print_warning(f"⚠️  {msg}")
                results.append(msg)
                continue

            logger.info("Executing LLM-generated shell command: %s", cmd)
            clr.print_shell(cmd)

            shell_output = self._execute_shell(cmd, from_llm=True)
            if shell_output and shell_output != "Command executed.":
                results.append(f"Output:\n{shell_output}")
            else:
                results.append(f"Done: {cmd}")

        return "\n".join(results)

    # ── Shell Execution ─────────────────────────────────────────────────────

    def _execute_shell(self, command: str, from_llm: bool = False) -> str:
        """
        Execute a command in PowerShell subprocess.
        
        Args:
            command: The PowerShell command to run.
            from_llm: If True, this command came from LLM output (extra safety).
        """
        logger.info("Shell exec%s: %s", " (from LLM)" if from_llm else "", command)

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=30,  # Hard timeout to prevent hanging
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            output = result.stdout.strip()
            error = result.stderr.strip()

            final_out = ""
            if output:
                final_out += output
            if error:
                # Filter out common PowerShell noise
                if not self._is_noise(error):
                    final_out += f"\nError: {error}" if final_out else f"Error: {error}"

            if not final_out:
                final_out = "Command executed."
                clr.print_info("Command executed.")
            else:
                # Print output with shell output color
                clr.print_shell_output(final_out)

            if self.worker:
                self.worker.output_ready.emit(final_out)

            # Truncate for TTS if needed
            if len(final_out) > MAX_OUTPUT_LENGTH:
                return final_out[:MAX_TTS_LENGTH] + "... (output truncated)"

            return final_out

        except subprocess.TimeoutExpired:
            msg = "Command timed out after 30 seconds."
            logger.warning("Shell command timed out: %s", command)
            clr.print_warning(msg)
            return msg
        except FileNotFoundError:
            msg = "Error: PowerShell not found. Is it installed?"
            clr.print_error(msg)
            return msg
        except Exception as e:
            logger.error("Shell execution error: %s", e)
            clr.print_error(f"Shell Error: {e}")
            return f"Shell Error: {e}"

    # ── Safety ──────────────────────────────────────────────────────────────

    @staticmethod
    def _is_dangerous_command(command: str) -> bool:
        """Check if a command could be destructive."""
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _is_noise(stderr: str) -> bool:
        """Filter out non-error PowerShell stderr output."""
        noise_patterns = [
            r"^WARNING:",
            r"^VERBOSE:",
            r"^DEBUG:",
            r"^ProgressPreference",
        ]
        for pattern in noise_patterns:
            if re.search(pattern, stderr, re.IGNORECASE):
                return True
        return False

    # ── Meta-Commands (llm/brain control) ───────────────────────────────────

    def _handle_meta_command(self, command_text: str) -> str:
        """Handle llm/brain configuration commands."""

        help_text = (
            "Brain Controls:\n"
            "─────────────────────────────────────\n"
            "  llm status           — Show current config & health\n"
            "  llm models           — List available models\n"
            "  llm use <model>      — Switch model\n"
            "  llm provider <name>  — Switch provider (ollama/gemini/groq/grok)\n"
            "  llm set temperature <0..2>\n"
            "  llm set top_p <0..1>\n"
            "  llm set max_tokens <int>\n"
            "  llm set timeout <seconds>\n"
            "  llm prompt show      — Show system prompt\n"
            "  llm prompt set <text>— Set system prompt\n"
            "  llm reset            — Reset all settings\n"
            "  clear memory         — Clear conversation memory\n"
        )

        # Help
        if re.search(r"^(llm|brain)\s+help$", command_text, re.IGNORECASE):
            return help_text

        # Status
        if re.search(r"^(llm|brain)\s+status$", command_text, re.IGNORECASE):
            status = self.brain.get_status()
            health_icon = "+" if status["health"] == "connected" else "x"
            return (
                "Brain Status:\n"
                f"  [{health_icon}] Health:     {status['health']}\n"
                f"  Provider:    {status['provider']}\n"
                f"  Model:       {status['model']}\n"
                f"  Temperature: {status['temperature']}\n"
                f"  Top-P:       {status['top_p']}\n"
                f"  Max Tokens:  {status['max_tokens']}\n"
                f"  Timeout:     {status['timeout']}s\n"
                f"  Memory:      {status['memory_messages']} messages\n"
                f"  Prompt:      {status['system_prompt_preview']}..."
            )

        # List models
        if re.search(r"^(llm|brain)\s+models$", command_text, re.IGNORECASE):
            ok, result = self.brain.list_local_models()
            if not ok:
                return f"Error: {result}"
            if not result:
                return "No models found for current provider."
            return "Available models:\n  - " + "\n  - ".join(result)

        # Switch provider
        provider_match = re.search(
            r"^(llm|brain)\s+provider\s+(.+)$", command_text, re.IGNORECASE
        )
        if provider_match:
            provider_name = provider_match.group(2).strip()
            ok, message = self.brain.set_provider(provider_name)
            return message

        # Switch model
        use_match = re.search(r"^(llm|brain)\s+use\s+(.+)$", command_text, re.IGNORECASE)
        if use_match:
            model_name = use_match.group(2).strip()
            ok, message = self.brain.set_model(model_name)
            return message

        # Set option
        set_match = re.search(
            r"^(llm|brain)\s+set\s+(temperature|top_p|max_tokens|timeout)\s+(.+)$",
            command_text, re.IGNORECASE,
        )
        if set_match:
            option_name = set_match.group(2).strip().lower()
            raw_value = set_match.group(3).strip()
            ok, message = self.brain.set_option(option_name, raw_value)
            return message

        # Show system prompt
        if re.search(r"^(llm|brain)\s+prompt\s+show$", command_text, re.IGNORECASE):
            return f"System Prompt:\n\n{self.brain.settings.system_prompt}"

        # Set system prompt
        prompt_match = re.search(
            r"^(llm|brain)\s+prompt\s+set\s+(.+)$", command_text, re.IGNORECASE
        )
        if prompt_match:
            prompt_text = prompt_match.group(2)
            ok, message = self.brain.set_system_prompt(prompt_text)
            return message

        # Reset
        if re.search(r"^(llm|brain)\s+reset$", command_text, re.IGNORECASE):
            return self.brain.reset_settings()

        # Unknown subcommand → show help
        return help_text
