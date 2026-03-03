"""
QLoRA Fine-Tuning Script — Small LM for Structured Action Outputs
====================================================================
Fine-tunes a small language model with QLoRA to reliably produce
[ACTION] and [SHELL] tags matching Jarvis's runtime contract.

Requirements:
    pip install transformers trl peft bitsandbytes datasets accelerate

Usage:
    python -m Jarvis.sft.train_qlora --data sft/train_chat.jsonl --model Qwen/Qwen2.5-1.5B
    python -m Jarvis.sft.train_qlora --data sft/train_chat.jsonl --model google/gemma-2b
    python -m Jarvis.sft.train_qlora --data sft/train_chat.jsonl --max-length 512 --packing

Notes:
    - Requires a GPU with >= 4GB VRAM (QLoRA 4-bit)
    - Trains LoRA adapters only (~10-50MB), not the full model
    - Output adapters saved to ./output/jarvis-qwen-lora/
    - Default batch_size=1 for 4GB GPUs; increase if you have more VRAM
    - --packing concatenates short sequences for GPU efficiency; most Jarvis
      examples are <200 tokens so packing can significantly improve throughput,
      but it changes loss dynamics (cross-example attention masking) — test
      carefully before using in production training runs.
"""

import argparse
import json
import logging
import os
import sys

logger = logging.getLogger("jarvis.train_qlora")


def check_dependencies():
    """Verify required packages are installed."""
    missing = []
    for pkg in ["transformers", "trl", "peft", "bitsandbytes", "datasets", "accelerate"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print(f"Install with: pip install {' '.join(missing)}")
        sys.exit(1)


def load_chat_dataset(path: str):
    """Load chat-format JSONL into a HuggingFace Dataset."""
    from datasets import Dataset

    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    return Dataset.from_list(examples)


def check_sequence_lengths(dataset, tokenizer, max_length: int) -> list[str]:
    """
    Tokenize every example and warn about any that exceed *max_length*.

    The dataset must already have a ``"text"`` column (post format_messages map)
    and an ``"id"`` column (preserved from the source JSONL).

    Returns:
        List of IDs whose token count exceeds max_length.
    """
    truncated_ids: list[str] = []

    logging.basicConfig(format="%(levelname)s: %(message)s")

    for i, example in enumerate(dataset):
        text = example.get("text", "")
        example_id = example.get("id") or f"idx_{i}"

        # Tokenize without truncation so we see the true length.
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        n_tokens = len(token_ids)

        if n_tokens > max_length:
            truncated_ids.append(example_id)
            logger.warning(
                "example '%s' will be truncated (%d tokens > max_length=%d)",
                example_id, n_tokens, max_length,
            )

    total = len(dataset)
    n_trunc = len(truncated_ids)
    if n_trunc:
        print(
            f"\n  [WARN] Sequence length check: {n_trunc}/{total} examples exceed "
            f"max_length={max_length} and will be truncated during training."
        )
        print(f"         Truncated IDs: {truncated_ids}\n")
    else:
        print(
            f"\n  [OK]   Sequence length check: all {total} examples fit within "
            f"max_length={max_length}.\n"
        )

    return truncated_ids


def train(args):
    """Run QLoRA fine-tuning."""
    check_dependencies()

    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        EarlyStoppingCallback,
    )
    from peft import LoraConfig, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer, DataCollatorForCompletionOnlyLM

    print(f"\n{'='*60}")
    print(f"  Jarvis SFT — QLoRA Fine-Tuning")
    print(f"  Model:      {args.model}")
    print(f"  Data:       {args.data}")
    print(f"  Output:     {args.output_dir}")
    print(f"  Epochs:     {args.epochs}")
    print(f"  LR:         {args.lr}")
    print(f"  LoRA r:     {args.lora_r}")
    print(f"  Max length: {args.max_length}")
    print(f"  Packing:    {args.packing}"
          + (" (WARNING: changes loss dynamics -- verify eval metrics)" if args.packing else ""))
    if args.smoke_test:
        print(f"  MODE:       SMOKE TEST (Dry-run)")
    print(f"{'='*60}\n")

    # 4-bit quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # Load model
    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Prepare for QLoRA
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    # LoRA config — target attention + MLP layers
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    # Load dataset
    print("Loading dataset...")
    dataset = load_chat_dataset(args.data)
    print(f"  {len(dataset)} training examples loaded")

    # Format messages for training using tokenizer's chat template if available
    def format_messages(example):
        """Convert chat messages to a single training string using ChatML format."""
        messages = example["messages"]
        # Try to use the tokenizer's built-in chat template
        if hasattr(tokenizer, 'apply_chat_template'):
            try:
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
                return {"text": text, "id": example.get("id", "")}
            except Exception:
                pass
        # Fallback: ChatML format (Qwen, many others)
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        return {"text": "\n".join(parts), "id": example.get("id", "")}

    dataset = dataset.map(format_messages)

    # Length-check pass: warn about examples that will be truncated
    print("Checking sequence lengths...")
    def check_sequence_lengths_internal(dataset, tokenizer, max_length: int) -> list[str]:
        truncated_ids: list[str] = []
        for i, example in enumerate(dataset):
            text = example.get("text", "")
            example_id = example.get("id") or f"idx_{i}"
            token_ids = tokenizer.encode(text, add_special_tokens=False)
            n_tokens = len(token_ids)
            if n_tokens > max_length:
                truncated_ids.append(example_id)
                logger.warning("example '%s' will be truncated (%d tokens > max_length=%d)", 
                               example_id, n_tokens, max_length)
        if truncated_ids:
            print(f"  [WARN] {len(truncated_ids)}/{len(dataset)} examples exceed max_length={max_length}")
        else:
            print(f"  [OK] All {len(dataset)} examples fit within max_length={max_length}")
        return truncated_ids

    check_sequence_lengths_internal(dataset, tokenizer, args.max_length)

    # Split into train/val
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset = split["train"]
    eval_dataset = split["test"]
    print(f"  Train: {len(train_dataset)}, Val: {len(eval_dataset)}")

    # SFT config
    use_bf16 = torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False
    
    # Base configuration
    sft_kwargs = {
        "output_dir": args.output_dir,
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": args.batch_size,
        "gradient_accumulation_steps": args.grad_accum,
        "gradient_checkpointing": True,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "learning_rate": args.lr,
        "weight_decay": 0.01,
        "warmup_ratio": 0.1,
        "logging_steps": 10,
        "eval_strategy": "steps",
        "eval_steps": 50,
        "save_strategy": "steps",
        "save_steps": 100,
        "save_total_limit": 3,
        "bf16": use_bf16,
        "fp16": not use_bf16 if torch.cuda.is_available() else False,
        "optim": "paged_adamw_8bit",
        "lr_scheduler_type": "cosine",
        "report_to": "none",
        "logging_dir": os.path.join(args.output_dir, "runs"),
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "max_grad_norm": 0.3,
        "max_seq_length": args.max_length,
        "packing": args.packing,
    }

    # Smoke test overrides
    if args.smoke_test:
        sft_kwargs.update({
            "max_steps": 5,
            "eval_steps": 2,
            "save_steps": 2,
            "logging_steps": 1,
        })

    sft_config = SFTConfig(**sft_kwargs)

    # Prepare response template for loss computation (ChatML format)
    # Loss will be computed only on assistant tokens, not on system/user turns
    response_template = "<|im_start|>assistant\n"
    response_template_ids = tokenizer.encode(
        response_template, add_special_tokens=False
    )
    
    # Create data collator that masks out non-assistant tokens from loss
    data_collator = DataCollatorForCompletionOnlyLM(
        response_template=response_template_ids,
        tokenizer=tokenizer,
    )

    print(f"Response template: {response_template!r}")
    print(f"Response token IDs: {response_template_ids}")
    print("Loss will be computed only on assistant tokens (not system/user)\n")

    # Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=sft_config,
        processing_class=tokenizer,
        peft_config=lora_config,
        data_collator=data_collator,
    )
    
    # Add early stopping
    trainer.add_callback(EarlyStoppingCallback(early_stopping_patience=3))

    # Train
    print("\nStarting training...")
    trainer.train()

    # Save
    print(f"\nSaving LoRA adapters to {args.output_dir}")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    print("\nTraining complete!")
    print(f"  LoRA adapters: {args.output_dir}")
    print(f"  To use: load base model + merge adapters with PEFT")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QLoRA fine-tune Gemma 2B for Jarvis")
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct",
                        help="Base model name or path")
    parser.add_argument("--data", required=True,
                        help="Chat-format JSONL training data")
    parser.add_argument("--output-dir", default="output/jarvis-gemma-lora",
                        help="Where to save LoRA adapters")
    parser.add_argument("--epochs", type=int, default=3,
                        help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=1,
                        help="Per-device batch size (1 for 4GB VRAM)")
    parser.add_argument("--grad-accum", type=int, default=4,
                        help="Gradient accumulation steps (effective batch = batch_size * grad_accum)")
    parser.add_argument("--lr", type=float, default=2e-4,
                        help="Learning rate")
    parser.add_argument("--lora-r", type=int, default=16,
                        help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32,
                        help="LoRA alpha")
    parser.add_argument("--max-length", type=int, default=1024,
                        help="Maximum token sequence length; examples longer than this "
                             "will be truncated. A pre-training length check logs all "
                             "affected example IDs. (default: 1024)")
    parser.add_argument("--packing", action="store_true",
                        help="Enable sequence packing in SFTConfig for short-sequence "
                             "efficiency (most Jarvis examples are <200 tokens). "
                             "WARNING: changes loss dynamics -- validate eval metrics when enabled.")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Run a quick dry-run with few steps")
    args = parser.parse_args()

    train(args)
