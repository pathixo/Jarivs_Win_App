# Jarvis Hybrid Brain
An autonomous AI development environment acting as a split-brain organism.

## Overview
Jarvis consists of two main "cortices":
- **Local Cortex**: Fast, handles I/O (Voice, Wake words, simple routing).
- **Cloud Cortex**: Smart, handles complex reasoning and code generation (Gemini 1.5 Pro).

## Architecture
- **Language**: Python 3.10+
- **Frontend**: PyQt6 (PySide6 potential for future)
- **Voice**: Porcupine (Wake Word) + Faster-Whisper (STT) + Edge-TTS (Audio Output)
- **Brain**: Google Gemini 1.5 Pro via Google Generative AI SDK

## Setup
1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Or verify_imports.py ensures paths are correct
   ```
2. Install dependencies:
   ```bash
   pip install -r Jarvis/requirements.txt
   ```
3. Configure API Keys in `Jarvis/config.py`:
   - `GOOGLE_API_KEY`: Required for Brain functions.
   - `PORCUPINE_ACCESS_KEY`: Required for Wake Word detection.

## Running nicely
To run the main application:
```bash
python Jarvis/main.py
```

## Features (Proof of Concept)
- **Local Terminal**: Embedded command-line interface.
- **Voice Commands**: "Jarvis" wake word detection (requires key).
- **Context Awareness**: Routing between local commands (fast) and cloud brain (smart).
- **Thinking Orb**: Visual feedback for system status.

## Current Limitations
- WebView integration is placeholder.
- Voice capabilities require valid API keys.
- STT implementation is basic.
