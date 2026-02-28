"""
QLoRA Fine-Tuning Script — Gemma 2B for Structured Action Outputs
====================================================================
Fine-tunes google/gemma-2b (or gemma-2-2b) with QLoRA to reliably
produce [ACTION] and [SHELL] tags matching Jarvis's runtime contract.

Requirements:
    pip install transformers trl peft bitsandbytes datasets accelerate

Usage:
    python -m Jarvis.sft.train_qlora --data sft/train_chat.jsonl --model google/gemma-2b
    python -m Jarvis.sft.train_qlora --data sft/train_chat.jsonl --model google/gemma-2-2b-it

Notes:
    - Requires a GPU with >= 8GB VRAM (QLoRA 4-bit)
    - Trains LoRA adapters only (~10-50MB), not the full model
    - Output adapters saved to ./output/jarvis-gemma-lora/
"""

import argparse
import json
import os
import sys


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


def train(args):
    """Run QLoRA fine-tuning."""
    check_dependencies()

    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer

    print(f"\n{'='*60}")
    print(f"  Jarvis SFT — QLoRA Fine-Tuning")
    print(f"  Model:   {args.model}")
    print(f"  Data:    {args.data}")
    print(f"  Output:  {args.output_dir}")
    print(f"  Epochs:  {args.epochs}")
    print(f"  LR:      {args.lr}")
    print(f"  LoRA r:  {args.lora_r}")
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
        device_map="auto",
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Prepare for QLoRA
    model = prepare_model_for_kbit_training(model)

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

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load dataset
    print("Loading dataset...")
    dataset = load_chat_dataset(args.data)
    print(f"  {len(dataset)} training examples loaded")

    # Format messages for training
    def format_messages(example):
        """Convert chat messages to a single training string."""
        messages = example["messages"]
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"<start_of_turn>system\n{content}<end_of_turn>")
            elif role == "user":
                parts.append(f"<start_of_turn>user\n{content}<end_of_turn>")
            elif role == "assistant":
                parts.append(f"<start_of_turn>model\n{content}<end_of_turn>")
        return {"text": "\n".join(parts)}

    dataset = dataset.map(format_messages)

    # Split into train/val
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset = split["train"]
    eval_dataset = split["test"]
    print(f"  Train: {len(train_dataset)}, Val: {len(eval_dataset)}")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        weight_decay=0.01,
        warmup_ratio=0.1,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        bf16=torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False,
        fp16=not torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False,
        optim="paged_adamw_8bit",
        lr_scheduler_type="cosine",
        report_to="none",
        max_grad_norm=0.3,
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
        tokenizer=tokenizer,
        max_seq_length=512,
    )

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
    parser.add_argument("--model", default="google/gemma-2b",
                        help="Base model name or path")
    parser.add_argument("--data", required=True,
                        help="Chat-format JSONL training data")
    parser.add_argument("--output-dir", default="output/jarvis-gemma-lora",
                        help="Where to save LoRA adapters")
    parser.add_argument("--epochs", type=int, default=3,
                        help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=4,
                        help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=4,
                        help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-4,
                        help="Learning rate")
    parser.add_argument("--lora-r", type=int, default=16,
                        help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32,
                        help="LoRA alpha")
    args = parser.parse_args()

    train(args)
