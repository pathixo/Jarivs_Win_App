"""
Terminal Branding Module
========================
ASCII art, styling, and visual theming for the Jarvis terminal window.
Inspired by Gemini CLI with a custom Jarvis aesthetic.
"""

from enum import Enum

# ─── Color Constants (ANSI Escape Codes) ───────────────────────────────────
class Colors:
    """ANSI color codes for terminal output."""
    
    # Standard colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Styling
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'


class StatusColor(Enum):
    """Status-based color scheme."""
    LISTENING = Colors.BRIGHT_GREEN
    PROCESSING = Colors.BRIGHT_YELLOW
    ERROR = Colors.BRIGHT_RED
    COMMAND = Colors.BRIGHT_CYAN
    OUTPUT = Colors.BRIGHT_WHITE
    DIM_TEXT = Colors.BRIGHT_BLACK


# ─── ASCII Art Logos ───────────────────────────────────────────────────────
def get_jarvis_logo_small():
    """Small Jarvis ASCII logo (for header)."""
    return r"""
    ║     ┃ ┃  ╺┓ ╻┏━┓ ╻ ┃╻ ┏┓ 
    ║     ┃ ┗━  ┗┫ ┫╹┫ ╸┃╹ ┗┓ 
    ╻┏━┓┏┓┏┓╋╸  ╸┗━╹  ╹ ╹  ╸╹  
    ┃┣━┫┣┫┃┣┋┗┛ ┗┫    ┏┓ ╻┏━┓
    ┗┗━┛┛┗┗┛┗━━━┗━   ┗┛ ┗┗━┛
    """.strip()


def get_jarvis_logo_large():
    """Large decorative Jarvis ASCII logo."""
    return r"""
  ╔══════════════════════════════════════════════════════════╗
  ║                                                          ║
  ║   ░▒▓███████▓▒░ ░▒▓██████▓▒░  ░▒▓███████▓▒░            ║
  ║  ░▓█          █▓ ▓█         █▓ █           █            ║
  ║  ░█  ░▒▓██▓▒░  █ ░█  ░▒▓██▓▒░  █  ░▒▓██▓▒░ █           ║
  ║  ░█  █       █  █ ░█  █       █  █       █  █           ║
  ║  ░▓█  ░▒▓██▓▒░  █ ░▓█  ░▒▓██▓▒░  ░▒▓██▓▒░ ░█           ║
  ║   ░▒▓███████▓▒░ ░▒▓███████▓▒░  ░▒▓███████▓▒░            ║
  ║                                                          ║
  ║              Autonomous AI Command Terminal             ║
  ║                                                          ║
  ╚══════════════════════════════════════════════════════════╝
    """.strip()


def get_jarvis_banner(status="LISTENING", persona="Witty", voice="en-GB-RyanNeural"):
    """Generate the terminal banner with status info."""
    banner = f"""
╔════════════════════════════════════════════════════════════╗
║  JARVIS - Command Execution Terminal                       ║
║════════════════════════════════════════════════════════════║
║  Status: {status:<18} │ Persona: {persona:<15}           ║
║  Voice: {voice:<40}                           ║
╚════════════════════════════════════════════════════════════╝
    """.strip()
    return banner


def get_divider(width=60, style="─"):
    """Generate a horizontal divider."""
    return f"  {style * width}"


def get_command_prompt(timestamp="", command_index=0):
    """Generate a formatted command prompt."""
    if timestamp:
        return f"  [{timestamp}] [EXEC] "
    return f"  [{command_index:03d}] [EXEC] "


def colorize_text(text, color):
    """Apply ANSI color to text."""
    if isinstance(color, StatusColor):
        color_code = color.value
    else:
        color_code = color
    return f"{color_code}{text}{Colors.RESET}"


def colorize_command(command_text):
    """Colorize a command for display."""
    return colorize_text(command_text, StatusColor.COMMAND)


def colorize_output(output_text, is_error=False):
    """Colorize command output."""
    if is_error:
        return colorize_text(output_text, StatusColor.ERROR)
    return colorize_text(output_text, StatusColor.OUTPUT)


def colorize_status(status_text, status_type="normal"):
    """Colorize status text based on type."""
    if status_type == "listening":
        return colorize_text(status_text, StatusColor.LISTENING)
    elif status_type == "processing":
        return colorize_text(status_text, StatusColor.PROCESSING)
    elif status_type == "error":
        return colorize_text(status_text, StatusColor.ERROR)
    return colorize_text(status_text, StatusColor.OUTPUT)


# ─── Terminal Block Templates ───────────────────────────────────────────────
def create_command_block(command_text, timestamp="", command_num=0):
    """Create a formatted command display block."""
    prompt = f"  [{timestamp}]" if timestamp else f"  [{command_num:03d}]"
    return f"{colorize_text(prompt, StatusColor.DIM_TEXT)} {colorize_command(command_text)}"


def create_output_block(output_lines, is_error=False):
    """Create a formatted output block from lines."""
    if not output_lines:
        return ""
    
    formatted_lines = []
    for line in output_lines:
        formatted_line = f"  {colorize_output(line, is_error)}"
        formatted_lines.append(formatted_line)
    
    return "\n".join(formatted_lines)


def create_status_line(message, icon="●"):
    """Create a formatted status line."""
    return f"{colorize_text(icon, StatusColor.LISTENING)} {message}"


# ─── Themed Widgets/Text ───────────────────────────────────────────────────
def get_startup_header():
    """Get the full startup header with logo."""
    logo = get_jarvis_logo_large()
    separator = get_divider(width=62)
    return f"\n{logo}\n\n{separator}\n"


def get_ready_message():
    """Get the 'ready' message."""
    return colorize_status("✓ Terminal ready for command execution", "listening")


def get_waiting_message():
    """Get the 'waiting for commands' message."""
    return colorize_status("⟳ Waiting for commands from Jarvis...", "processing")


def get_error_message(error_text):
    """Get a formatted error message."""
    return colorize_status(f"✗ Error: {error_text}", "error")
