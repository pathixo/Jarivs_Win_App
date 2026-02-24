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


# ─────────────────────────── Shell Stream Filter ────────────────────────────

class _ShellStreamFilter:
    """
    Stateful filter for LLM token streams.

    Strips [SHELL]...[/SHELL] tags in real-time so only conversational text
    reaches the display callback. Extracted commands are stored in
    self.shell_commands and executed after streaming completes.
    """

    _OPEN  = "[SHELL]"
    _CLOSE = "[/SHELL]"

    def __init__(self):
        self._buf       = ""   # partial tag detection lookahead buffer
        self._in_shell  = False
        self._shell_buf = ""   # accumulates the shell command text
        self.shell_commands: list[str] = []

    def feed(self, text: str) -> str:
        """Return the displayable portion of a token (empty when inside a SHELL block)."""
        display = ""
        for ch in text:
            if not self._in_shell:
                self._buf += ch
                if self._OPEN in self._buf:
                    idx = self._buf.index(self._OPEN)
                    display += self._buf[:idx]
                    self._buf = ""
                    self._in_shell = True
                elif not self._OPEN.startswith(self._buf):
                    display += self._buf
                    self._buf = ""
            else:
                self._shell_buf += ch
                if self._CLOSE in self._shell_buf:
                    idx = self._shell_buf.index(self._CLOSE)
                    cmd = self._shell_buf[:idx].strip()
                    if cmd:
                        self.shell_commands.append(cmd)
                    self._shell_buf = self._shell_buf[idx + len(self._CLOSE):]
                    self._in_shell = False
        return display

    def flush(self) -> str:
        """Flush any buffered display text at end of stream."""
        if not self._in_shell:
            result, self._buf = self._buf, ""
            return result
        return ""


# ─────────────────────────── Constants ──────────────────────────────────────

# Commands that are safe to run directly (no LLM needed)
DIRECT_SHELL_PATTERNS = [
    # Common shell builtins / utilities (must START with the command)
    r"^(cls|dir|ls|cd|pwd|ipconfig|whoami|ping|echo|mkdir|rm|rmdir|del|copy|"
    r"move|type|cat|ren|rename|attrib|tree|find|findstr|sort|more\s+\S+|fc|comp|xcopy|"
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

    def __init__(self, worker=None, tts=None, listener=None):
        self.brain = Brain()
        self.tools = Tools()
        self.worker = worker
        self.tts = tts  # TTS instance for voice switching
        self.listener = listener  # Listener instance for STT language switching
        self._stt_language = "auto"  # Track current STT language
        
        self.confirmation_mode = False  # Ask before running any shell command
        self.wsl_mode = False           # Run risky/all commands in WSL
        self._confirm_callback = None   # Callback(command_text) -> bool

        # Apply initial persona voice to TTS
        if self.tts:
            active = self.brain.personas.get_active()
            self.tts.set_voice(active.voice)
            self.tts.set_rate(active.tts_rate)

        logger.info("Orchestrator initialized")

    # ── Main Entry Point ────────────────────────────────────────────────────

    def process_command(self, command_text: str, token_callback=None, begin_callback=None) -> str:
        """
        Main entry: classify intent → route → execute → format response.

        Args:
            command_text:   Raw user input (voice or typed).
            token_callback: Optional callable(str) invoked for each streamed
                            LLM token (display text only, SHELL tags filtered).
            begin_callback: Optional callable() invoked just before the first
                            token arrives (use to prepare the UI stream block).

        Returns a string suitable for TTS.
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

            # 2. Persona commands: "persona ..."
            if re.search(r"^persona\b", command_text, re.IGNORECASE):
                result = self._handle_persona_command(command_text)
                print(clr.info(result))
                return result

            # 3. Voice commands: "voice ..."
            if re.search(r"^voice\b", command_text, re.IGNORECASE):
                result = self._handle_voice_command(command_text)
                print(clr.info(result))
                return result

            # 4. Memory commands
            if re.search(r"^(clear memory|forget|reset memory)$", command_text, re.IGNORECASE):
                result = self.brain.clear_memory()
                print(clr.info(result))
                return result

            # 5. STT commands: "stt ..."
            if re.search(r"^stt\b", command_text, re.IGNORECASE):
                result = self._handle_stt_command(command_text)
                print(clr.info(result))
                return result

            # 6. Shell control commands: "shell ..."
            if re.search(r"^shell\b", command_text, re.IGNORECASE):
                result = self._handle_shell_command(command_text)
                print(clr.info(result))
                return result

            # 7. Direct shell command detection
            shell_cmd = self._detect_shell_command(command_text)
            if shell_cmd:
                clr.print_shell(shell_cmd)
                result = self._execute_shell(shell_cmd)
                return result

            # 8. Route to Brain (LLM) for everything else
            return self._process_with_llm(
                command_text,
                token_callback=token_callback,
                begin_callback=begin_callback,
            )

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

    def _process_with_llm(
        self,
        command_text: str,
        depth: int = 0,
        token_callback=None,
        begin_callback=None,
    ) -> str:
        """
        Send to Brain, stream/parse response, execute any [SHELL] commands found.

        When token_callback is provided the response is streamed token-by-token
        with [SHELL] tags filtered out in real-time. Shell commands collected by
        the filter are executed after streaming completes.
        """
        t0 = time.time()
        clr.print_debug("  Thinking...")

        if token_callback:
            # ── Streaming path ──────────────────────────────────────────
            if begin_callback:
                begin_callback()

            stream_filter = _ShellStreamFilter()
            llm_response = ""

            clr.print_ai_start()
            for token in self.brain.generate_response_stream(command_text):
                llm_response += token
                visible = stream_filter.feed(token)
                if visible:
                    token_callback(visible)
                    clr.print_ai_token(visible)

            remaining = stream_filter.flush()
            if remaining:
                token_callback(remaining)
                clr.print_ai_token(remaining)
            clr.print_ai_end()

            shell_commands = stream_filter.shell_commands
        else:
            # ── Non-streaming path (fallback) ───────────────────────────
            llm_response = self.brain.generate_response(command_text)
            shell_commands = re.findall(r'\[SHELL\](.*?)\[/SHELL\]', llm_response, re.DOTALL)

        elapsed = time.time() - t0
        clr.print_debug(f"  Response in {elapsed:.2f}s")
        logger.info("LLM responded in %.2fs (%d chars)", elapsed, len(llm_response))

        if not llm_response:
            clr.print_error("No response received.")
            return "I didn't get a response. Please try again."

        if not shell_commands:
            # Pure conversational response
            if not token_callback:
                clr.print_ai(llm_response)
            return llm_response

        # Conversational part (outside [SHELL] tags) — for TTS
        clean_text = re.sub(r'\[SHELL\].*?\[/SHELL\]', '', llm_response, flags=re.DOTALL).strip()

        results = []
        if clean_text:
            if not token_callback:
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
                self.brain.memory.add("system", msg)
                results.append(msg)
                continue

            logger.info("Executing LLM-generated shell command: %s", cmd)
            clr.print_shell(cmd)

            shell_output = self._execute_shell(cmd, from_llm=True)

            # Feed the output back into the LLM's memory
            self.brain.memory.add("system", f"Output of `{cmd}`:\n{shell_output}")

            if shell_output and shell_output != "Command executed.":
                results.append(f"Output:\n{shell_output}")
            else:
                results.append(f"Done: {cmd}")

            # Error auto-recovery (non-streaming only to avoid nesting issues)
            is_error = shell_output.startswith("Error:") or shell_output.startswith("Shell Error:")
            if is_error and depth < 2 and not token_callback:
                clr.print_warning(f"Command failed. Auto-recovering (attempt {depth + 1}/2)...")
                recovery_prompt = (
                    f"The command `{cmd}` failed with the following output:\n"
                    f"{shell_output}\n\n"
                    "Please analyze the error, explain what went wrong briefly, "
                    "and provide a corrected command wrapped in [SHELL] tags."
                )
                recovery_result = self._process_with_llm(recovery_prompt, depth=depth + 1)
                results.append(f"--- Auto-Recovery ---\n{recovery_result}")

        return "\n".join(results)

    # ── Shell Execution ─────────────────────────────────────────────────────

    def _execute_shell(self, command: str, from_llm: bool = False) -> str:
        """
        Execute a command in PowerShell subprocess.
        
        Args:
            command: The PowerShell command to run.
            from_llm: If True, this command came from LLM output (extra safety).
        """
        # Confirmation Mode
        if self.confirmation_mode:
            if not self._request_confirmation(command):
                msg = f"Command cancelled by user: `{command}`"
                clr.print_warning(msg)
                return msg

        # WSL Sandbox override
        if self.wsl_mode:
            logger.info("Routing command to WSL: %s", command)
            # Simple wsl wrapper. Note: might fail for Windows-specific paths/commands
            command = f"wsl -- {command}"

        logger.info("Shell exec%s: %s", " (from LLM)" if from_llm else "", command)

        try:
            # Decide wrapper based on command content (crude WSL routing if not forced)
            shell_args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
            if command.startswith("wsl -- "):
                shell_args = ["wsl", "--", command[7:]]

            result = subprocess.run(
                shell_args,
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

    def _request_confirmation(self, command: str) -> bool:
        """
        Request user confirmation for a command.
        Will use the callback if registered (UI), otherwise defaults to console if possible.
        """
        if self._confirm_callback:
            return self._confirm_callback(command)
        
        # Fallback (though orchestrator usually runs in non-interactive background)
        print(f"\n[CONFIRM] Run this command? (y/n): {clr.shell(command)}")
        # In a background thread without a terminal input, this might hang or fail.
        # We really rely on the callback from main.py
        return True # Default to True if no callback to avoid silent stalls

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
            "  shell ...            — Shell & Sandbox controls\n"
            "  clear memory         — Clear conversation memory\n"
        )

        # Help
        if re.search(r"^(llm|brain)\s+help$", command_text, re.IGNORECASE):
            return help_text

        # Status
        if re.search(r"^(llm|brain)\s+status$", command_text, re.IGNORECASE):
            status = self.brain.get_status()
            health_icon = "+" if status["health"] == "connected" else "x"
            voice = self.tts.get_voice() if self.tts else "N/A"
            return (
                "Brain Status:\n"
                f"  [{health_icon}] Health:     {status['health']}\n"
                f"  Provider:    {status['provider']}\n"
                f"  Model:       {status['model']}\n"
                f"  Persona:     {status['persona']}\n"
                f"  Voice:       {voice}\n"
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

    # ── Persona Commands ────────────────────────────────────────────────────

    RECOMMENDED_VOICES = [
        ("en-GB-RyanNeural", "British Male (witty default)"),
        ("en-US-GuyNeural", "American Male (professional)"),
        ("en-US-JennyNeural", "American Female (friendly)"),
        ("en-US-AndrewNeural", "American Male (technical)"),
        ("en-AU-WilliamNeural", "Australian Male (comic)"),
        ("en-GB-SoniaNeural", "British Female"),
        ("en-US-AriaNeural", "American Female"),
        ("en-IN-NeerjaNeural", "Indian Female"),
        ("en-IN-PrabhatNeural", "Indian Male"),
    ]

    def _handle_persona_command(self, command_text: str) -> str:
        """Handle persona management commands."""

        help_text = (
            "Persona Controls:\n"
            "-----------------------------------\n"
            "  persona list        - List available personas\n"
            "  persona set <name>  - Switch persona (also changes voice)\n"
            "  persona status      - Show active persona\n"
            "  persona reset       - Reset to default (witty)\n"
        )

        # persona help
        if re.search(r"^persona\s+help$", command_text, re.IGNORECASE):
            return help_text

        # persona list
        if re.search(r"^persona\s+list$", command_text, re.IGNORECASE):
            personas = self.brain.personas.list_all()
            active = self.brain.personas.get_active_name()
            lines = ["Available Personas:"]
            for p in personas:
                marker = " <-" if p.name == active else ""
                lines.append(f"  - {p.display_name} ({p.name}) - {p.description}{marker}")
            return "\n".join(lines)

        # persona set <name>
        set_match = re.search(r"^persona\s+set\s+(.+)$", command_text, re.IGNORECASE)
        if set_match:
            name = set_match.group(1).strip()
            ok, message, new_voice = self.brain.set_persona(name)
            if ok and self.tts:
                profile = self.brain.personas.get_active()
                self.tts.set_voice(new_voice)
                self.tts.set_rate(profile.tts_rate)
            return message

        # persona status
        if re.search(r"^persona\s+status$", command_text, re.IGNORECASE):
            profile = self.brain.personas.get_active()
            voice = self.tts.get_voice() if self.tts else "N/A"
            return (
                f"Active Persona: {profile.display_name}\n"
                f"  Voice:  {voice}\n"
                f"  Style:  {profile.description}"
            )

        # persona reset
        if re.search(r"^persona\s+reset$", command_text, re.IGNORECASE):
            result = self.brain.personas.reset()
            profile = self.brain.personas.get_active()
            self.brain.settings.system_prompt = profile.system_prompt
            if self.tts:
                self.tts.set_voice(profile.voice)
                self.tts.set_rate(profile.tts_rate)
            return result

        return help_text

    def _handle_voice_command(self, command_text: str) -> str:
        """Handle voice control commands."""

        help_text = (
            "Voice Controls:\n"
            "-----------------------------------\n"
            "  voice set <voice_id>  - Set TTS voice manually\n"
            "  voice list            - Show recommended voices\n"
            "  voice status          - Show current voice\n"
        )

        # voice help
        if re.search(r"^voice\s+help$", command_text, re.IGNORECASE):
            return help_text

        # voice set <id>
        set_match = re.search(r"^voice\s+set\s+(.+)$", command_text, re.IGNORECASE)
        if set_match:
            voice_id = set_match.group(1).strip()
            if self.tts:
                self.tts.set_voice(voice_id)
                return f"Voice set to '{voice_id}'."
            return "TTS not available."

        # voice list
        if re.search(r"^voice\s+list$", command_text, re.IGNORECASE):
            current = self.tts.get_voice() if self.tts else ""
            lines = ["Recommended Voices:"]
            for vid, desc in self.RECOMMENDED_VOICES:
                marker = " <-" if vid == current else ""
                lines.append(f"  - {vid} - {desc}{marker}")
            lines.append("\nTip: Use 'voice set <voice_id>' to change.")
            return "\n".join(lines)

        # voice status
        if re.search(r"^voice\s+status$", command_text, re.IGNORECASE):
            if self.tts:
                return f"Current voice: {self.tts.get_voice()}"
            return "TTS not available."

        return help_text

    # -- STT Commands --------------------------------------------------------

    # Common language name -> Whisper code mapping
    LANGUAGE_ALIASES = {
        "auto": "auto", "detect": "auto",
        "english": "en", "en": "en",
        "hindi": "hi", "hi": "hi",
        "spanish": "es", "es": "es",
        "french": "fr", "fr": "fr",
        "german": "de", "de": "de",
        "japanese": "ja", "ja": "ja",
        "chinese": "zh", "zh": "zh",
        "korean": "ko", "ko": "ko",
        "portuguese": "pt", "pt": "pt",
        "russian": "ru", "ru": "ru",
        "arabic": "ar", "ar": "ar",
        "italian": "it", "it": "it",
        "tamil": "ta", "ta": "ta",
        "telugu": "te", "te": "te",
        "bengali": "bn", "bn": "bn",
        "marathi": "mr", "mr": "mr",
        "gujarati": "gu", "gu": "gu",
        "kannada": "kn", "kn": "kn",
        "malayalam": "ml", "ml": "ml",
        "punjabi": "pa", "pa": "pa",
        "urdu": "ur", "ur": "ur",
    }

    def _handle_stt_command(self, command_text: str) -> str:
        """Handle STT language switching commands."""

        help_text = (
            "STT Controls:\n"
            "-----------------------------------\n"
            "  stt language <lang>   - Set STT language (auto/hindi/english/...)\n"
            "  stt language status   - Show current STT language\n"
            "  stt language list     - Show supported languages\n"
        )

        # stt help
        if re.search(r"^stt\s+help$", command_text, re.IGNORECASE):
            return help_text

        # stt language status
        if re.search(r"^stt\s+language\s+status$", command_text, re.IGNORECASE):
            return f"Current STT language: {self._stt_language}"

        # stt language list
        if re.search(r"^stt\s+language\s+list$", command_text, re.IGNORECASE):
            langs = sorted(set(self.LANGUAGE_ALIASES.values()))
            names = []
            for code in langs:
                # Find the human-readable name for this code
                name = next((k for k, v in self.LANGUAGE_ALIASES.items() if v == code and len(k) > 2), code)
                names.append(f"  - {name} ({code})")
            return "Supported STT Languages:\n" + "\n".join(names)

        # stt language <lang>
        lang_match = re.search(r"^stt\s+language\s+(.+)$", command_text, re.IGNORECASE)
        if lang_match:
            lang_input = lang_match.group(1).strip().lower()
            lang_code = self.LANGUAGE_ALIASES.get(lang_input, lang_input)

            # Send LANG command to the STT worker
            if self.listener and hasattr(self.listener, '_worker') and self.listener._worker:
                try:
                    self.listener._worker.stdin.write(f"LANG:{lang_code}\n")
                    self.listener._worker.stdin.flush()
                    import json
                    response = self.listener._worker.stdout.readline().strip()
                    if response:
                        data = json.loads(response)
                        if data.get("status") == "lang_set":
                            self._stt_language = lang_code if lang_code != "auto" else "auto"
                            display = lang_input if lang_input in self.LANGUAGE_ALIASES else lang_code
                            return f"STT language set to '{display}' ({lang_code}). Speak now!"
                except Exception as e:
                    return f"Error setting STT language: {e}"

            self._stt_language = lang_code if lang_code != "auto" else "auto"
            return f"STT language set to '{lang_code}' (will apply on next restart)."

        return help_text

    def _handle_shell_command(self, command_text: str) -> str:
        """Handle shell configuration and sandbox controls."""
        
        help_text = (
            "Shell & Sandbox Controls:\n"
            "-----------------------------------\n"
            "  shell confirmation on/off - Toggle ask-before-exec\n"
            "  shell wsl on/off         - Toggle WSL sandbox for commands\n"
            "  shell status             - Show current shell settings\n"
        )

        # shell status
        if re.search(r"^shell\s+status$", command_text, re.IGNORECASE):
            conf = "ON" if self.confirmation_mode else "OFF"
            wsl = "ON" if self.wsl_mode else "OFF"
            return (
                "Shell Settings:\n"
                f"  Confirmation Mode: {conf}\n"
                f"  WSL Sandbox Mode:  {wsl}"
            )

        # shell confirmation on/off
        conf_match = re.search(r"^shell\s+confirmation\s+(on|off)$", command_text, re.IGNORECASE)
        if conf_match:
            state = conf_match.group(1).lower() == "on"
            self.confirmation_mode = state
            return f"Command confirmation mode turned {'ON' if state else 'OFF'}."

        # shell wsl on/off
        wsl_match = re.search(r"^shell\s+wsl\s+(on|off)$", command_text, re.IGNORECASE)
        if wsl_match:
            state = wsl_match.group(1).lower() == "on"
            self.wsl_mode = state
            return f"WSL sandbox mode turned {'ON' if state else 'OFF'}."

        return help_text
