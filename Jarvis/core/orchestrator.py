"""
Orchestrator Module — Command Router & Execution Engine
========================================================
Central coordinator that receives user input and decides how to handle it:

  1. Meta-commands (llm/brain control)  →  Internal settings management
  2. Direct shell patterns              →  Shell execution via ActionRouter
  3. Natural language                   →  Brain (LLM) processing
     └─ LLM may return [SHELL]/[ACTION] →  Routed through OS Abstraction Layer

Features:
  - Structured intent classification
  - OS Abstraction Layer (no direct subprocess calls)
  - Safety-aware execution with SafetyEngine
  - App Registry for reliable app launching
  - Conversation context awareness
  - Proper error handling and logging
  - Colorized terminal output
  - Output formatting for TTS compatibility
"""

import logging
import re
import threading
import time
from typing import Optional

from Jarvis.core.brain import Brain, Provider
from Jarvis.core.tools import Tools
from Jarvis.core import colors as clr
from Jarvis.core.pipeline import eager_sentence_split, PipelineMetrics, FILLER_PHRASES, FILLER_TIMEOUT_S
from Jarvis.core.system import (
    get_backend, ActionRouter, extract_actions, RiskLevel,
    ActionRequest, ActionType, ACTION_TAG_PATTERN, SHELL_TAG_PATTERN
)
from Jarvis.core.terminal_bridge import get_terminal_bridge
from Jarvis.core.intent_engine import IntentEngine, IntentResult
from Jarvis.config import (
    GROQ_API_KEY, GROQ_INTENT_MODEL,
    INTENT_ENGINE_ENABLED, INTENT_CONFIDENCE_THRESHOLD,
    GEMINI_API_KEY, OLLAMA_MODEL,
)

logger = logging.getLogger("jarvis.orchestrator")


# ─────────────────────────── Tag Stream Filter ────────────────────────────

class _TagStreamFilter:
    """
    Stateful filter for LLM token streams.

    Strips [SHELL]...[/SHELL] and [ACTION]...[/ACTION] tags in real-time
    so only conversational text reaches the display callback.
    Extracted commands/actions are stored and executed after streaming completes.
    """

    _TAGS = [
        ("[SHELL]", "[/SHELL]"),
        ("[ACTION]", "[/ACTION]"),
        ("[EXEC_CODE]", "[/EXEC_CODE]"),
    ]

    def __init__(self):
        self._buf       = ""   # partial tag detection lookahead buffer
        self._in_tag    = False
        self._tag_type  = None  # which tag we're currently inside
        self._close_tag = None  # the closing tag to look for
        self._tag_buf   = ""   # accumulates the tag content
        self.shell_commands: list[str] = []
        self.action_commands: list[str] = []
        self.code_commands: list[str] = []

    def feed(self, text: str) -> str:
        """Return the displayable portion of a token (empty when inside a tag block)."""
        display = ""
        for ch in text:
            if not self._in_tag:
                self._buf += ch
                
                # Pre-filter: Check for markdown code block markers starting (e.g. ```)
                # and strip them if they appear just before or as part of a tag sequence.
                if "```" in self._buf:
                    # If we see backticks, we strip them from the display buffer
                    # to prevent them leaking into the UI while we wait for the tag.
                    self._buf = self._buf.replace("```", "")
                    # Also strip common language identifiers that follow
                    for lang in ["shell", "action", "powershell", "cmd", "python"]:
                        if self._buf.lower().endswith(lang):
                            self._buf = self._buf[:-(len(lang))]
                            break

                # Check for any opening tag (case-insensitive)
                matched = False
                buf_upper = self._buf.upper()
                for open_tag, close_tag in self._TAGS:
                    if open_tag in buf_upper:
                        idx = buf_upper.index(open_tag)
                        display += self._buf[:idx]
                        self._buf = ""
                        self._in_tag = True
                        self._tag_type = open_tag
                        self._close_tag = close_tag
                        matched = True
                        break
                if matched:
                    continue
                # Check if buffer could still be a partial tag prefix
                could_be_prefix = any(
                    tag.startswith(buf_upper) for tag, _ in self._TAGS
                )
                if not could_be_prefix:
                    display += self._buf
                    self._buf = ""
            else:
                self._tag_buf += ch
                tag_buf_upper = self._tag_buf.upper()
                if self._close_tag in tag_buf_upper:
                    idx = tag_buf_upper.index(self._close_tag)
                    content = self._tag_buf[:idx].strip()
                    # Also clean up trailing backticks inside the tag buffer if they exist
                    content = content.replace("```", "").strip()
                    if content:
                        if self._tag_type == "[SHELL]":
                            self.shell_commands.append(content)
                        elif self._tag_type == "[ACTION]":
                            self.action_commands.append(content)
                        elif self._tag_type == "[EXEC_CODE]":
                            self.code_commands.append(content)
                    self._tag_buf = self._tag_buf[idx + len(self._close_tag):]
                    self._in_tag = False
                    self._tag_type = None
                    self._close_tag = None
                    
                    # Post-tag: Clean up trailing backticks in the main buffer
                    self._buf = self._buf.replace("```", "")
        return display

    def flush(self) -> str:
        """Flush any buffered display text at end of stream."""
        if not self._in_tag:
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
    r"start-process|stop-process|restart-service|get-date|taskmgr|control|"
    r"services\.msc|regedit|mstsc|winver|curl|wget|ssh|scp)\b",
    # Dev tools (common/safe usage)
    r"^(git\s+(status|branch|log|diff|show|remote))",
    r"^(npm\s+(list|v|version))",
    r"^(pip\s+(list|show))",
    r"^(python\s+(--version|-V))",
    # App launchers (legacy/direct)
    r"^(notepad|calc|explorer|code|chrome|firefox|edge|mspaint|cmd|powershell)\b",
]

# Dangerous commands that need extra caution (synchronized with SafetyEngine)
DANGEROUS_PATTERNS = [
    r"format\b",
    r"diskpart\b",
    r"bcdedit\b",
    r"rm\s+-rf",
    r"remove-item\s+.*-recurse",
    r"del\s+/[sS]",
    r"reg\s+(delete|add)",
    r"netsh\s+advfirewall",
    r"Set-Service",
    r"Stop-Service",
    r"Set-ExecutionPolicy",
]

# Maximum output length before truncation (for TTS)
MAX_OUTPUT_LENGTH = 500
MAX_TTS_LENGTH = 300


def _log_intent(intent: "IntentResult") -> None:
    """Print a colourised intent analysis summary to the terminal."""
    conf_color = "\033[92m" if intent.confidence >= 0.75 else ("\033[93m" if intent.confidence >= 0.5 else "\033[91m")
    reset = "\033[0m"
    tag = f"  [Intent] {conf_color}{intent.category}{reset}"
    if intent.action:
        tag += f" / {intent.action}"
    tag += f" ({conf_color}{intent.confidence:.0%}{reset})"
    if intent.is_ambiguous:
        tag += f" ⚠ ambiguous"
    if intent.latency_ms:
        tag += f" [{intent.latency_ms:.0f}ms]"
    clr.print_info(tag)
    if intent.reasoning:
        clr.print_info(f"    reasoning: {intent.reasoning}")
    if intent.error:
        clr.print_info(f"    [Intent fallback: {intent.error}]")


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
        self.seamless_mode = True       # AUTO-SWITCH: Use cloud (Gemini/Groq) if local is slow
        self._confirm_callback = None   # Callback(command_text) -> bool

        # OS Abstraction Layer
        self._backend = get_backend()
        self.action_router = ActionRouter(
            self._backend,
            confirm_callback=self._request_confirmation,
        )

        # ── Intent Engine (Deep Thinking) ─────────────────────────────────
        # Powered by Groq — runs concurrently, adds zero net latency.
        self.intent_engine: IntentEngine | None = None
        if INTENT_ENGINE_ENABLED and GROQ_API_KEY:
            self.intent_engine = IntentEngine(
                api_key=GROQ_API_KEY,
                model=GROQ_INTENT_MODEL,
                confidence_threshold=INTENT_CONFIDENCE_THRESHOLD,
            )
            logger.info("IntentEngine initialized | model=%s threshold=%.0f%%",
                        GROQ_INTENT_MODEL, INTENT_CONFIDENCE_THRESHOLD * 100)
        else:
            logger.info("IntentEngine disabled (INTENT_ENGINE_ENABLED=false or no GROQ_API_KEY)")

        # Apply initial persona voice to TTS
        if self.tts:
            active = self.brain.personas.get_active()
            self.tts.set_voice(active.voice)
            self.tts.set_rate(active.tts_rate)
            
        # Start health monitor for Seamless Mode
        threading.Thread(target=self._health_monitor_loop, daemon=True).start()

        logger.info("Orchestrator initialized | platform=%s | seamless=%s", 
                    self._backend.platform_name, self.seamless_mode)

    def _health_monitor_loop(self):
        """Monitor local component health and auto-adjust seamless mode settings."""
        while True:
            try:
                # Check Ollama health
                ollama_ok = self.brain._backends[Provider.OLLAMA].health_check()
                if not ollama_ok and self.seamless_mode:
                    logger.warning("Ollama unreachable, seamless mode forcing Cloud fallback")
                
                time.sleep(60) # Check every minute
            except Exception as e:
                logger.error("Health monitor error: %s", e)
                time.sleep(60)

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

        # ── Launch Deep Intent Analysis concurrently ────────────────────────
        # Fires off immediately so it runs in parallel with any
        # deterministic bypasses and the filler-phrase timeout.
        _intent_future = None
        if self.intent_engine:
            _history = self.brain.memory.get_history()
            _intent_future = self.intent_engine.analyze_async(command_text, _history)

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

            # 4. Capability commands
            if re.search(r"^(what can you do|capabilities|help permissions|sandbox)$", command_text, re.IGNORECASE):
                result = self._handle_capabilities_command()
                print(clr.info(result))
                return result

            # 5. Memory commands
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

            # 7. Direct app launch detection: "open spotify", "launch notepad", "can you open notepad"
            # Improved regex: match verb-app patterns anywhere in sentence, not just at start
            app_match = re.search(r"(?:can\s+you\s+)?(?:can\s+)?(?:please\s+)?(open|launch|start|run)\s+([\w\s.-]+?)(?:\s+(?:for\s+)?(?:me|please|now)|$)", command_text, re.IGNORECASE)
            if app_match:
                app_name = app_match.group(2).strip()
                # Sanitize: strip common conversational fluff
                fluff = [r"\s+please\b", r"\s+thanks\b", r"\s+for\s+me\b", r"\s+now\b", r"^\s+the\s+"]
                for pat in fluff:
                    app_name = re.sub(pat, "", app_name, flags=re.IGNORECASE).strip()

                # Check if it's a known app or a plausible exe before bypassing LLM
                registry = getattr(self._backend, "_app_registry", None)
                if registry and (registry.resolve(app_name) or app_name.lower().endswith(".exe")):
                    from Jarvis.core.system.actions import ActionRequest, ActionType
                    req = ActionRequest(action_type=ActionType.LAUNCH_APP, target=app_name)
                    clr.print_info(f"  Direct Launch: {app_name}")
                    result = self.action_router.execute_action(req)
                    return result.message

            # 8a. Pre-LLM system control bypass
            #     Catches "screenshot", "lock screen", "what time is it", "mute", etc.
            sys_result = self._detect_system_intent(command_text)
            if sys_result is not None:
                return sys_result

            # 8b. Pre-LLM media / search bypass — deterministic, no hallucination
            #    Catches "play X on youtube", "search X", "open url in chrome", etc.
            #    before the LLM sees them. Avoids placeholder text and model confusion.
            direct_result = self._detect_media_or_search_intent(command_text)
            if direct_result is not None:
                return direct_result

            # 8b. Direct shell command detection
            shell_cmd = self._detect_shell_command(command_text)
            if shell_cmd:
                clr.print_shell(shell_cmd)
                result = self._execute_shell(shell_cmd)
                return result

            # ── Collect intent result (if engine ran) ───────────────────────
            # Collect with a short timeout (should already be done by now).
            intent: IntentResult | None = None
            if _intent_future is not None:
                try:
                    intent = _intent_future.result(timeout=1.5)
                    _log_intent(intent)

                    # Intent-assisted routing: if Groq is highly confident
                    # in a specific category, log it and adjust the query.
                    if intent.is_confident:
                        effective = intent.effective_query or command_text
                    else:
                        effective = command_text
                        if intent.is_ambiguous:
                            clr.print_info(
                                f"  [Intent] Ambiguous ({intent.confidence:.0%}): {intent.ambiguity_note}"
                            )
                except Exception as e:
                    logger.debug("Intent future timed out or failed: %s", e)
                    effective = command_text
            else:
                effective = command_text

            # 9. Route to Brain (LLM) for everything else
            return self._process_with_llm(
                effective,
                intent=intent,
                token_callback=token_callback,
                begin_callback=begin_callback,
            )

        except Exception as e:
            return self._handle_processing_error(e)

    def _handle_processing_error(self, e: Exception, also_speak: bool = False) -> str:
        """Centralized error handling for command processing."""
        err_str = str(e)
        logger.error("Command processing failed: %s", err_str, exc_info=True)
        
        # Check for connection/technical errors
        if any(msg in err_str for msg in [
            "Max retries exceeded", "Failed to establish a new connection", 
            "11434", "Connection refused", "Ollama", "http"
        ]):
            friendly_err = "I'm having trouble connecting to my brain, sir. Please check if Ollama is running."
            clr.print_error(friendly_err)
            if also_speak:
                self._speak_async(friendly_err)
            return friendly_err
            
        # Generic fallback - prefix with Error: to prevent main loop from speaking it
        clr.print_error(f"Error: {err_str}")
        return f"Error: I encountered an unexpected failure, sir. {err_str}"

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

    def _detect_system_intent(self, text: str) -> Optional[str]:
        """
        Deterministically handle Windows system control intents WITHOUT the LLM.
        Covers: screenshot, lock screen, time/date, mute/volume, open folder, timer.
        Returns the response string if handled, or None to fall through.
        """
        import datetime
        tl = text.strip().lower()

        # ── 0. Math / Calculation — instant, from Python eval ────────────────
        # "calculate 5+3", "what is 25*4", "how much is 15% of 200", etc.
        calc_match = re.search(
            r"(?:calculate|compute|eval(?:uate)?|solve)\s+(.+)",
            tl, re.IGNORECASE
        )
        if not calc_match:
            calc_match = re.search(
                r"(?:what(?:'s| is)|how much is)\s+([\d][\d\s+\-*/^.%()\w]*)",
                tl, re.IGNORECASE
            )
        if calc_match:
            expr = calc_match.group(1).strip().rstrip("?.")
            # Convert natural language operators
            expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
            expr = re.sub(r"(\d+)\s*%\s*of\s*(\d+)", r"\1/100*\2", expr)
            expr = re.sub(r"(\d+)\s+(?:times|x)\s+(\d+)", r"\1*\2", expr)
            expr = re.sub(r"(\d+)\s+(?:plus|and)\s+(\d+)", r"\1+\2", expr)
            expr = re.sub(r"(\d+)\s+(?:minus)\s+(\d+)", r"\1-\2", expr)
            expr = re.sub(r"(\d+)\s+(?:divided by|over)\s+(\d+)", r"\1/\2", expr)
            # Only bypass if expression looks mathematic (has digits + operators)
            if re.search(r"\d", expr) and re.search(r"[+\-*/().]", expr):
                result = self.tools.calculate(expr)
                if not result.startswith("Error"):
                    msg = f"The answer is {result}."
                    clr.print_info(f"  Math bypass: {expr} = {result}")
                    return msg

        # ── 1. Time / Date — instant, from Python datetime ──────────────────────
        if re.search(r"what('?s| is) (the )?(time|current time)", tl) or re.search(r"\btime( is it| now)?\b", tl):
            now = datetime.datetime.now()
            t = now.strftime("%I:%M %p").lstrip("0")
            msg = f"It's {t}."
            clr.print_info(f"  Time bypass: {msg}")
            return msg

        if re.search(r"what('?s| is) (the )?(date|today)", tl) or re.search(r"today'?s date", tl):
            today = datetime.datetime.now().strftime("%A, %B %d, %Y")
            msg = f"Today is {today}."
            clr.print_info(f"  Date bypass: {msg}")
            return msg

        # ── 2. Screenshot ──────────────────────────────────────────────
        if re.search(r"(take|capture|grab)\s+(a\s+)?screenshot", tl) or re.search(r"^screenshot$", tl):
            clr.print_info("  Screenshot bypass")
            return self._backend.screenshot().message

        # ── 3. Lock screen / computer ────────────────────────────────────
        if re.search(r"lock\s+(the\s+)?(screen|computer|pc|laptop|workstation)", tl) or re.search(r"^lock( ?(me|my ?(pc|computer|screen)))?$", tl):
            clr.print_info("  Lock screen bypass")
            return self._backend.lock_screen().message

        # ── 4. Mute / Unmute ──────────────────────────────────────────
        if re.search(r"^mute(\s+(the\s+)?(sound|audio|volume|mic))?$", tl):
            clr.print_info("  Mute bypass")
            return self._backend.mute_toggle(mute=True).message

        if re.search(r"^unmute(\s+(the\s+)?(sound|audio|volume|mic))?$", tl):
            clr.print_info("  Unmute bypass")
            return self._backend.mute_toggle(mute=False).message

        # ── 5. Set volume ─────────────────────────────────────────────
        vol_match = re.search(r"(set\s+)?(volume|vol)(\s+to)?\s+(\d{1,3})\s*%?", tl)
        if vol_match:
            pct = int(vol_match.group(4))
            clr.print_info(f"  Volume bypass: {pct}%")
            return self._backend.set_volume(pct).message

        # ── 6. Open folder ─────────────────────────────────────────────
        folder_match = re.search(
            r"(?:open|show|go to)\s+(?:my\s+)?(downloads?|documents?|pictures?|music|videos?|desktop)",
            tl
        )
        if folder_match:
            fname = folder_match.group(1).rstrip("s")  # downloads -> download
            # Map back to full name
            fname_map = {"download": "downloads", "document": "documents",
                         "picture": "pictures", "music": "music",
                         "video": "videos", "desktop": "desktop"}
            fname = fname_map.get(fname, fname)
            clr.print_info(f"  Open folder bypass: {fname}")
            return self._backend.open_folder(fname).message

        # ── 7. Task Manager / System Tools ────────────────────────────
        if re.search(r"(open\s+)?task\s*manager", tl):
            from Jarvis.core.system.actions import ActionRequest, ActionType
            req = ActionRequest(action_type=ActionType.LAUNCH_APP, target="taskmgr")
            result = self.action_router.execute_action(req)
            return result.message

        # Not handled — fall through to media/search bypass or LLM
        return None

    def _detect_media_or_search_intent(self, text: str) -> Optional[str]:
        """
        Deterministically handle media/search intents WITHOUT the LLM.
        Covers: play X on youtube/spotify, search X on google, open URL, etc.

        Returns the response string if handled, or None to fall through to LLM.
        """
        from urllib.parse import quote
        from Jarvis.core.system.actions import ActionRequest, ActionType

        t = text.strip()
        tl = t.lower()

        # ── Helper to actually run a play_music or open_url action ──
        def _do_play(query: str) -> str:
            req = ActionRequest(action_type=ActionType.PLAY_MUSIC, target=query)
            clr.print_info(f"  Direct Media: {query}")
            result = self.action_router.execute_action(req)
            return result.message

        def _do_open_url(url: str) -> str:
            req = ActionRequest(action_type=ActionType.OPEN_URL, target=url)
            clr.print_info(f"  Direct URL: {url}")
            result = self.action_router.execute_action(req)
            return result.message

        def _do_search_google(query: str) -> str:
            url = f"https://www.google.com/search?q={quote(query)}"
            return _do_open_url(url)

        def _do_search_youtube(query: str) -> str:
            url = f"https://www.youtube.com/results?search_query={quote(query)}"
            return _do_open_url(url)

        # ── 1. YouTube intent patterns ────────────────────────────────────
        # "play X on youtube", "watch X on youtube", "search X on youtube",
        # "play X youtube", "video X on youtube"
        yt_match = re.search(
            r"(?:play|watch|search|find|look up|video|open)\s+(.+?)\s+(?:on\s+)?youtube",
            tl, re.IGNORECASE
        )
        if yt_match:
            query = yt_match.group(1).strip()
            # Strip leading noise
            query = re.sub(r"^(a\s+|the\s+|me\s+|some\s+)", "", query, flags=re.IGNORECASE)
            if query:
                clr.print_info(f"  YouTube search bypass: {query}")
                return _do_search_youtube(query)

        yt_open = re.search(r"(?:open|go to|launch|start)\s+youtube", tl)
        if yt_open and not yt_match:
            return _do_open_url("https://www.youtube.com")

        # ── 2. Spotify intent patterns ────────────────────────────────────
        # "play X on spotify", "play X by Y", "play X"
        spotify_match = re.search(
            r"(?:play|search|find)\s+(.+?)\s+(?:on\s+)?spotify",
            tl, re.IGNORECASE
        )
        if spotify_match:
            query = spotify_match.group(1).strip()
            query = re.sub(r"^(a\s+|the\s+|me\s+|some\s+)", "", query, flags=re.IGNORECASE)
            if query:
                clr.print_info(f"  Spotify search bypass: {query}")
                return _do_play(query + " spotify")

        # "play X by Y" — default to Spotify
        play_by_match = re.search(
            r"^(?:play|put on|start playing)\s+(.+?)\s+by\s+(.+)$",
            tl, re.IGNORECASE
        )
        if play_by_match:
            song = play_by_match.group(1).strip()
            artist = play_by_match.group(2).strip()
            query = f"{song} {artist}"
            clr.print_info(f"  Play by-artist bypass: {query}")
            return _do_play(query)

        # "play X" (generic, no platform specified) — default Spotify
        generic_play = re.search(
            r"^(?:play|put on|start playing)\s+(.+)$",
            tl, re.IGNORECASE
        )
        if generic_play:
            query = generic_play.group(1).strip()
            # Don't bypass if it looks like a file path or shell command
            if not re.search(r'[\\/\.:]', query) and len(query.split()) <= 8:
                clr.print_info(f"  Generic play bypass: {query}")
                return _do_play(query)

        # ── 3. Google/web search patterns ────────────────────────────────
        # "search for X", "google X", "search X on google"
        google_match = re.search(
            r"(?:search\s+(?:for\s+)?|google\s+|look up\s+)(.+?)(?:\s+on\s+google)?$",
            tl, re.IGNORECASE
        )
        if google_match:
            query = google_match.group(1).strip()
            if query and not re.search(r"youtube|spotify", query):
                clr.print_info(f"  Google search bypass: {query}")
                return _do_search_google(query)

        # ── 4. Open a website / URL directly ─────────────────────────────
        url_match = re.search(
            r"(?:go to|open|navigate to|visit)\s+(https?://[^\s]+|[\w.-]+\.[a-z]{2,}(?:/[^\s]*)?)",
            tl, re.IGNORECASE
        )
        if url_match:
            raw_url = url_match.group(1).strip()
            if not raw_url.startswith("http"):
                raw_url = "https://" + raw_url
            clr.print_info(f"  Direct URL bypass: {raw_url}")
            return _do_open_url(raw_url)

        # Not handled — fall through to LLM
        return None

    # ── LLM Processing ──────────────────────────────────────────────────────

    # System prompt for the local "Action Engine" (Phase 1)
    _ACTION_ENGINE_PROMPT = (
        "You are an action engine. Your ONLY job is to decide what to DO.\n"
        "Analyze the user's request carefully.\n\n"
        "RULES:\n"
        "1. If the request needs a shell/terminal command, output ONLY:\n"
        "   [SHELL]the exact command[/SHELL]\n"
        "2. If it needs to open an app/URL/file, output ONLY:\n"
        "   [ACTION]LAUNCH_APP:appname[/ACTION] or [ACTION]OPEN_URL:url[/ACTION]\n"
        "3. If the request is a math calculation, output ONLY:\n"
        "   [CALC]the mathematical expression[/CALC]\n"
        "4. If the request is just conversation/question/chat, output ONLY:\n"
        "   CONVERSATION\n\n"
        "NEVER add explanation. NEVER add conversation. Output ONLY the tag or CONVERSATION.\n\n"
        "Examples:\n"
        "User: open notepad → [ACTION]LAUNCH_APP:notepad[/ACTION]\n"
        "User: what's 25 * 4 → [CALC]25 * 4[/CALC]\n"
        "User: list files in downloads → [SHELL]dir %USERPROFILE%\\Downloads[/SHELL]\n"
        "User: how are you → CONVERSATION\n"
        "User: open spotify → [ACTION]LAUNCH_APP:spotify[/ACTION]\n"
        "User: what's the weather → CONVERSATION\n"
        "User: create a folder called test → [SHELL]mkdir test[/SHELL]\n"
        "User: open google chrome → [ACTION]LAUNCH_APP:chrome[/ACTION]\n"
        "User: what is 2 to the power of 10 → [CALC]2**10[/CALC]\n"
        "User: tell me a joke → CONVERSATION\n"
        "User: run python script test.py → [SHELL]python test.py[/SHELL]\n"
        "User: open calculator → [ACTION]LAUNCH_APP:calc[/ACTION]\n"
        "User: open task manager → [ACTION]LAUNCH_APP:taskmgr[/ACTION]\n"
        "User: open command prompt → [ACTION]LAUNCH_APP:cmd[/ACTION]\n"
        "User: what's 15% of 230 → [CALC]0.15 * 230[/CALC]\n"
        "User: search python tutorials → CONVERSATION\n"
    )

    # Regex to extract [CALC]...[/CALC] from action engine output
    _CALC_TAG_RE = re.compile(r"\[CALC\](.*?)\[/CALC\]", re.IGNORECASE | re.DOTALL)

    def _process_with_llm(
        self,
        command_text: str,
        depth: int = 0,
        token_callback=None,
        begin_callback=None,
        intent: "IntentResult | None" = None,
    ) -> str:
        """
        Hybrid 2-Step Architecture:
          Phase 1 (LOCAL):  Ask local Ollama model to classify + extract actions.
          Phase 2 (EXECUTE): Run any [SHELL]/[ACTION]/[CALC] tags found.
          Phase 3 (CLOUD):  Stream final conversational response from Gemini,
                           enriched with execution results.

        If Gemini is unavailable, falls back to local model for conversation too.
        """
        t0 = time.time()

        # ── Inject Intent Context into Brain memory (ephemeral system note) ──
        _injected_intent_note = False
        if intent and not intent.error:
            note = intent.to_system_note()
            if note:
                self.brain.memory.add("system", note)
                _injected_intent_note = True

        # ════════════════════════════════════════════════════════════════════
        #  PHASE 1: Local Action Classification (Ollama — fast, no internet)
        # ════════════════════════════════════════════════════════════════════
        action_response = ""
        try:
            clr.print_info("  [Phase 1] Local action analysis...")
            action_response = self.brain.generate_response(
                command_text,
                history=[],  # No history needed for action classification
                provider_override="ollama",
                model_override=OLLAMA_MODEL,
                system_prompt_override=self._ACTION_ENGINE_PROMPT,
                skip_memory=True,  # Don't pollute conversation memory
            )
            logger.info("Action engine response: %s", action_response[:200])
            clr.print_info(f"  [Phase 1] Result: {action_response.strip()[:120]}")
        except Exception as e:
            logger.warning("Phase 1 (local action) failed: %s", e)
            action_response = "CONVERSATION"

        # ════════════════════════════════════════════════════════════════════
        #  PHASE 2: Execute any extracted actions
        # ════════════════════════════════════════════════════════════════════
        execution_results = []
        is_action_request = False

        # 2a. Extract [CALC] tags
        calc_matches = self._CALC_TAG_RE.findall(action_response)
        for expr in calc_matches:
            is_action_request = True
            clr.print_info(f"  [Calc] {expr.strip()}")
            calc_result = self.tools.calculate(expr.strip())
            execution_results.append(f"Calculation: {expr.strip()} = {calc_result}")
            clr.print_info(f"  [Calc] Result: {calc_result}")

        # 2b. Extract [SHELL] and [ACTION] tags using the existing filter
        action_filter = _TagStreamFilter()
        action_filter.feed(action_response)
        action_filter.flush()

        for action_str in action_filter.action_commands:
            is_action_request = True
            from Jarvis.core.system.action_router import parse_action_tag
            action_req = parse_action_tag(action_str)
            if action_req:
                clr.print_info(f"  [Action] {action_req.action_type.value} -> {action_req.target}")
                action_result = self.action_router.execute_action(action_req)
                execution_results.append(f"Action ({action_req.action_type.value}): {action_result.message}")

        for cmd in action_filter.shell_commands:
            cmd = cmd.strip()
            if not cmd:
                continue
            is_action_request = True
            clr.print_shell(cmd)
            self._speak_async("Running that now, sir.")
            shell_output = self._execute_shell(cmd, from_llm=True)
            execution_results.append(f"Shell `{cmd}`: {shell_output}")

        # ════════════════════════════════════════════════════════════════════
        #  PHASE 3: Conversational Response (Gemini preferred, local fallback)
        # ════════════════════════════════════════════════════════════════════
        # Build the prompt for the conversation model
        if execution_results:
            # Summarize what was done so the conversation model can describe it
            exec_summary = "\n".join(execution_results)
            conv_prompt = (
                f"The user said: \"{command_text}\"\n\n"
                f"I already performed these actions:\n{exec_summary}\n\n"
                f"Now give a brief, natural conversational response confirming what was done. "
                f"Be concise (1-2 sentences). Don't repeat the command verbatim."
            )
        else:
            # Pure conversation — just pass the user's text
            conv_prompt = command_text

        # Decide conversation provider: Gemini if available, else local
        conv_provider = "gemini" if GEMINI_API_KEY else None  # None = use default
        conv_model = None  # Use provider default

        # ── Filler Logic ──
        _first_token_received = threading.Event()

        def _speak_filler():
            time.sleep(FILLER_TIMEOUT_S)
            if not _first_token_received.is_set():
                import random
                self._speak_async(random.choice(FILLER_PHRASES))

        # Only use filler for pure conversation (actions already gave feedback)
        if not is_action_request:
            threading.Thread(target=_speak_filler, daemon=True).start()
        else:
            _first_token_received.set()  # Skip filler

        if token_callback:
            # ── Streaming path (Preferred) ─────────────────────────────
            if begin_callback:
                begin_callback()

            stream_filter = _TagStreamFilter()
            llm_response = ""

            clr.print_ai_start()
            t_first_token = None
            _visible_tokens = []

            try:
                for token in self.brain.generate_response_stream(
                    conv_prompt,
                    provider_override=conv_provider,
                    model_override=conv_model,
                ):
                    if not _first_token_received.is_set():
                        _first_token_received.set()
                        t_first_token = time.time()
                        logger.info("TTFT: %.0fms", (t_first_token - t0) * 1000)

                    llm_response += token
                    visible = stream_filter.feed(token)

                    if visible:
                        token_callback(visible)
                        clr.print_ai_token(visible)
                        _visible_tokens.append(visible)

            except Exception as e:
                _first_token_received.set()
                logger.warning("Gemini stream failed, falling back to local: %s", e)
                # Fallback: try local model
                try:
                    llm_response = self.brain.generate_response(conv_prompt)
                    if llm_response:
                        token_callback(llm_response)
                        clr.print_ai_token(llm_response)
                        _visible_tokens.append(llm_response)
                except Exception as e2:
                    return self._handle_processing_error(e2, also_speak=True)

            remaining = stream_filter.flush()
            if remaining:
                token_callback(remaining)
                clr.print_ai_token(remaining)
                _visible_tokens.append(remaining)

            clr.print_ai_end()

            # ── Eager sentence flush for TTS ──
            def _token_iter():
                for t in _visible_tokens:
                    yield t

            for sentence, is_final in eager_sentence_split(_token_iter()):
                sentence = sentence.strip()
                if sentence and len(sentence) > 3:
                    self._speak_async(sentence)

            # Handle any residual shell/action tags from Gemini (unlikely but safe)
            for cmd in stream_filter.shell_commands:
                cmd = cmd.strip()
                if cmd:
                    clr.print_shell(cmd)
                    shell_output = self._execute_shell(cmd, from_llm=True)
                    self.brain.memory.add("system", f"Output of `{cmd}`:\n{shell_output}")

        else:
            # ── Non-streaming path ────────────────────────────────────
            _first_token_received.set()
            llm_response = self.brain.generate_response(
                conv_prompt,
                provider_override=conv_provider,
                model_override=conv_model,
            )

        elapsed = time.time() - t0
        logger.info("Hybrid pipeline completed in %.2fs", elapsed)

        if not llm_response and not execution_results:
            return "I'm sorry, sir, I didn't get a response. Could you repeat that?"

        # Build final result
        final_parts = []
        if execution_results:
            final_parts.extend(execution_results)

        # Clean the conversational response
        from Jarvis.core.system.action_router import ACTION_TAG_PATTERN, SHELL_TAG_PATTERN, EXEC_CODE_TAG_PATTERN
        if llm_response:
            clean_text = SHELL_TAG_PATTERN.sub('', llm_response)
            clean_text = ACTION_TAG_PATTERN.sub('', clean_text)
            clean_text = EXEC_CODE_TAG_PATTERN.sub('', clean_text).strip()
            if clean_text:
                if not token_callback:
                    clr.print_ai(clean_text)
                    self._speak_async(clean_text)
                final_parts.append(clean_text)

        # Store in memory
        self.brain.memory.add("user", command_text)
        self.brain.memory.add("assistant", llm_response or "\n".join(execution_results))

        return "\n".join(final_parts) if final_parts else (llm_response or "Done.")

    def _speak_async(self, text: str) -> None:
        """Helper to speak text via TTS in a background thread if available."""
        if self.tts and text.strip():
            # Clean text of tags just in case
            clean = re.sub(r"\[/?(ACTION|SHELL|EXEC_CODE|SYSTEMINFO).*?\]", "", text, flags=re.I).strip()
            if clean:
                self.tts.speak(clean)

    # ── Shell Execution ─────────────────────────────────────────────────────

    def _execute_shell(self, command: str, from_llm: bool = False) -> str:
        """
        Execute a command via the OS Abstraction Layer.

        Routes through ActionRouter → SystemBackend. The ActionRouter
        handles all safety decisions (block CRITICAL, confirm HIGH).
        Confirmation mode adds blanket confirmation for ALL commands.

        Args:
            command: The shell command to run.
            from_llm: If True, this command came from LLM output (extra safety).
        """
        # Get terminal bridge for real-time display
        terminal_bridge = get_terminal_bridge()
        
        # Blanket confirmation mode (asks even for safe commands)
        if self.confirmation_mode:
            if not self._request_confirmation(command):
                msg = f"Command cancelled by user: `{command}`"
                clr.print_warning(msg)
                return msg

        # WSL Sandbox override
        if self.wsl_mode:
            logger.info("Routing command to WSL: %s", command)
            command = f"wsl -- {command}"

        # Emit command to terminal window
        terminal_bridge.on_command_started(command)
        
        # Execute via ActionRouter (which delegates to SystemBackend)
        result = self.action_router.execute_shell(command, from_llm=from_llm)

        # Format output for display — use message for blocked/denied commands
        if not result.success:
            final_out = result.message
            is_error = True
        else:
            final_out = str(result)
            is_error = False

        if result.success and final_out == "Command executed.":
            clr.print_info("Command executed.")
        elif final_out:
            clr.print_shell_output(final_out)

        # Emit output to terminal window
        terminal_bridge.on_command_completed(command, final_out, is_error=is_error)

        if self.worker:
            if hasattr(self.worker, 'cli_output_ready'):
                self.worker.cli_output_ready.emit(final_out)
            else:
                self.worker.output_ready.emit(final_out)

        # Truncate for TTS if needed
        if len(final_out) > MAX_OUTPUT_LENGTH:
            return final_out[:MAX_TTS_LENGTH] + "... (output truncated)"

        return final_out

    def _request_confirmation(self, command: str) -> bool:
        """
        Request user confirmation for a command.
        Uses the registered callback (UI dialog). Defaults to DENY if no
        callback is wired — never auto-approve dangerous operations.
        """
        if self._confirm_callback:
            return self._confirm_callback(command)

        # Safe fallback: deny if no UI callback is available
        logger.warning(
            "No confirmation callback — denying command: %s", command
        )
        print(f"\n[DENIED] No confirmation callback for: {clr.shell(command)}")
        return False

    # ── Capability Commands ──────────────────────────────────────────────────

    def _handle_capabilities_command(self) -> str:
        """Explain the 3-tier permission sandbox (GREEN/YELLOW/RED)."""
        return (
            "Jarvis Permission Sandbox (3-Tier Model):\n"
            "──────────────────────────────────────────\n"
            "Tier GREEN (Auto-execute):\n"
            "  - Allowed: App launch, URL open, system info, web search, media play, read files.\n"
            "  - No confirmation required.\n\n"
            "Tier YELLOW (Confirm first):\n"
            "  - Allowed: Write files, create directories, run arbitrary shell commands, kill processes.\n"
            "  - Jarvis will ALWAYS ask for your permission before proceeding.\n\n"
            "Tier RED (Blocked):\n"
            "  - Blocked: Registry edits, BIOS changes, format drives, shutdown, user account changes.\n"
            "  - These operations are restricted for your safety.\n\n"
            "You can also use 'shell confirmation on' to require confirmation for ALL commands."
        )

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
        """Handle voice control commands (Hindi/English only)."""

        help_text = (
            "Voice Controls (Hindi/English only):\n"
            "-----------------------------------\n"
            "  voice set <voice_id>  - Set TTS voice manually\n"
            "  voice list            - Show recommended voices\n"
            "  voice status          - Show current voice\n"
            "  voice language <lang> - Set TTS language mode (auto/hi/en only)\n"
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
                return (
                    f"Current voice: {self.tts.get_voice()}\n"
                    f"Language mode: {self.tts._language_mode}"
                )
            return "TTS not available."

        # voice language <lang> - RESTRICTED TO EN/HI
        lang_match = re.search(r"^voice\s+language\s+(.+)$", command_text, re.IGNORECASE)
        if lang_match:
            lang = lang_match.group(1).strip().lower()
            if lang in ["hindi", "hi"]:
                mode = "hi"
            elif lang in ["english", "en"]:
                mode = "en"
            elif lang in ["auto"]:
                mode = "auto"
            else:
                return (f"Error: Unsupported language '{lang}'. "
                       "Only 'auto', 'en' (English), or 'hi' (Hindi) supported.\n"
                       "Supported languages: en (English), hi (Hindi), auto (auto-detect)")
            
            if self.tts:
                if self.tts.set_language_mode(mode):
                    return f"Voice language mode set to '{mode}'."
                else:
                    return f"Error: Failed to set language mode to '{mode}'."
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
        """Handle STT language switching commands (Hindi/English only)."""

        help_text = (
            "STT Controls (Hindi/English only):\n"
            "-----------------------------------\n"
            "  stt language <lang>   - Set STT language (auto/hi/en only)\n"
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
            return (
                "Supported STT Languages (Restricted):\n"
                "  - auto (auto-detect between en/hi)\n"
                "  - en (English)\n"
                "  - hi (Hindi)"
            )

        # stt language <lang> - RESTRICTED TO EN/HI
        lang_match = re.search(r"^stt\s+language\s+(.+)$", command_text, re.IGNORECASE)
        if lang_match:
            lang_input = lang_match.group(1).strip().lower()
            
            # Normalize to ISO 639-1 codes
            if lang_input in ["hindi", "hi"]:
                lang_code = "hi"
            elif lang_input in ["english", "en"]:
                lang_code = "en"
            elif lang_input in ["auto"]:
                lang_code = "auto"
            else:
                return (f"Error: Unsupported language '{lang_input}'. "
                       "Only 'auto', 'en' (English), or 'hi' (Hindi) supported.\n"
                       "Use 'stt language list' to see supported languages.")

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
                            self._stt_language = lang_code
                            display = lang_input if lang_input in ["english", "hindi", "en", "hi", "auto"] else lang_code
                            return f"STT language set to '{display}' ({lang_code}). Speak now!"
                except Exception as e:
                    return f"Error setting STT language: {e}"

            self._stt_language = lang_code
            return f"STT language set to '{lang_code}' (will apply on next restart)."

        return help_text

    def _handle_shell_command(self, command_text: str) -> str:
        """Handle shell configuration and sandbox controls."""
        
        help_text = (
            "Shell & Sandbox Controls:\n"
            "-----------------------------------\n"
            "  shell confirmation on/off - Toggle ask-before-exec\n"
            "  shell wsl on/off         - Toggle WSL sandbox for commands\n"
            "  shell seamless on/off    - Toggle Smart-Switch to Cloud (Gemini/Groq)\n"
            "  shell status             - Show current shell settings\n"
        )

        # shell status
        if re.search(r"^shell\s+status$", command_text, re.IGNORECASE):
            conf = "ON" if self.confirmation_mode else "OFF"
            wsl = "ON" if self.wsl_mode else "OFF"
            seamless = "ON" if self.seamless_mode else "OFF"
            return (
                "Shell Settings:\n"
                f"  Confirmation Mode: {conf}\n"
                f"  WSL Sandbox Mode:  {wsl}\n"
                f"  Seamless Cloud:    {seamless}"
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

        # shell seamless on/off
        seamless_match = re.search(r"^shell\s+seamless\s+(on|off)$", command_text, re.IGNORECASE)
        if seamless_match:
            state = seamless_match.group(1).lower() == "on"
            self.seamless_mode = state
            return f"Seamless Cloud auto-switch turned {'ON' if state else 'OFF'}."

        return help_text
