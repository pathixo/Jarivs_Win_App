# Jarvis OS Agent Architecture Upgrade

**Version:** 2.0  
**Date:** March 5, 2026  
**Author:** Swara-Core Architect  

---

## Executive Summary

This document outlines the architectural upgrade of Jarvis from a voice-native assistant to a fully extensible Operating System Agent. The upgrade introduces 6 major capabilities while respecting the RTX 2050 4GB VRAM constraint through hybrid API/local routing strategies.

---

## Current Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        PyQt6 Main Thread                     │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ MainWindow  │  │  TrayIcon   │  │   SettingsWindow     │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬───────────┘ │
│         │                │                     │             │
│         └────────────────┴─────────────────────┘             │
│                          │                                   │
│                    ┌─────▼─────┐                             │
│                    │  Worker   │ ◄─── pyqtSignal bridge      │
│                    └─────┬─────┘                             │
└──────────────────────────┼──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Listener     │  │ Orchestrator  │  │     TTS       │
│  (STT Thread) │  │ (LLM Thread)  │  │  (Audio Out)  │
└───────────────┘  └───────┬───────┘  └───────────────┘
                           │
                    ┌──────▼──────┐
                    │ActionRouter │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │SafetyEng │ │SystemBack│ │ToolRegis │
        └──────────┘ └──────────┘ └──────────┘
```

---

## Upgraded Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PyQt6 Main Thread                              │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ MainWindow  │  │OverlayWidget│  │  TrayIcon │  │  SettingsWindow  │  │
│  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  └────────┬─────────┘  │
│         └────────────────┴───────────────┴─────────────────┘            │
│                                    │                                     │
│                              ┌─────▼─────┐                               │
│                              │  Worker   │                               │
│                              └─────┬─────┘                               │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
     ┌───────────────────────────────┼───────────────────────────────┐
     ▼                               ▼                               ▼
┌─────────────┐              ┌───────────────┐              ┌─────────────┐
│  Listener   │              │ Orchestrator  │              │     TTS     │
│(STT Thread) │              │ (LLM Thread)  │              │ (Audio Out) │
└─────────────┘              └───────┬───────┘              └─────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             ┌────────────┐  ┌─────────────┐  ┌─────────────┐
             │ActionRouter│  │PluginManager│  │VisionRouter │
             └─────┬──────┘  └──────┬──────┘  └──────┬──────┘
                   │                │                │
     ┌─────────────┼────────┐       │         ┌──────┴──────┐
     ▼             ▼        ▼       ▼         ▼             ▼
┌─────────┐ ┌──────────┐ ┌─────┐ ┌──────┐ ┌───────┐  ┌───────────┐
│SafetyEng│ │SystemBack│ │Tools│ │Plugins│ │LocalOCR│  │GeminiAPI │
└─────────┘ └──────────┘ └─────┘ └──────┘ └───────┘  └───────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             ┌────────────┐  ┌─────────────┐  ┌─────────────┐
             │WorkflowEng │  │ MobileAPI   │  │ComputeAgent │
             └────────────┘  └─────────────┘  └─────────────┘
```

---

## Feature 1: Plugin Ecosystem

### Purpose
Enable dynamic loading of external Python modules without modifying core code.

### Architecture

```
Jarvis/core/plugins/
├── __init__.py      # Exports PluginManager
├── base.py          # Abstract JarvisPlugin class
├── registry.py      # Plugin discovery & lifecycle
├── hooks.py         # Event hook definitions
└── loader.py        # Safe dynamic import utility
```

### Interface: `JarvisPlugin` (base.py)

```python
class JarvisPlugin(ABC):
    """Base class for all Jarvis plugins."""
    
    name: str                    # Unique plugin identifier
    version: str                 # Semantic version
    description: str             # Human-readable description
    author: str                  # Plugin author
    dependencies: List[str]      # Required pip packages
    
    @abstractmethod
    def on_load(self) -> None:
        """Called when plugin is loaded."""
        
    @abstractmethod  
    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        
    def register_tools(self, registry: ToolRegistry) -> None:
        """Register tools with the agent's tool registry."""
        
    def register_actions(self, router: ActionRouter) -> None:
        """Register new action types with the action router."""
        
    def register_hooks(self, hooks: HookManager) -> None:
        """Subscribe to lifecycle hooks."""
```

### Hook Events (hooks.py)

| Hook | Trigger | Payload |
|------|---------|---------|
| `pre_action` | Before action execution | `ActionRequest` |
| `post_action` | After action execution | `ActionResult` |
| `pre_inference` | Before LLM call | `messages, context` |
| `post_inference` | After LLM response | `response, tokens` |
| `on_wake` | Wake word detected | `audio_data` |
| `on_sleep` | Assistant goes idle | `session_stats` |
| `ui_update` | UI state change | `component, state` |

### Integration Points

1. **Orchestrator** calls `HookManager.emit('pre_inference', ...)` before LLM
2. **ActionRouter** calls `HookManager.emit('pre_action', ...)` before dispatch
3. **Listener** calls `HookManager.emit('on_wake', ...)` on wake word
4. **PluginManager** scans `Jarvis/plugins/` directory on startup

---

## Feature 2: Desktop Overlay UI

### Purpose
Provide an ambient, non-intrusive, always-on-top widget for quick interactions.

### Architecture

```
Jarvis/ui/overlay.py
├── TransparentOverlay(QWidget)   # Main container
├── AmbientOrb                    # Minimized state indicator
├── QuickCommandBar               # Expandable input field
└── ContextHUD                    # Screen understanding display
```

### Key Properties

| Property | Value | Purpose |
|----------|-------|---------|
| `WindowStaysOnTopHint` | True | Always visible |
| `FramelessWindowHint` | True | No title bar |
| `TranslucentBackground` | True | Transparency support |
| `WA_TransparentForMouseEvents` | Selective | Click-through regions |

### State Machine

```
┌─────────┐  hover   ┌──────────┐  click   ┌──────────┐
│ AMBIENT ├─────────►│ EXPANDED ├─────────►│ FOCUSED  │
│  (orb)  │◄─────────┤  (bar)   │◄─────────┤ (input)  │
└─────────┘  timeout └──────────┘   blur   └──────────┘
     │                                          │
     │              voice trigger               │
     └──────────────────────────────────────────┘
```

### Thread Safety

- UI updates via `Worker.output_ready` signal
- Animation timers on main thread
- Screen capture on background thread with signal callback

---

## Feature 3: Screen Understanding

### Purpose
Capture and analyze screen content for context-aware assistance.

### Architecture

```
Jarvis/core/vision/
├── capture.py       # Fast screen capture (mss)
├── router.py        # Hybrid local/API routing
├── ocr.py           # Local text extraction
└── analyzer.py      # Cloud vision API calls
```

### Hybrid Routing Strategy (VRAM-Aware)

```
┌──────────────────┐
│  Screen Capture  │
│     (mss)        │
└────────┬─────────┘
         │
    ┌────▼────┐
    │ Router  │
    └────┬────┘
         │
    ┌────┴────┐
    │ Analyze │
    │ Request │
    └────┬────┘
         │
  ┌──────┴──────┐
  │ Complexity? │
  └──────┬──────┘
         │
    ┌────┴────┐         ┌────────────┐
    │  LOW    ├────────►│ Local OCR  │ ~500MB VRAM
    └─────────┘         │ (EasyOCR)  │
                        └────────────┘
    ┌─────────┐         ┌────────────┐
    │  HIGH   ├────────►│ Gemini API │ 0 VRAM
    └─────────┘         │ (Vision)   │
                        └────────────┘
```

### Complexity Heuristics

| Condition | Route |
|-----------|-------|
| Text extraction only | Local OCR |
| UI element detection | Local OCR + heuristics |
| Image understanding | Gemini Vision API |
| Chart/graph analysis | Gemini Vision API |
| Multi-modal query | Gemini Vision API |

### New Action Type

```python
ActionType.SCREEN_ANALYZE = "screen_analyze"

# Usage in LLM output:
# [ACTION]screen_analyze: what app is in focus[/ACTION]
# [ACTION]screen_analyze: extract text from selection[/ACTION]
```

---

## Feature 4: Workflow Automation

### Purpose
Record, save, and replay sequences of OS actions (macros).

### Architecture

```
Jarvis/core/workflows/
├── engine.py        # Workflow executor
├── recorder.py      # Action recording
├── actions.py       # Workflow primitives
├── scheduler.py     # Timed/triggered execution
└── templates/       # Pre-built workflows (YAML)
```

### Workflow Definition Schema (YAML)

```yaml
name: "Morning Routine"
description: "Open work apps and arrange windows"
trigger:
  type: time
  value: "09:00"
  days: [mon, tue, wed, thu, fri]
  
steps:
  - action: launch_app
    target: "Outlook"
    wait: 2000
    
  - action: launch_app
    target: "Teams"
    wait: 2000
    
  - action: snap_window
    target: "Outlook"
    position: left
    
  - action: snap_window
    target: "Teams"
    position: right
    
  - action: notification
    message: "Workspace ready!"
```

### Recording API

```python
class WorkflowRecorder:
    def start_recording(self) -> str:
        """Start recording, return session ID."""
        
    def stop_recording(self) -> Workflow:
        """Stop and return recorded workflow."""
        
    def add_checkpoint(self, name: str) -> None:
        """Add named checkpoint for conditional branching."""
```

### Trigger Types

| Type | Description |
|------|-------------|
| `manual` | Voice/text command |
| `time` | Scheduled execution |
| `event` | System event (app launch, file change) |
| `hotkey` | Keyboard shortcut |
| `screen` | Screen content match (via vision) |

---

## Feature 5: Mobile Companion API

### Purpose
Expose local endpoints for remote interaction from mobile devices.

### Architecture

```
Jarvis/api/
├── server.py        # FastAPI application
├── routes.py        # REST endpoints
├── auth.py          # Token authentication
├── sync.py          # State synchronization
└── discovery.py     # mDNS/Bonjour broadcast
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/status` | Assistant status |
| POST | `/api/v1/command` | Send text command |
| GET | `/api/v1/history` | Conversation history |
| POST | `/api/v1/wake` | Trigger wake |
| GET | `/api/v1/notifications` | Pending notifications |
| WS | `/api/v1/stream` | Real-time updates |

### Authentication Flow

```
┌────────┐                      ┌────────┐
│ Mobile │                      │ Jarvis │
└───┬────┘                      └───┬────┘
    │                               │
    │  GET /api/v1/pair?code=XXXX   │
    │──────────────────────────────►│
    │                               │
    │  Display pairing code on PC   │
    │◄──────────────────────────────│
    │                               │
    │  User confirms on PC          │
    │                               │
    │  {"token": "jwt..."}          │
    │◄──────────────────────────────│
    │                               │
    │  All subsequent requests      │
    │  Authorization: Bearer jwt    │
    │──────────────────────────────►│
```

### Thread Integration

- FastAPI runs in separate thread via `uvicorn`
- Commands queued to `Orchestrator` via `queue.Queue`
- Responses sent back via callback or WebSocket

---

## Feature 6: Distributed Compute Agents

### Purpose
Offload heavy computation to other local machines or cloud APIs.

### Architecture

```
Jarvis/core/compute/
├── node.py          # Worker node client
├── dispatcher.py    # Task routing
├── protocol.py      # JSON-RPC over WebSocket
└── offload.py       # Cloud API integration
```

### Node Discovery Protocol

```
┌─────────────────────────────────────────────────────────────┐
│                    Local Network                             │
│                                                             │
│  ┌──────────┐    UDP Broadcast     ┌──────────┐            │
│  │  Master  │◄────────────────────►│  Node 1  │            │
│  │ (Jarvis) │    Port 5757         │ (GPU PC) │            │
│  └────┬─────┘                      └──────────┘            │
│       │                                                     │
│       │         WebSocket           ┌──────────┐            │
│       └────────────────────────────►│  Node 2  │            │
│                 Port 5758           │(Cloud VM)│            │
│                                     └──────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### Task Types

| Type | Local Preference | Cloud Fallback |
|------|------------------|----------------|
| `llm_inference` | Node with VRAM > 8GB | Groq/Gemini API |
| `vision_analyze` | Node with VRAM > 6GB | Gemini Vision |
| `tts_generate` | Any node | Edge TTS (cloud) |
| `stt_transcribe` | Node with Whisper | Groq Whisper |
| `code_execute` | Sandboxed node | None (security) |

### Capability Advertisement

```json
{
  "node_id": "desktop-rtx3080",
  "capabilities": {
    "vram_mb": 10240,
    "ram_mb": 32768,
    "models": ["llama3.1:70b", "whisper-large"],
    "features": ["cuda", "vision"]
  },
  "load": {
    "vram_used_mb": 4096,
    "cpu_percent": 25,
    "queue_depth": 2
  }
}
```

---

## Implementation Order

```
1. Plugin Ecosystem    ████████████████████  Foundation for all others
2. Desktop Overlay     ████████████████      UI for user interaction
3. Screen Understanding████████████████      Enables context awareness
4. Workflow Automation ████████████████      Builds on actions
5. Mobile API          ████████████████      Remote access layer
6. Distributed Compute ████████████████      Performance scaling
```

### Rationale

1. **Plugins first**: All other features can be implemented as plugins, ensuring modularity
2. **Overlay second**: Provides visual feedback for development/testing
3. **Vision third**: Required for advanced workflow triggers
4. **Workflow fourth**: Uses vision and existing action system
5. **Mobile fifth**: Wraps existing functionality
6. **Compute last**: Optimization layer, not critical path

---

## Dependency Matrix

| Package | Version | Feature | VRAM Impact |
|---------|---------|---------|-------------|
| mss | ^9.0 | Screen capture | 0 |
| easyocr | ^1.7 | Local OCR | ~500MB |
| pyautogui | ^0.9 | Workflow recording | 0 |
| pynput | ^1.7 | Input monitoring | 0 |
| pywin32 | ^306 | Windows API | 0 |
| fastapi | ^0.110 | Mobile API | 0 |
| uvicorn | ^0.27 | ASGI server | 0 |
| websockets | ^12.0 | Compute protocol | 0 |
| google-generativeai | ^0.4 | Vision API | 0 |
| pyzeroconf | ^0.131 | mDNS discovery | 0 |

**Total VRAM overhead: ~500MB** (within 4GB constraint)

---

## Configuration Extensions

Add to `Jarvis/.env`:

```bash
# Plugin System
PLUGIN_DIR=plugins
PLUGIN_AUTOLOAD=true

# Overlay UI
OVERLAY_ENABLED=true
OVERLAY_POSITION=bottom-right
OVERLAY_OPACITY=0.9

# Screen Understanding
VISION_PROVIDER=hybrid           # hybrid | local | gemini
VISION_OCR_ENGINE=easyocr        # easyocr | tesseract
GEMINI_VISION_MODEL=gemini-1.5-flash

# Workflow Automation
WORKFLOW_DIR=workflows
WORKFLOW_RECORD_INPUTS=false     # Privacy: don't record keystrokes

# Mobile API
API_ENABLED=true
API_PORT=5757
API_REQUIRE_AUTH=true

# Distributed Compute
COMPUTE_MASTER=true
COMPUTE_DISCOVERY_PORT=5757
COMPUTE_WS_PORT=5758
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Plugin crashes core | Process isolation, exception boundaries |
| VRAM overflow | Dynamic model unloading, API fallback |
| Screen capture privacy | User consent, recording indicators |
| Mobile API security | JWT auth, local network only |
| Workflow infinite loop | Max iterations, timeout guards |

---

## Testing Strategy

1. **Unit Tests**: Each module in isolation
2. **Integration Tests**: Feature combinations
3. **VRAM Profiling**: Monitor with `nvidia-smi`
4. **UI Testing**: Manual overlay interaction
5. **Load Testing**: Concurrent API requests

---

## Approval Checkpoint

This architecture document outlines the upgrade plan. The VS Code track will now proceed with implementation starting with the Plugin Ecosystem.

**Parallel tracks can begin:**
- **Gemini CLI**: Install dependencies listed above
- **Antigravity**: Prepare test scenarios

---

*Document generated by Swara-Core Architect*
