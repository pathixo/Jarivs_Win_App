# Swara AI (Jarvis v2.0.0) Release Notes

Welcome to the **v2.0.0** release of our standalone Windows assistant application! This major update brings a complete visual overhaul featuring an extreme glassmorphism aesthetic, along with highly requested functional "Quick Start" integrations and crucial backend stability fixes.

## 🌟 What's New in v2.0.0

### Complete Visual Overhaul
- **Extreme Glassmorphism UI**: We've completely redesigned the dashboard to feature a stunning, edge-to-edge dark aurora background. All panels and cards now feature true glassmorphic blending (`rgba(255,255,255,0.05)`) with custom bright inner directional strokes and deep 40px drop shadows to create a vibrant floating effect.
- **Swara AI Branding**: Rebranded the primary dashboard navigation from "AI Hub" to "Swara AI", and professionalized the hero text to a sleek "Ready to assist you."
- **Clean Title Bar**: Removed the clunky "Jarvis AI" text from the top left for a cleaner, modern frameless window experience.

### New Interactive Quick Start Services
The home page dashboard now features three fully functional, built-in mini-apps to jumpstart your workflow:
- **🎨 Image Generation**: Instantly generate AI images directly from the dashboard! Clicking the card opens a prompt dialog and utilizes high-quality instantaneous models (via Pollinations API fallback for out-of-the-box reliability) to generate and display the result in a customized graphic viewer.
- **⟨/⟩ Code Assistant**: Choose your brain before you code. A new interactive dialog lets you select your preferred LLM (e.g., `gemini-2.0-flash`, `llama-3.3-70b-versatile`, `gpt-4o`) before launching the voice assistant, instantly hot-swapping the active pipeline model.
- **🌐 Web Search**: Ask questions or search topics via a new popup dialog. The dashboard hooks directly into the `DuckDuckGo` backend action router and displays the top 5 web results, complete with clickable URLs and descriptive snippets.

### Personalization & Control
- **Background Dimming Control**: Added a real-time `Opacity Slider` directly to the dashboard home page. This allows you to dynamically adjust a dark overlay behind the UI elements to tone down the vivid aurora background when you need more focus.

## 🛠️ Bug Fixes & Stability Improvements

- **Resolved Audio Stuttering (TTS)**: Fixed a severe race condition in the PyQt6 `QMediaPlayer` event loop where both `StoppedState` and `EndOfMedia` signals were firing simultaneously. Voice queues will no longer overlap and cut themselves off mid-sentence.
- **Silenced FFmpeg Console Spam**: Applied the `AV_LOG_LEVEL=quiet` environment variable to completely suppress the distracting `[mp3 @ 00...] Estimating duration from bitrate` logs that were flooding the terminal.
- **Memory Engine Crash Fix**: Fixed a fatal exception that occurred during the post-conversation background memory extraction phase by properly routing the pipeline to `auto_extract_async`.

## 📦 Getting Started
To experience the new dashboard:
```bash
python -m Jarvis.app
```
From there, you can control your LLMs, adjust your background opacity, test the new Quick Start apps, or hit the **Launch Assistant** button to start the voice orb!
