import sys
import os
from dotenv import load_dotenv

def get_base_path():
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))

def get_app_data_path():
    """Get writable path for logs and config"""
    if getattr(sys, 'frozen', False):
        path = os.path.join(os.getenv('APPDATA'), 'Antigravity', 'Jarvis')
    else:
        path = os.path.dirname(os.path.abspath(__file__))
    
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

# Load env from AppData if frozen, else local
env_path = os.path.join(get_base_path(), ".env")
load_dotenv(dotenv_path=env_path)

# ─────────────────────── LLM Provider Config ────────────────────────────────
# Active provider: "ollama" | "gemini" | "groq" | "grok"
# Default is "gemini" — conversation goes through Gemini API for quality.
# Local Ollama is still used for action classification (hybrid mode).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Ollama Configuration (Local Brain — used for action classification in hybrid mode)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "jarvis-action")

# Ollama Model Auto-Selection
# When enabled, Jarvis picks the fast model for simple queries, the logic
# model for complex reasoning, and the code model for programming tasks.
OLLAMA_FAST_MODEL  = os.getenv("OLLAMA_FAST_MODEL",  "jarvis-action")          # speed
OLLAMA_LOGIC_MODEL = os.getenv("OLLAMA_LOGIC_MODEL", "llama3.2:3b")           # reasoning
OLLAMA_CODE_MODEL  = os.getenv("OLLAMA_CODE_MODEL",  "llama3.2:3b")           # coding
OLLAMA_AUTO_SELECT = os.getenv("OLLAMA_AUTO_SELECT", "true").lower() == "true"

# Gemini Configuration (Google Cloud)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Groq Configuration (Groq Cloud — fast inference)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ─────────────────────── Intent Engine Config ────────────────────────────────
# Deep thinking intent analysis powered by Groq (runs concurrently — no latency cost)
# Set INTENT_ENGINE_ENABLED=false to disable if Groq rate limits are a concern.
INTENT_ENGINE_ENABLED     = os.getenv("INTENT_ENGINE_ENABLED", "true").lower() == "true"
GROQ_INTENT_MODEL         = os.getenv("GROQ_INTENT_MODEL", "llama3-70b-8192")
INTENT_CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.6"))

# Grok Configuration (xAI Cloud)
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3-mini-fast")

# ─────────────────────── Wake Word & Audio ──────────────────────────────────
# Porcupine (Wake Word) API Key
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")

# Porcupine Model Path
PORCUPINE_MODEL_PATH = os.getenv("PORCUPINE_MODEL_PATH", "")

# Default Wake Word
WAKE_WORD = "jarvis"

# TTS Voice
TTS_VOICE = "en-IE-EmilyNeural"

# Default Persona
DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "friday")

# ─────────────────────── Pipeline Config ────────────────────────────────────
# STT Provider: "auto" | "groq" | "gemini" | "local"
#   local — Always use local faster-whisper (primary, unlimited usage)
#   groq  — Always use Groq Whisper API (cloud, 8 hour/day limit)
#   gemini — Always use Gemini 1.5 Flash
#   auto  — Local with Gemini fallback
STT_PROVIDER = os.getenv("STT_PROVIDER", "local")

# TTS Engine: "auto" | "kokoro" | "edge"
#   auto   — Kokoro (local GPU) with edge-tts fallback
#   kokoro — Always use Kokoro ONNX (local, lowest latency)
#   edge   — Always use edge-tts (cloud, Microsoft Edge voices)
TTS_ENGINE = os.getenv("TTS_ENGINE", "auto")

# Pipeline Mode: "streaming" | "sequential"
#   streaming   — Overlapping STT→LLM→TTS pipeline (low latency)
#   sequential  — Classic sequential processing
PIPELINE_MODE = os.getenv("PIPELINE_MODE", "streaming")

# Barge-In: Allow user to interrupt Jarvis mid-speech
BARGE_IN_ENABLED = os.getenv("BARGE_IN_ENABLED", "true").lower() == "true"

# VAD Engine: "silero" | "energy"
#   silero — Neural VAD (accurate, ~1ms per chunk)
#   energy — RMS energy threshold (legacy)
VAD_ENGINE = os.getenv("VAD_ENGINE", "silero")

# Response Style: "concise" | "detailed"
#   concise  — Short replies, optimized for voice
#   detailed — Longer replies for complex queries
RESPONSE_STYLE = os.getenv("RESPONSE_STYLE", "concise")

# Kokoro TTS Model paths (auto-downloaded on first use)
KOKORO_MODEL_PATH = os.getenv("KOKORO_MODEL_PATH", "")
KOKORO_VOICES_PATH = os.getenv("KOKORO_VOICES_PATH", "")

# ─────────────────────── Paths ──────────────────────────────────────────────
BASE_DIR = get_base_path()
DATA_DIR = get_app_data_path()
LOGS_DIR = os.path.join(DATA_DIR, "logs")
AVATARS_DIR = os.path.join(DATA_DIR, "avatars")
VOICE_PROFILES_DIR = os.path.join(DATA_DIR, "voice_profiles")
DB_PATH = os.path.join(DATA_DIR, "jarvis.db")

for _dir in [LOGS_DIR, AVATARS_DIR, VOICE_PROFILES_DIR]:
    if not os.path.exists(_dir):
        os.makedirs(_dir, exist_ok=True)
