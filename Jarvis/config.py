import os
from dotenv import load_dotenv

load_dotenv()

# Ollama Configuration (Local Brain)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:2b")

# Porcupine (Wake Word) API Key
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")

# Porcupine Model Path (Wait for user to provide, or default)
PORCUPINE_MODEL_PATH = os.getenv("PORCUPINE_MODEL_PATH", "")

# Default Wake Word (Requires Porcupine model path)
WAKE_WORD = "jarvis"

# TTS Voice (Microsoft Edge TTS)
TTS_VOICE = "en-US-JennyNeural"

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Ensure logs directory exists
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)
