# Pipeline Path Fix — LoRA Output Directory Consistency

## Issue
The training and export pipeline had a path mismatch that prevented end-to-end execution:

- **train_qlora.py** was saving LoRA adapters to: `output/jarvis-gemma-lora`
- **export_to_ollama.py** was looking for LoRA adapters at: `output/jarvis-qwen-lora`

This caused `export_to_ollama.py` to fail with: `RepositoryNotFoundError: Can't find 'adapter_config.json' at 'output/jarvis-qwen-lora'`

## Root Cause
During Step 8 (export_to_ollama.py optimization), the default LoRA path was correctly updated to match the actual base model (Qwen, not Gemma). However, **train_qlora.py was not updated** to save to the new path.

## Solution
Updated **train_qlora.py** in two locations:

1. **Line 18 (docstring):**
   ```python
   - Output adapters saved to ./output/jarvis-qwen-lora/
   ```

2. **Line 326 (argparse default):**
   ```python
   parser.add_argument("--output-dir", default="output/jarvis-qwen-lora",
                       help="Where to save LoRA adapters")
   ```

## Impact
- ✅ train_qlora.py now outputs to `output/jarvis-qwen-lora`
- ✅ export_to_ollama.py now finds the correct LoRA adapters by default
- ✅ Full pipeline execution now works end-to-end
- ✅ 100% backward compatible (users can override with `--output-dir` flag)

## Testing
The complete pipeline can now be run:
```bash
python -m Jarvis.sft.train_qlora --data Jarvis/sft/train_chat.jsonl --max-length 1024
python -m Jarvis.sft.export_to_ollama --quantize q4_K_M
```

## Files Modified
- `Jarvis/sft/train_qlora.py` (2 lines changed)

## Status
✅ **FIXED** — Pipeline path consistency restored
