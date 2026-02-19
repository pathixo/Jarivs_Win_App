# Jarvis Hybrid Brain Project

This repository hosts the **Jarvis Hybrid Brain** application, an autonomous AI development environment designed to function as a split-brain organism with Local and Cloud cortices.

## Project Structure
- **Jarvis/**: Main application source code.
    - **core/**: Brain and Orchestrator logic.
    - **ui/**: PyQt6 User Interface.
    - **input/**: Voice and Audio capture.
    - **output/**: TTS and Visualizations.

## Getting Started

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com) (for Local Brain)

### Installation
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r Jarvis/requirements.txt
   ```
3. Set up environment variables (see `Jarvis/config.py`).

### Running the App
Double-click `run_jarvis.bat` or run:
```powershell
.\run_jarvis.bat
```

## Features
- **Hybrid Intelligence**: Routes simple commands locally and complex reasoning to a local LLM (Ollama).
- **Voice Interface**: Wake word detection ("Jarvis") and text-to-speech response.
- **Embedded Terminal**: Execute shell commands directly from the UI.
- **Integrated Audio**: Seamless voice responses without external popups.

For more detailed documentation, see [Jarvis/README.md](Jarvis/README.md).
