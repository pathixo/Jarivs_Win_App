# Step 9 — Language Restriction & Gemini API Integration

**Status:** Plan Ready for Implementation  
**Date:** 2026-03-03  
**Priority:** High  
**Estimated Duration:** 6-8 hours  

---

## 🎯 Objective

Transform Jarvis from multi-language support to **Hindi/English only**, integrate **Gemini API** as STT/TTS fallback, and use **local models** for command execution to reduce API quota usage.

---

## 📋 Requirements Breakdown

### Requirement 1: Language Restriction to Hindi & English
**Current State:**
- Language detector designed for multi-language support
- STT router accepts any language code
- TTS supports multiple voice options
- Orchestrator routes to any language

**Target State:**
- Only Hindi (hi) and English (en) accepted
- Other languages explicitly rejected
- API calls only with valid ISO 639-1 codes (en, hi)
- Language commands limited to "hindi"/"english" only

**Rationale:**
- Simplifies maintenance and testing
- Reduces API failures from invalid language codes
- Focuses on Hindi/English which are primary use cases
- Improves reliability and consistency

---

### Requirement 2: Gemini API Integration for STT/TTS
**Current State:**
- Groq Whisper for STT (primary)
- Local Faster-Whisper fallback
- Kokoro/Edge-TTS for TTS
- No Gemini STT option

**Target State:**
- Groq → Gemini → Local fallback chain
- Gemini STT as secondary provider when Groq unavailable
- Smart provider selection based on language
- Gemini API key already in .env: `<YOUR_GEMINI_API_KEY>`

**Benefits:**
- Increased reliability (3-provider fallback)
- Better handling of API rate limits
- Redundancy if one provider fails
- Language-specific routing optimization

---

### Requirement 3: Local Models for Command Execution
**Current State:**
- Local models only used for main LLM
- All command validation via cloud APIs
- No local context building
- High API quota usage

**Target State:**
- Local models for command validation
- Local models for safety checking
- Local models for OCR/image processing
- Reduce cloud API calls by 30-50%

**Use Cases:**
- Command validation: "Is this a safe command?" → Local model
- Shell safety check: Validate before execution → Local model  
- Context building: Extract system info → Local model
- OCR text extraction → Local model (if available)

**Benefits:**
- Faster execution (local = ~50ms vs cloud = ~200-500ms)
- Reduced API quota usage
- Better privacy (no command data sent to cloud)
- Graceful degradation if cloud APIs unavailable

---

### Requirement 4: .env Configuration
**New Settings Needed:**
```bash
# Language Restriction
SUPPORTED_LANGUAGES=en,hi

# Gemini STT
GEMINI_STT_ENABLED=true
GEMINI_STT_VOICE=en-US-Neural2-A,hi-IN-Neural2-A

# Local Model Usage
LOCAL_MODEL_COMMAND_VALIDATION=true
LOCAL_MODEL_SAFETY_CHECK=true
LOCAL_MODEL_OCR_ENABLED=false
```

---

## 🚀 Implementation Plan

### Phase 1: Language Restriction (1-2 hours)

#### 1a. Modify `Jarvis/core/language_detector.py`
```python
# Changes:
- Restrict detect() to return only "hi" or "en"
- Add get_supported_languages() → ["en", "hi"]
- Reject Devanagari that isn't complete Hindi
- Only calculate confidence for these two languages
- Return confidence 0.0 for all other scripts

# Example:
detect("नमस्ते") → {"lang": "hi", "confidence": 0.99}
detect("Hello") → {"lang": "en", "confidence": 0.99}
detect("Bonjour") → {"lang": "unknown", "confidence": 0.0}  # Rejected
```

#### 1b. Update `Jarvis/input/stt_router.py`
```python
# Changes:
- Add _SUPPORTED_LANGUAGES = {"en", "hi", "auto"}
- Validate language before sending to APIs
- Reject language outside supported set
- Add _validate_language(lang) method
- Pass only valid codes to Groq/Gemini

# Example:
transcribe(..., language="hi") → ✅ Sent to API as "hi"
transcribe(..., language="hindi") → ❌ Rejected, logged warning
transcribe(..., language="fr") → ❌ Rejected, not supported
```

#### 1c. Restrict `Jarvis/output/tts.py`
```python
# Changes:
- Restrict voice selection to en/hi variants only
- Map language to TTS voice codes
- Reject non-en/hi voice requests
- Voice mapping:
  - en → "en-GB-SoniaNeural" (Edge TTS)
  - hi → "hi-IN-SwaraNeural" (Edge TTS)
```

#### 1d. Update `Jarvis/core/orchestrator.py`
```python
# Changes:
- Limit language setting commands to "english"/"hindi" only
- Update help text to show only en/hi support
- Reject language switch commands for other languages
- Log warnings for unsupported language attempts
```

---

### Phase 2: Gemini API Integration (2-3 hours)

#### 2a. Extend `Jarvis/input/stt_router.py` - Add Gemini STT
```python
# New class: GeminiSTT
class GeminiSTT:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._model = "gemini-2.0-flash"
        
    def transcribe_bytes(self, audio_bytes, language="auto"):
        """Transcribe using Gemini audio API"""
        # Upload audio to Gemini
        # Call with prompt: "Transcribe this audio"
        # Extract text from response
        # Return same format as GroqSTT

# Integrate into STTRouter.transcribe():
# 1. Try Groq (fastest, most accurate)
# 2. If Groq fails with 400 or rate limit → Try Gemini
# 3. If Gemini fails → Fall back to local Whisper
```

#### 2b. Update `.env` with Gemini Settings
```bash
GEMINI_STT_ENABLED=true
GEMINI_MODEL=gemini-2.0-flash
```

#### 2c. Smart Provider Selection in `stt_router.py`
```python
# Detect current language from context
# Route intelligently:
#   Hindi audio → Groq (has Hindi support) 
#              → Gemini (fallback)
#              → Local Whisper
#   English audio → Same chain
# Add provider health check before using
```

#### 2d. Update `Jarvis/config.py`
```python
# New config variables:
GEMINI_STT_ENABLED = os.getenv("GEMINI_STT_ENABLED", "true").lower() == "true"
GEMINI_STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-2.0-flash")
STT_FALLBACK_CHAIN = ["groq", "gemini", "local"]  # Provider order
```

---

### Phase 3: Local Models for Command Execution (2-3 hours)

#### 3a. Create `Jarvis/core/local_model_router.py` (NEW)
```python
# New file
class LocalModelRouter:
    """Route tasks to local Ollama models"""
    
    TASK_ROUTES = {
        "command_validation": "gemma:2b",  # Fast model
        "shell_safety": "llama3.2:3b",     # Logic model
        "ocr_extract": "local_ocr",        # Tesseract/PaddleOCR
        "image_description": "none",       # Not available yet
    }
    
    def validate_command(self, cmd: str) -> tuple[bool, str]:
        """Is this a safe command?"""
        # Use local model to validate
        # Return (is_safe, reason)
    
    def extract_app_name(self, text: str) -> str:
        """Extract app name from complex query"""
        # Use local model for NLU
        # Return app name
```

#### 3b. Update `Jarvis/core/orchestrator.py`
```python
# Changes:
- Import LocalModelRouter
- Before LLM processing complex commands, try local model
- Use local model for: command validation, app name extraction
- Example:
  command = "can you open notepad"
  app_name = local_router.extract_app_name(command)  # "notepad"
  is_safe = local_router.validate_command("open notepad")  # True
```

#### 3c. Update `Jarvis/core/system/action_router.py`
```python
# Changes:
- Before executing shell commands, validate locally
- Use local model to check: Is this safe?
- Complement cloud safety checks
- Catch edge cases cloud might miss
```

#### 3d. Update `Jarvis/core/tools.py`
```python
# Changes:
- Use local models for context building
- Extract system info locally (no cloud call needed)
- Build command suggestions using local models
- Cache results to avoid repeated calls
```

---

## 📊 Task Breakdown

| Task | Component | Priority | Time |
|------|-----------|----------|------|
| 1a | language_detector.py | 🔴 HIGH | 30min |
| 1b | stt_router.py validation | 🔴 HIGH | 30min |
| 1c | tts.py restriction | 🔴 HIGH | 30min |
| 1d | orchestrator.py routing | 🔴 HIGH | 30min |
| 2a | GeminiSTT class | 🔴 HIGH | 60min |
| 2b | .env update | 🔴 HIGH | 10min |
| 2c | Provider selection | 🔴 HIGH | 30min |
| 2d | config.py | 🔴 HIGH | 20min |
| 3a | local_model_router.py | 🟡 MEDIUM | 90min |
| 3b | orchestrator.py delegation | 🟡 MEDIUM | 60min |
| 3c | action_router.py safety | 🟡 MEDIUM | 45min |
| 3d | tools.py enhancement | 🟡 MEDIUM | 45min |
| **Total** | - | - | **8 hours** |

---

## ✅ Success Criteria

### Language Restriction
- ✅ Only Hindi (hi) and English (en) language codes accepted
- ✅ Other languages explicitly rejected with clear error message
- ✅ Language detector returns only {"lang": "en"/"hi", "confidence": float}
- ✅ API calls validated before sending (no invalid codes to cloud)

### Gemini Integration
- ✅ Gemini STT works as backup when Groq unavailable
- ✅ Fallback chain: Groq → Gemini → Local Whisper
- ✅ Language-aware provider selection working
- ✅ Configuration via .env working

### Local Model Execution
- ✅ Command validation uses local model first
- ✅ 30-50% reduction in cloud API calls
- ✅ Local safety checks catch edge cases
- ✅ Performance improved: ~50ms local vs ~200-500ms cloud

### Overall Quality
- ✅ 100% backward compatible
- ✅ No breaking changes
- ✅ Clean, documented code
- ✅ Comprehensive tests written
- ✅ Production ready

---

## 🔄 Execution Flow

```
User Speaks Hindi
    ↓
[Language Detection] → "hi" (restricted check)
    ↓
[STT Provider Selection] → Try Groq with lang="hi"
    ↓
If Groq fails/unavailable → Try Gemini with lang="hi"
    ↓
If Gemini fails → Try Local Whisper
    ↓
[Local Model Validation] → Is this a safe command?
    ↓
[Command Extraction] → Local model extracts app/action
    ↓
[Execute] → Run action or escalate to LLM
```

---

## 📝 Configuration Examples

### .env
```bash
# Language Restriction
SUPPORTED_LANGUAGES=en,hi

# Gemini Integration
GEMINI_STT_ENABLED=true
GEMINI_MODEL=gemini-2.0-flash

# Local Model Routes
LOCAL_MODEL_COMMAND_VALIDATION=true
LOCAL_MODEL_SAFETY_CHECK=true
LOCAL_MODEL_OCR_ENABLED=false

# STT Provider Chain
STT_PRIMARY=groq
STT_FALLBACK=gemini,local
```

### Usage
```bash
# ✅ Works
User: "नोटपैड खोलो" (Hindi)
→ Detected as "hi"
→ STT processes as Hindi
→ Outputs: "नोटपैड खोलो"
→ Local model: safe ✅
→ Executes: Open Notepad

# ✅ Works
User: "Can you open notepad?"
→ Detected as "en"
→ STT processes as English
→ Outputs: "Can you open notepad"
→ Local model extracts: app="notepad"
→ Executes: Open Notepad

# ❌ Rejected
User: "Ouvrez le bloc-notes" (French)
→ Detected as "unknown" (not en/hi)
→ Rejected: "Sorry, I only support Hindi and English"
```

---

## 🛠️ Tools & Dependencies

### Existing
- ✅ Groq Whisper API (already integrated)
- ✅ Local Faster-Whisper (already integrated)
- ✅ Edge-TTS (already integrated)
- ✅ Kokoro ONNX (already integrated)
- ✅ Ollama local models (already integrated)
- ✅ Gemini API key (in .env)

### No New Dependencies Needed
- Using existing Gemini SDK via `google-generativeai` (if installed)
- Using existing Ollama for local models
- No additional libraries required

---

## ⚠️ Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Language restriction breaks use cases | Medium | Confirm en/hi sufficient first |
| Gemini API not supported for audio | Medium | Fall back to local whisper |
| Local model slowness | Low | Use fast model (gemma:2b), cache results |
| Breaking existing language commands | Medium | Extensive testing before deploy |
| API quota explosion | Low | Local models reduce quota usage |

---

## 🚀 Deployment Strategy

### Stage 1: Language Restriction (Low Risk)
- Deploy language_detector.py changes
- Deploy stt_router validation
- Monitor for rejected language attempts
- Gradual rollout to users

### Stage 2: Gemini Fallback (Medium Risk)
- Deploy GeminiSTT in parallel to Groq
- Only activate on Groq failures
- Monitor Gemini quality and latency
- Gradual increase in Gemini usage

### Stage 3: Local Models (Low Risk)
- Optional optimization
- Can disable if issues arise
- Purely local (no breaking changes)
- Gradual rollout

---

## 📊 Expected Impact

### Performance
- **STT latency:** +50-100ms (Gemini fallback, only when Groq unavailable)
- **Local validation:** -150ms (local model instead of cloud call)
- **Overall:** Neutral to slightly positive

### API Quota
- **STT calls:** -5% (some Groq → Gemini usage)
- **Cloud calls:** -30-50% (local model validation)
- **Overall quota reduction:** -25-35%

### Reliability
- **STT success rate:** +2-3% (Gemini fallback)
- **Command execution:** +5-10% (local validation catches edge cases)
- **Overall availability:** +3-5%

---

## 📚 Documentation

Will create:
1. `LANGUAGE_RESTRICTION_GUIDE.md` — User guide
2. `GEMINI_INTEGRATION_GUIDE.md` — Integration details
3. `LOCAL_MODEL_EXECUTION_GUIDE.md` — Implementation guide
4. `STEP_9_IMPLEMENTATION.md` — Technical details

---

## ✨ Next Steps

1. **Review & Approve** this plan
2. **Start Sprint 1:** Language Restriction (1-2 hours)
3. **Start Sprint 2:** Gemini Integration (2-3 hours)
4. **Start Sprint 3:** Local Model Routing (2-3 hours)
5. **Testing & Verification** (1-2 hours)
6. **Deploy to Production**

---

**Plan Status:** ✅ Ready for Implementation  
**Confidence Level:** High (95%)  
**Ready to Start:** YES  
**Estimated Completion:** 8 hours from now

