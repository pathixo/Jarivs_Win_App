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
load_dotenv()

# Ollama Configuration (Local Brain)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:2b")

# Porcupine (Wake Word) API Key
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")

# Porcupine Model Path
PORCUPINE_MODEL_PATH = os.getenv("PORCUPINE_MODEL_PATH", "")

# Default Wake Word
WAKE_WORD = "jarvis"

# TTS Voice
TTS_VOICE = "en-US-GuyNeural"

# Paths
BASE_DIR = get_base_path()
DATA_DIR = get_app_data_path()
LOGS_DIR = os.path.join(DATA_DIR, "logs")

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR, exist_ok=True)
