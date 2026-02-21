<p align="center">
  <h1 align="center">🧠 Jarvis</h1>
  <p align="center">
    <strong>Autonomous AI Assistant for Windows</strong>
  </p>
  <p align="center">
    Voice-controlled · Multi-LLM · Shell Execution · Real-time TTS
  </p>
  <p align="center">
    <a href="#quickstart">Quickstart</a> •
    <a href="#features">Features</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#configuration">Configuration</a> •
    <a href="#commands">Commands</a> •
    <a href="#contributing">Contributing</a>
  </p>
</p>

---

## What is Jarvis?

Jarvis is a **desktop AI assistant** that listens to your voice, understands natural language, executes system commands, and speaks back — all running natively on Windows with a PyQt6 interface.

Unlike chatbots that just *talk about* doing things, Jarvis **actually does them**. Say *"create a folder called Projects"* and it runs the PowerShell command. Ask *"what's running on port 3000?"* and it checks for you.

```
You:     "Hey Jarvis, list all Python files in Downloads"
Jarvis:  Here are your Python files.
         [EXEC] Get-ChildItem $env:USERPROFILE\Downloads -Filter *.py
         > script.py  main.py  utils.py
```

---

## Features

| Feature | Description |
|---|---|
| 🎙️ **Voice Interface** | Wake word detection ("Jarvis") via Porcupine + real-time speech-to-text via Faster-Whisper |
| 🧠 **Multi-LLM Brain** | Switch between **Groq**, **Gemini**, **Grok**, or local **Ollama** — at runtime |
| ⚡ **Shell Execution** | AI-generated PowerShell commands are auto-extracted and executed safely |
| 🔊 **Text-to-Speech** | Natural voice responses via Edge-TTS (Microsoft neural voices) |
| 🛡️ **Safety Guards** | Dangerous commands (`format`, `rm -rf`, `diskpart`) are blocked automatically |
| 🔄 **Provider Failover** | If one LLM is down or rate-limited, Jarvis auto-switches to another |
| 💬 **Conversation Memory** | Sliding-window context (20 messages) for multi-turn conversations |
| 🎨 **Colored Terminal** | Semantic coloring — cyan for input, green for AI, yellow for commands, magenta for output |
| 🖥️ **Desktop UI** | PyQt6 window with embedded terminal, thinking orb, and system tray |
| 📦 **One-Click Launch** | `run_jarvis.bat` handles venv, dependencies, and env setup automatically |

---

## Quickstart

### Prerequisites

- **Python 3.10+** — [Download](https://python.org/downloads/)
- **API Key** (at least one):
  - [Groq](https://console.groq.com/keys) (free, fastest) ← **recommended**
  - [Gemini](https://aistudio.google.com/apikey) (free tier available)
  - [Ollama](https://ollama.com) (fully local, no API key needed)

### Setup (3 steps)

```powershell
# 1. Clone and enter the project
git clone https://github.com/your-username/Antigravity.git
cd Antigravity

# 2. Create virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r Jarvis\requirements.txt

# 3. Configure your API key
copy .env.example .env
notepad .env          # Paste your API key, set LLM_PROVIDER
```

### Run

```powershell
.\run_jarvis.bat
```

Or manually:
```powershell
.venv\Scripts\activate
python -m Jarvis.main
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      Jarvis App                          │
│                                                          │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐   │
│  │ Listener │───▶│ Orchestrator │───▶│    Brain      │   │
│  │ (Voice)  │    │  (Router)    │◀───│ (Multi-LLM)   │   │
│  └──────────┘    │              │    └───────────────┘   │
│       │          │  ┌────────┐  │     ▲  ▲  ▲  ▲        │
│       │          │  │ Tools  │  │     │  │  │  │         │
│       │          │  └────────┘  │     │  │  │  └ Ollama  │
│       │          │  ┌────────┐  │     │  │  └── Grok     │
│       │          │  │ Shell  │  │     │  └───── Gemini   │
│       │          │  └────────┘  │     └──────── Groq     │
│       ▼          └──────────────┘                        │
│  ┌──────────┐    ┌──────────────┐                        │
│  │  STT     │    │     TTS      │                        │
│  │(Whisper) │    │  (Edge-TTS)  │                        │
│  └──────────┘    └──────────────┘                        │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              PyQt6 UI (Window + Tray)             │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### Project Structure

```
Antigravity/
├── run_jarvis.bat              # One-click launcher
├── .env                        # API keys & config (git-ignored)
├── .env.example                # Reference config template
│
└── Jarvis/
    ├── main.py                 # App entry point — wires everything together
    ├── config.py               # Environment loading & constants
    ├── requirements.txt        # Python dependencies
    │
    ├── core/
    │   ├── brain.py            # Multi-provider LLM interface (Groq/Gemini/Grok/Ollama)
    │   ├── orchestrator.py     # Command router & shell executor
    │   ├── tools.py            # Sandboxed file system operations
    │   └── colors.py           # Terminal color utilities
    │
    ├── input/
    │   ├── listener.py         # Autonomous voice listener (wake word + recording)
    │   ├── audio_capture.py    # Microphone audio capture
    │   └── transcribe_worker.py # Faster-Whisper STT worker thread
    │
    ├── output/
    │   ├── tts.py              # Edge-TTS text-to-speech
    │   └── visuals.py          # Thinking orb animation
    │
    ├── ui/
    │   ├── window.py           # Main PyQt6 window
    │   └── tray.py             # System tray icon & menu
    │
    └── tests/
        └── test_orchestrator.py # Unit tests for command routing
```

---

## Configuration

All configuration is done via the `.env` file in the project root:

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | Active LLM backend | `ollama` |
| `GROQ_API_KEY` | Groq Cloud API key | — |
| `GROQ_MODEL` | Groq model name | `llama-3.3-70b-versatile` |
| `GEMINI_API_KEY` | Google Gemini API key | — |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.0-flash` |
| `GROK_API_KEY` | xAI Grok API key | — |
| `GROK_MODEL` | Grok model name | `grok-3-mini-fast` |
| `OLLAMA_URL` | Ollama API endpoint | `http://localhost:11434/api/generate` |
| `OLLAMA_MODEL` | Ollama model name | `gemma:2b` |
| `PORCUPINE_ACCESS_KEY` | Picovoice wake word key | — |
| `TTS_VOICE` | Edge-TTS voice ID | `en-US-GuyNeural` |

### Provider Comparison

| Provider | Speed | Intelligence | Cost | Needs Internet |
|---|---|---|---|---|
| **Groq** | ⚡ Fastest | 🧠🧠🧠 (Llama 3.3 70B) | Free tier | Yes |
| **Gemini** | Fast | 🧠🧠🧠 (Flash) | Free tier | Yes |
| **Grok** | Fast | 🧠🧠🧠 (xAI) | Paid | Yes |
| **Ollama** | Varies | 🧠 (depends on model) | Free | No |

---

## Commands

### Voice Commands
Just say **"Jarvis"** followed by your request:
- *"Jarvis, what time is it?"*
- *"Jarvis, open notepad"*
- *"Jarvis, list files in my Downloads"*
- *"Jarvis, create a folder called Projects"*
- *"Jarvis, how much RAM am I using?"*

### Brain Control Commands
Type or say these to manage the LLM at runtime:

```
llm status                    — Show provider, model, and health
llm models                    — List available models
llm provider <name>           — Switch provider (groq/gemini/grok/ollama)
llm use <model>               — Switch model
llm set temperature <0..2>    — Adjust creativity
llm set max_tokens <int>      — Set response length limit
llm set timeout <seconds>     — Set request timeout
llm prompt show               — View system prompt
llm prompt set <text>         — Override system prompt
llm reset                     — Reset all settings to defaults
clear memory                  — Clear conversation history
```

### Direct Shell Commands
These bypass the LLM and execute directly:
```
dir                           — List directory contents
git status                    — Check git status
pip list                      — List Python packages
ipconfig                      — Show network config
tasklist                      — List running processes
python script.py              — Run a Python script
```

---

## Terminal Color Scheme

| Color | Meaning | Tag |
|---|---|---|
| 🔵 **Bright Cyan** | Your input (voice/typed) | `[YOU]` |
| 🟢 **Bright Green** | AI responses | `[JARVIS]` |
| 🟡 **Bright Yellow** | Shell commands being executed | `[EXEC]` |
| 🟣 **Magenta** | Shell command output | *(raw output)* |
| 🔴 **Bright Red** | Errors | `[ERROR]` |
| 🔵 **Bright Blue** | System info | `[INFO]` |
| ⚪ **Dark Gray** | Debug/timing info | *(dimmed)* |

---

## How It Works

1. **Listener** detects the wake word "Jarvis" via Porcupine
2. **Audio Capture** records your voice until silence is detected
3. **Faster-Whisper** transcribes the audio to text locally
4. **Orchestrator** classifies the intent:
   - Is it a shell command? → Execute directly in PowerShell
   - Is it a brain meta-command? → Adjust settings
   - Otherwise → Send to the **Brain** (LLM)
5. **Brain** generates a response, possibly containing `[SHELL]...[/SHELL]` tags
6. **Orchestrator** extracts and executes any shell commands, with safety checks
7. **TTS** converts the response to speech via Edge-TTS
8. **UI** displays everything in the embedded terminal with color coding

---

## Safety

Jarvis includes safety guards for commands generated by the LLM:

**Blocked commands** (auto-detected):
- `format c:` — Drive formatting
- `rm -rf` / `Remove-Item -Recurse` — Recursive deletion
- `diskpart` — Disk partitioning
- `bcdedit` — Boot config changes
- `reg delete` — Registry deletion
- `shutdown` — System shutdown

If a dangerous command is detected, Jarvis will block it and display a warning instead of executing it.

---

## Development

### Running Tests
```powershell
.venv\Scripts\python.exe -m unittest Jarvis.tests.test_orchestrator -v
```

### Testing the Brain Directly
```python
from Jarvis.core.brain import Brain
brain = Brain()
response = brain.generate_response("Hello, what can you do?")
print(response)
```

### Switching Providers Programmatically
```python
from Jarvis.core.brain import Brain
brain = Brain(provider="groq")       # Start with Groq
brain.set_provider("gemini")          # Switch to Gemini
brain.set_model("gemini-2.0-flash")   # Change model
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Desktop UI | PyQt6 |
| Wake Word | Porcupine (Picovoice) |
| Speech-to-Text | Faster-Whisper (local) |
| Text-to-Speech | Edge-TTS (Microsoft Neural) |
| LLM Providers | Groq · Gemini · Grok · Ollama |
| Shell | PowerShell (Windows native) |
| Config | python-dotenv |

---

## Roadmap

- [ ] Streaming LLM responses (token-by-token display)
- [ ] Multi-step task execution (chained commands)
- [ ] Function calling / tool use via LLM APIs
- [ ] Plugin system for extensible tools
- [ ] Cross-platform support (macOS / Linux)
- [ ] WebSocket-based remote access
- [ ] Conversation persistence (save/load sessions)

---

## License

This project is proprietary. All rights reserved.

---

<p align="center">
  Built with focus and intention.
</p>
