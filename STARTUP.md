# 🧠 Welcome to Project Antigravity (Jarvis v2.0) 🚀

Welcome, Agent! You are now part of the team building **Jarvis**, the most advanced autonomous OS assistant for Windows. This guide will get you up and running in minutes.

---

## 🛠️ Prerequisites

Before you dive in, ensure you have the following installed:

*   **Python 3.10+ (64-bit)** 🐍
*   **Git** 🌿
*   **Ollama** (Required for local "Brain" processing) 🧠
    *   Download at [ollama.com](https://ollama.com)
*   **Optional (but recommended):**
    *   **Groq API Key** (For lightning-fast STT/LLM) ⚡
    *   **Gemini API Key** (For high-quality reasoning) ✨

---

## 📥 Getting Started

### 1. Clone & Setup 
Run the automated bootstrapper. It handles the virtual environment and all dependencies.

```powershell
# Clone the repo
git clone https://github.com/your-username/Antigravity.git
cd Antigravity

# Run the installer
.\Setup.bat
```

### 2. Configure Your ⚙️ `.env`
Copy the example environment file and add your API keys.

```powershell
cp .env.example .env
```
Open `.env` and fill in:
*   `GEMINI_API_KEY` (Get it from Google AI Studio)
*   `GROQ_API_KEY` (Get it from Groq Console)
*   `LLM_PROVIDER` (Set to `gemini` or `groq`)

### 3. Pull the Local Brain 🧠
Jarvis uses a custom-tuned model for action classification. Run this to pull the necessary models:
```powershell
ollama pull llama3.2:3b
# If you have the custom jarvis-action model:
# ollama create jarvis-action -f Modelfile.jarvis
```

---

## 🚀 Running Jarvis

Launch the application using the batch script:

```powershell
.\run_jarvis.bat
```

*   **GUI Mode:** By default, it opens the **Jarvis Dashboard** 🖥️.
*   **Voice Mode:** Jarvis lives in your System Tray 📥. Say **"Jarvis"** to wake him up!
*   **Logs:** If something goes wrong, check `Jarvis/logs/crash.log` 📄.

---

## 🏗️ Project Structure

| Directory | Description |
| :--- | :--- |
| `Jarvis/core/` | 🧠 The "Brain" - Orchestrator, Intent Engine, Security Validator. |
| `Jarvis/ui/` | 🎨 The "Face" - PyQt6 Dashboard, Tray, and Overlay. |
| `Jarvis/input/` | 👂 The "Ears" - Audio processing, STT Router, and VAD. |
| `Jarvis/output/` | 🗣️ The "Voice" - TTS (Kokoro/Edge) and Visuals. |
| `Jarvis/sft/` | 🧪 Fine-tuning pipeline for Gemma 2B. |
| `Jarvis/plugins/` | 🧩 Extensible tools (e.g., Spotify, Browser control). |

---

## 🛠️ How to Contribute

### 🧩 Adding a Plugin
Want to give Jarvis a new skill? Drop a `.py` file into `Jarvis/plugins/`.
Check `Jarvis/plugins/hello_example.py` for a template!

### 🧪 Testing
We take stability seriously. Run the tests before pushing:
```powershell
pytest Jarvis/tests/
```

### 🧠 Fine-Tuning (SFT)
To improve Jarvis's command accuracy:
1.  Generate a dataset: `python -m Jarvis.sft.generate_dataset`
2.  Train the model: `python -m Jarvis.sft.train_qlora`

---

## 🛡️ Security First
*   **Safe Shell:** Never use raw string formatting for PowerShell. Use `Jarvis.core.powershell_safe`.
*   **Redaction:** Jarvis automatically masks secrets in logs. Keep it that way!
*   **Path Safety:** Always validate file paths to prevent traversal attacks.

---

## 🆘 Need Help?
*   Check `docs/INDEX.md` for deep-dive documentation.
*   Read `ARCHITECTURE_UPGRADE.md` to see recent system changes.
*   Ping the lead developer if you're stuck!

---
<p align="center">
  <i>"I'm sorry, Dave. I'm afraid I can't do that... Just kidding, I'm Jarvis!"</i> 😉
</p>
