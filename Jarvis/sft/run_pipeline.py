"""
SFT Pipeline Runner — Orchestration & Dataset Versioning
=========================================================
Automates the full Jarvis fine-tuning pipeline:
  1. Validate seed data
  2. Generate expanded dataset
  3. Convert to chat format
  4. Train QLoRA adapters
  5. Evaluate model performance
  6. Export to Ollama

Includes dataset versioning with SHA-256 hashing and manifest generation.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Project root relative to this script
ROOT_DIR = Path(__file__).parent.parent.parent
SFT_DIR = ROOT_DIR / "Jarvis" / "sft"
MANIFEST_PATH = SFT_DIR / "manifest.json"

def get_file_hash(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def update_manifest(filepath: str):
    """Update manifest.json with file hash and timestamp."""
    rel_path = os.path.relpath(filepath, ROOT_DIR)
    file_hash = get_file_hash(filepath)
    
    manifest = {}
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    if "files" not in manifest:
        manifest["files"] = {}
    
    manifest["files"][rel_path] = {
        "hash": file_hash,
        "updated_at": datetime.now().isoformat(),
        "size_bytes": os.path.getsize(filepath)
    }
    manifest["last_run"] = datetime.now().isoformat()

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"  [Manifest] Updated {rel_path} | {file_hash[:8]}")

def run_step(name: str, command: list[str], env: dict = None):
    """Run a shell command and check exit code."""
    print(f"\n>>> Step: {name}")
    print(f"    Command: {' '.join(command)}")
    
    t0 = time.time()
    result = subprocess.run(command, cwd=ROOT_DIR, env=env)
    elapsed = time.time() - t0
    
    if result.returncode != 0:
        print(f"\n!!! Step '{name}' failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    
    print(f"--- Step '{name}' complete (%.2fs)" % elapsed)

def main():
    parser = argparse.ArgumentParser(description="Jarvis SFT Pipeline Runner")
    parser.add_argument("--count", type=int, default=500, help="Target example count for generation")
    parser.add_argument("--dry-run", action="store_true", help="Validate + Generate + Smoke-test only")
    parser.add_argument("--skip-train", action="store_true", help="Skip training step")
    args = parser.parse_args()

    # Define paths
    seed_jsonl = SFT_DIR / "seed_dataset.jsonl"
    train_jsonl = SFT_DIR / "train.jsonl"
    chat_jsonl = SFT_DIR / "train_chat.jsonl"

    # Step 1: Validate Seed
    run_step("Schema Validation", [
        sys.executable, "-m", "Jarvis.sft.schema", "--validate", str(seed_jsonl)
    ])

    # Step 2: Generate Dataset
    run_step("Dataset Generation", [
        sys.executable, "-m", "Jarvis.sft.generate_dataset", "--out", str(train_jsonl), "--count", str(args.count)
    ])
    update_manifest(str(train_jsonl))

    # Step 3: Convert to Chat
    run_step("Chat Format Conversion", [
        sys.executable, "-m", "Jarvis.sft.convert_to_chat", "--input", str(train_jsonl), "--output", str(chat_jsonl)
    ])
    update_manifest(str(chat_jsonl))

    # Step 4: Training
    if not args.skip_train:
        train_cmd = [sys.executable, "-m", "Jarvis.sft.train_qlora", "--data", str(chat_jsonl)]
        if args.dry_run:
            train_cmd.append("--smoke-test")
        
        run_step("QLoRA Training", train_cmd)

    # Step 5 & 6: Eval and Export (Skip on dry-run)
    if not args.dry_run and not args.skip_train:
        # Step 5: Eval
        run_step("Model Evaluation", [
            sys.executable, "-m", "Jarvis.sft.eval_structured", "--data", str(train_jsonl)
        ])

        # Step 6: Export
        run_step("Export to Ollama", [
            sys.executable, "-m", "Jarvis.sft.export_to_ollama",
            "--lora-path", "output/jarvis-gemma-lora",
        ])

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Manifest: {MANIFEST_PATH}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
