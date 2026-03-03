# API Fallback & Routing Logic - When System Shifts from Local to Cloud

## Overview
The system uses a **3-level cascade** for Speech-to-Text (STT) and handles different task types intelligently.

---

## 1. STT (Speech-to-Text) Routing - The 3-Level Cascade

### Default Flow (Auto Mode)
```
User speaks audio
    ↓
Try Groq (fastest cloud)
    ├─ ✅ Success? Return immediately (~200ms)
    └─ ❌ Fails? → Next step
        ↓
    Try Gemini (robust cloud backup)
        ├─ ✅ Success? Return immediately (~300-500ms)
        └─ ❌ Fails? → Next step
            ↓
        Use Local faster-whisper (~300-800ms)
            ├─ ✅ Returns result (always succeeds)
            └─ No API cost
```

---

## 2. When System SHIFTS to Cloud APIs (From Local)

### Scenario 1: **Groq Quota Available**
**Condition:** `Groq.remaining_seconds > 10` (daily limit not exhausted)

**What happens:**
- ✅ Groq STT is ATTEMPTED FIRST
- LOCAL model is skipped
- Fastest option (~200ms)
- Most accurate (Whisper Large v3 Turbo)

**Code:**
```python
def _should_use_groq(self) -> bool:
    if self._groq is None: return False
    return self._groq.remaining_seconds > 10  # ← KEY CONDITION
```

---

### Scenario 2: **Groq Quota Exhausted** 
**Condition:** `Groq.remaining_seconds <= 10` (daily limit hit)

**What happens:**
- ❌ Groq skipped
- ✅ Gemini tried next (backup cloud)
- LOCAL skipped (cloud preferred if available)
- Uses Gemini 1.5 Flash (~300-500ms)

**Code:**
```python
def _should_use_gemini(self) -> bool:
    if self._gemini is None: return False
    return True  # Always try if available
```

---

### Scenario 3: **Both Cloud APIs Fail**
**Conditions:** 
- Groq failed/unavailable AND
- Gemini failed/unavailable

**What happens:**
- ✅ LOCAL model takes over
- No more cloud API calls
- ~300-800ms latency
- Zero API cost

**Code:**
```python
# After Groq fails
if result.get("error") is None:
    return result
else:
    logger.warning("GroqSTT failed, falling back to next provider")

# After Gemini fails
if result.get("error") is None:
    return result
else:
    logger.warning("GeminiSTT failed, falling back to local")

# Use local
if self._local:
    result = self._local.transcribe_bytes(...)
    return result
```

---

## 3. Text-Based Task Routing (LLM Selection)

### Simple Queries → LOCAL Model (No API Cost)
**Tasks that use local Ollama model:**
- "What is X?" (knowledge questions)
- "Who is Y?" (factual)
- "Define Z" (definitions)
- "When is/was X?" (factual events)
- "How do I X?" (simple how-to)
- Yes/No questions
- Simple reasoning (~2-3 turns)

**Code in orchestrator.py:**
```python
def _should_use_local_model(self, command: str) -> bool:
    if re.search(r"^(what|who|when|where|why|how)\s+", command, re.I):
        return True  # Use local
    # ... more patterns
```

**Latency:** ~2-5 seconds  
**Cost:** $0

---

### Complex Tasks → CLOUD API (Groq/Gemini)
**Tasks that require cloud LLM:**
- Multi-turn conversations (context management)
- Creative writing/poetry
- Code generation
- Complex reasoning (5+ steps)
- Email/document composition
- System-wide planning
- Undefined/ambiguous queries

**Code:**
```python
if self._should_use_local_model(command):
    # Use local Ollama
    result = local_model.query(prompt)
else:
    # Use cloud Groq/Gemini
    result = cloud_llm.query(prompt)
```

**Latency:** ~500ms-2s (depending on Groq/Gemini availability)  
**Cost:** Uses API quota

---

## 4. System Meta-Commands (Always Local, No API)

These NEVER call cloud APIs:
```
llm [model] [prompt]      → Use local Ollama directly
voice [en|hi]             → Configure voice (no API)
stt [groq|gemini|local]   → Change STT provider (no API)
shell [command]           → Run system command (no API)
screenshot                → Take screenshot (no API)
lock                      → Lock system (no API)
time/date                 → Get time (no API)
volume [0-100]            → Change volume (no API)
```

---

## 5. Media & Search (Always Local, No API)

These bypass LLM entirely:
```
open youtube [search]     → Direct browser (no API)
play spotify [song]       → Direct app (no API)
google [query]            → Direct browser search (no API)
open [app]                → Launch app (no API)
```

---

## 6. Summary: Decision Tree

```
┌─ SPEECH INPUT (Audio)
│  ├─ Groq available & quota > 10s? 
│  │  └─ YES → Try Groq (200ms)
│  ├─ Groq failed or quota exhausted?
│  │  └─ YES → Try Gemini (300-500ms)
│  └─ Gemini failed?
│     └─ YES → Use Local (300-800ms)
│
└─ TEXT INPUT (Command/Question)
   ├─ Is system meta-command (llm, voice, stt, shell)?
   │  └─ YES → Handle locally, NO API
   ├─ Is media/search (open youtube, google)?
   │  └─ YES → Handle locally, NO API
   ├─ Is simple query (what/who/when/where)?
   │  └─ YES → Use local model, NO API
   └─ Is complex task (creative, code, multi-turn)?
      └─ YES → Use Groq/Gemini, costs API quota
```

---

## 7. Quota Management

### Groq Free Tier
- **Limit:** 28,800 seconds/day (~8 hours)
- **Usage:** 1 second per second of audio
- **Reset:** Midnight UTC
- **Check:** `groq.remaining_seconds`

### Gemini Free Tier
- **Limit:** 60 requests/minute (rate limited)
- **Limit:** 1,500 requests/day
- **Reset:** Per calendar day
- **Fallback:** Auto-retries if rate limited

### Local Ollama
- **Limit:** Unlimited
- **Cost:** CPU/GPU compute only
- **Speed:** Depends on model size (gemma:2b vs llama3.2:3b)

---

## 8. Example Scenarios

### Scenario A: User says "Hello Jarvis" in Hindi (नमस्ते)
```
1. Audio captured → STT Router
2. Groq quota available? YES
3. Try Groq transcribe → SUCCESS
4. Text: "नमस्ते"
5. Is it command? NO
6. Is it simple greeting? YES
7. Use LOCAL model to respond
8. Result: "नमस्ते! कैसे हो?" (local model response)
Cost: ~0.3s Groq quota (STT only)
```

### Scenario B: User says "Write me a poem about AI"
```
1. Audio captured → STT Router
2. Groq quota = 5,000s (available)
3. Groq transcribe → SUCCESS
4. Text: "Write me a poem about AI"
5. Is simple query? NO (creative task)
6. Use GROQ LLM to generate poem
7. TTS responds with Groq-generated poem
Cost: ~0.5s Groq quota (STT + LLM processing)
```

### Scenario C: Groq quota exhausted, user asks "What is machine learning?"
```
1. Audio captured → STT Router
2. Groq quota = 2s (exhausted)
3. Skip Groq (quota check failed)
4. Try Gemini → SUCCESS
5. Text: "What is machine learning?"
6. Is simple query? YES
7. Use LOCAL model to answer
8. LOCAL responds immediately
Cost: FREE (Gemini for STT only, no LLM)
```

### Scenario D: Network down, no cloud available
```
1. Audio captured → STT Router
2. Try Groq → FAILS (no internet)
3. Try Gemini → FAILS (no internet)
4. Use LOCAL → SUCCESS
5. Text transcribed locally
6. All subsequent processing local
7. System works completely offline
Cost: FREE (all local)
```

---

## 9. Configuration

### Via .env
```env
# Set default STT provider
STT_PROVIDER=auto          # "auto" (try cloud first, then local)
                           # "groq" (cloud only)
                           # "gemini" (cloud backup only)
                           # "local" (offline only)

# API Keys
GROQ_API_KEY=gsk_xxxx      # Required for Groq
GEMINI_API_KEY=AIza_xxxx   # Required for Gemini

# Local model
LOCAL_STT_MODEL=base.en    # faster-whisper size (tiny/small/base/medium)
```

---

## 10. Optimization Tips

To minimize API cost:
1. **Use local for simple queries** (already automatic)
2. **Batch similar requests** (e.g., define 5 terms in one prompt)
3. **Monitor Groq quota** (check daily limit)
4. **Run Ollama 24/7** for fallback (cheap CPU/GPU compute)
5. **Switch to "local" provider** if quota concerns (use offline mode)

---

**Current Effective Setup:**
- ✅ STT: Groq → Gemini → Local (auto fallback)
- ✅ LLM: Local for simple queries, Cloud for complex
- ✅ System commands: Always local
- ✅ Projected savings: 50-60% API reduction vs. full cloud
