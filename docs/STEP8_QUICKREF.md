# Step 8: Quick Reference Guide

## What Was Fixed

### 8a ✅ CANONICAL_SYSTEM_PROMPT Import
- Already correct (line 25 imports it, line 175-182 uses it)
- Ensures Jarvis personality is consistent across training and inference

### 8b ✅ Add --quantize Flag  
Default: **q4_K_M** (~1GB, recommended)

```bash
python -m Jarvis.sft.export_to_ollama                    # q4_K_M (1GB)
python -m Jarvis.sft.export_to_ollama --quantize q5_K_M  # q5_K_M (1.5GB)
python -m Jarvis.sft.export_to_ollama --quantize f16     # f16 (3GB)
```

### 8c ✅ Use llama.cpp quantize Binary
- Automatically compresses GGUF after conversion
- F16 (3GB) → q4_K_M (1GB) with 67% reduction
- Graceful fallback if binary not found

### 8d ✅ Fix LoRA Default Path
- Changed from `output/jarvis-gemma-lora` → `output/jarvis-qwen-lora`
- Matches the base model (Qwen/Qwen2.5-1.5B-Instruct)

### 8e ✅ Robust Requirements.txt Filtering
- Skips commented lines (#) and empty lines
- Removes torch packages (any case variation)
- 3-retry logic with 5s backoff on pip install failure

---

## Common Use Cases

### Development (Small & Fast)
```bash
python -m Jarvis.sft.export_to_ollama --quantize q4_K_M
# Result: ~1GB GGUF, fast inference
```

### Production (High Quality)
```bash
python -m Jarvis.sft.export_to_ollama --quantize q5_K_M
# Result: ~1.5GB GGUF, better quality
```

### Maximum Quality (Reference)
```bash
python -m Jarvis.sft.export_to_ollama --quantize f16
# Result: ~3GB GGUF, maximum quality (no quantization)
```

### Custom Paths
```bash
python -m Jarvis.sft.export_to_ollama \
  --base-model Qwen/Qwen2.5-1.5B-Instruct \
  --lora-path ./my-lora \
  --quantize q4_K_M \
  --ollama-name my-jarvis
```

---

## Output Files

```
output/
├── jarvis-merged/          # Merged HF model
├── jarvis-action.gguf      # Final GGUF (quantized)
└── Modelfile.jarvis        # Ollama model definition
```

---

## Troubleshooting

### Q: "llama-quantize binary not found"
**A:** Quantize binary needs to be built from llama.cpp
```bash
# Won't block - falls back to f16 GGUF automatically
```

### Q: "Model path mismatch error"
**A:** Verify LoRA matches base model
```bash
# Check LoRA in output/ matches Qwen
ls output/jarvis-qwen-lora/
```

### Q: Pip install fails
**A:** Automatic retry with backoff (3 attempts, 5s between)
- Check internet connection
- Try manually: `pip install -r llama.cpp/requirements.txt`

### Q: GGUF file too large
**A:** Use smaller quantization
```bash
python -m Jarvis.sft.export_to_ollama --quantize q4_K_M
# 67% smaller than f16
```

---

## File Changes Summary

**File:** `Jarvis/sft/export_to_ollama.py`  
**Changes:** 5 major improvements across ~80 lines

| Line | Change | Impact |
|------|--------|--------|
| 5, 14-17 | Updated docstring | Documents quantization options |
| 23 | Added `import time` | For retry backoff |
| 63, 118-125 | Updated `convert_to_gguf()` signature | Accepts quantize_type parameter |
| 75-82 | Improved torch filtering | More robust (skip comments, empty lines) |
| 84-100 | Added retry logic | 3 retries with 5s backoff |
| 128-167 | Added `quantize_gguf()` function | New quantization step |
| 174 | Added comment "8a" | Marks CANONICAL_SYSTEM_PROMPT usage |
| 201 | Added comment "8d" | Marks LoRA path fix |
| 202 | Fixed LoRA default | jarvis-gemma-lora → jarvis-qwen-lora |
| 209-210 | Added --quantize argument | With choices validation |
| 221 | Updated function call | Passes quantize arg to convert_to_gguf() |

---

## Verification Checklist

- [x] CANONICAL_SYSTEM_PROMPT imported and used (line 25, 175-182)
- [x] --quantize argument added with 3 options (line 209-210)
- [x] quantize_gguf() function implemented (lines 128-167)
- [x] Default LoRA path fixed (line 202)
- [x] Torch filtering improved (lines 75-82)
- [x] Pip install retry logic added (lines 84-100)
- [x] File size reduction working (67% with q4_K_M)
- [x] Backward compatible (all changes optional/default)

---

**Status:** ✅ Step 8 Complete  
**Ready for:** Immediate production use
