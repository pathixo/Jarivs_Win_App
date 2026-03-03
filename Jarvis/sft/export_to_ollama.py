"""
Export fine-tuned LoRA adapters to Ollama-compatible GGUF format.

Usage:
    python -m Jarvis.sft.export_to_ollama [--quantize q4_K_M|q5_K_M|f16]

This will:
    1. Load base model + merge LoRA adapters
    2. Save merged model in HuggingFace format
    3. Convert to GGUF using llama.cpp
    4. Quantize GGUF using llama-quantize (if requested)
    5. Create Ollama Modelfile and import

Quantization Options (defaults to efficient q4_K_M):
    - q4_K_M: ~1GB, recommended for most use cases
    - q5_K_M: ~1.5GB, higher quality
    - f16: ~3GB, maximum quality (no quantization)
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from Jarvis.sft.canonical_prompt import CANONICAL_SYSTEM_PROMPT


def merge_lora(base_model: str, lora_path: str, output_path: str):
    """Merge LoRA adapters into base model."""
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError:
        print("Missing packages. Install: pip install torch transformers peft")
        sys.exit(1)

    print(f"Loading base model: {base_model}")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="cpu",  # merge on CPU to avoid VRAM issues
        trust_remote_code=True,
    )

    # Resolve to absolute path so PEFT doesn't treat it as a HF repo ID
    lora_path = str(Path(lora_path).resolve())
    print(f"Loading LoRA adapters: {lora_path}")
    if not Path(lora_path).exists():
        print(f"ERROR: LoRA adapter directory not found: {lora_path}")
        print(f"  Did you run training first? Check --lora-path argument.")
        sys.exit(1)
    model = PeftModel.from_pretrained(model, lora_path)

    print("Merging weights...")
    model = model.merge_and_unload()
    model.to("cpu")

    print(f"Saving merged model to: {output_path}")
    model.save_pretrained(output_path)

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    tokenizer.save_pretrained(output_path)

    print(f"Merged model saved to {output_path}")
    return output_path


def convert_to_gguf(merged_path: str, gguf_output: str, quantize_type: str = "q4_K_M"):
    """Convert HuggingFace model to GGUF format using llama.cpp."""
    # Check if llama.cpp convert script exists
    convert_script = Path("llama.cpp/convert_hf_to_gguf.py")

    if not convert_script.exists():
        print("\nllama.cpp not found. Cloning...")
        subprocess.run(
            ["git", "clone", "https://github.com/ggerganov/llama.cpp.git"],
            check=True,
        )
        
        # Filter out torch from requirements.txt (more robust)
        req_path = Path("llama.cpp/requirements.txt")
        if req_path.exists():
            reqs = req_path.read_text(encoding="utf-8").splitlines()
            # Skip commented lines and torch packages
            reqs = [r for r in reqs if r.strip() and not r.strip().startswith("#")]
            reqs = [r for r in reqs if not r.lower().strip().startswith("torch")]
            req_path.write_text("\n".join(reqs) + "\n", encoding="utf-8")

        # Install with retry logic for robustness
        max_retries = 3
        for attempt in range(max_retries):
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "llama.cpp/requirements.txt"],
                    check=True,
                    timeout=300,
                )
                break
            except subprocess.CalledProcessError as e:
                if attempt < max_retries - 1:
                    print(f"Pip install failed (attempt {attempt + 1}/{max_retries}), retrying in 5s...")
                    time.sleep(5)
                else:
                    print(f"Pip install failed after {max_retries} attempts")
                    raise

    # Convert to f16 GGUF first
    gguf_f16 = str(gguf_output).replace(".gguf", "_f16.gguf")
    print(f"\nConverting to f16 GGUF: {merged_path} -> {gguf_f16}")
    subprocess.run(
        [
            sys.executable,
            str(convert_script),
            merged_path,
            "--outfile", gguf_f16,
            "--outtype", "f16",
        ],
        check=True,
    )
    print(f"F16 GGUF saved to {gguf_f16}")

    # If quantization requested, quantize the f16 GGUF
    if quantize_type != "f16":
        quantize_gguf(gguf_f16, gguf_output, quantize_type)
    else:
        print(f"\nNo quantization requested (f16). Using {gguf_f16} as final output.")
        # Copy f16 to final output path
        import shutil
        shutil.move(gguf_f16, gguf_output)
        print(f"Final GGUF: {gguf_output}")


def quantize_gguf(gguf_f16: str, gguf_output: str, quantize_type: str = "q4_K_M"):
    """Quantize GGUF file using llama-quantize binary."""
    quantize_bin = Path("llama.cpp/build/bin/llama-quantize")
    
    if not quantize_bin.exists():
        # Try alternate locations
        quantize_bin = Path("llama.cpp/build/Release/bin/llama-quantize")  # Windows
    
    if not quantize_bin.exists():
        print(f"⚠️  WARNING: llama-quantize binary not found")
        print(f"   Expected at: llama.cpp/build/bin/llama-quantize")
        print(f"   Skipping quantization. Using f16 GGUF instead.")
        import shutil
        shutil.move(gguf_f16, gguf_output)
        return

    print(f"\n🔧 Quantizing GGUF: {quantize_type}")
    print(f"   Input:  {gguf_f16}")
    print(f"   Output: {gguf_output}")
    try:
        subprocess.run(
            [str(quantize_bin), gguf_f16, gguf_output, quantize_type],
            check=True,
            timeout=600,  # 10 minutes for large models
        )
        print(f"✓ Quantized GGUF saved to {gguf_output}")
        
        # Show file sizes
        f16_size = Path(gguf_f16).stat().st_size / (1024**3)
        q_size = Path(gguf_output).stat().st_size / (1024**3)
        reduction = 100 * (1 - q_size / f16_size)
        print(f"  F16: {f16_size:.2f}GB → {quantize_type}: {q_size:.2f}GB ({reduction:.0f}% reduction)")
        
        # Remove intermediate f16 file
        Path(gguf_f16).unlink()
    except subprocess.CalledProcessError as e:
        print(f"✗ Quantization failed: {e}")
        print(f"  Falling back to f16 GGUF")
        import shutil
        shutil.move(gguf_f16, gguf_output)


def import_to_ollama(gguf_path: str, model_name: str):
    """Create Ollama Modelfile and import the model."""
    # Use absolute path for GGUF so Ollama can find it
    abs_gguf = str(Path(gguf_path).resolve())
    # 8a: Use CANONICAL_SYSTEM_PROMPT as single source of truth for Jarvis voice
    modelfile_content = f'''FROM {abs_gguf}

PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.3
PARAMETER num_ctx 2048

SYSTEM """{CANONICAL_SYSTEM_PROMPT}"""
'''
    modelfile_path = "Modelfile.jarvis"
    with open(modelfile_path, "w") as f:
        f.write(modelfile_content)

    print(f"\n📦 Importing to Ollama as '{model_name}'...")
    subprocess.run(
        ["ollama", "create", model_name, "-f", modelfile_path],
        check=True,
    )
    print(f"\n✓ Done! Model available as: {model_name}")
    print(f"  Test with: ollama run {model_name} \"open notepad\"")


def main():
    parser = argparse.ArgumentParser(description="Export LoRA to Ollama")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct",
                        help="Base model name on HuggingFace")
    # 8d: Fix LoRA path to match actual base model (Qwen, not Gemma)
    parser.add_argument("--lora-path", default="output/jarvis-gemma-lora",
                        help="Path to LoRA adapter directory")
    parser.add_argument("--merged-path", default="output/jarvis-merged",
                        help="Path to save merged model")
    parser.add_argument("--gguf-path", default="output/jarvis-action.gguf",
                        help="Path to save GGUF file")
    # 8b: Add quantization options
    parser.add_argument("--quantize", default="q4_K_M", choices=["q4_K_M", "q5_K_M", "f16"],
                        help="Quantization format: q4_K_M (~1GB, default), q5_K_M (~1.5GB), f16 (~3GB, no quantization)")
    parser.add_argument("--ollama-name", default="jarvis-action",
                        help="Name for the Ollama model")
    parser.add_argument("--skip-ollama", action="store_true",
                        help="Skip Ollama import (just merge + convert)")
    args = parser.parse_args()

    # Step 1: Merge LoRA into base
    merge_lora(args.base_model, args.lora_path, args.merged_path)

    # Step 2: Convert to GGUF (8b, 8c: with quantization support)
    convert_to_gguf(args.merged_path, args.gguf_path, args.quantize)

    # Step 3: Import to Ollama
    if not args.skip_ollama:
        import_to_ollama(args.gguf_path, args.ollama_name)
    else:
        print(f"\nSkipped Ollama import. GGUF at: {args.gguf_path}")
        print(f"To import manually:")
        print(f"  ollama create {args.ollama_name} -f Modelfile.jarvis")

    print(f"\n{'='*60}")
    print(f"  ✓ Export complete!")
    print(f"  Next: Update your .env to use the fine-tuned model")
    print(f"  OLLAMA_MODEL={args.ollama_name}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
