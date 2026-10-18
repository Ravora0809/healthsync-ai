"""LoRA/QLoRA supervised fine-tuning for HEALTHSYNC-AI's evidence-linked extractor.
Start with synthetic examples, then replace them with a sufficiently sized, reviewed dataset.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("QWEN_BASE_MODEL_ID", "Qwen/Qwen3-4B"))
    parser.add_argument("--train", default="ml_training/data/train.jsonl")
    parser.add_argument("--validation", default="ml_training/data/validation.jsonl")
    parser.add_argument("--output", default="ml_training/output/healthsync-qwen3-extractor")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--allow-small-dataset", action="store_true", help="For a smoke test only; do not report such a model as a research result.")
    args = parser.parse_args()

    train_path, val_path = Path(args.train), Path(args.validation)
    if not train_path.is_file() or not val_path.is_file():
        raise SystemExit(
            "Training data not found. Copy train.example.jsonl/validation.example.jsonl to the expected filenames, "
            "then expand and review the labeled dataset before training."
        )
    if not torch.cuda.is_available():
        raise SystemExit("This starter QLoRA script expects a CUDA GPU (e.g. Google Colab T4/A100). Use Colab or adapt the precision/quantization settings for your hardware.")

    from transformers import BitsAndBytesConfig
    from peft import prepare_model_for_kbit_training

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=quantization, device_map="auto", torch_dtype=compute_dtype,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    dataset = load_dataset("json", data_files={"train": str(train_path), "validation": str(val_path)})
    train_count, val_count = len(dataset["train"]), len(dataset["validation"])
    if not args.allow_small_dataset and (train_count < 50 or val_count < 10):
        raise SystemExit(
            f"Dataset too small for a meaningful run (train={train_count}, validation={val_count}). "
            "Expand the reviewed dataset to at least 50 train / 10 validation examples as a technical minimum. "
            "For a pipeline smoke test only, pass --allow-small-dataset; do not use that adapter for research claims."
        )

    def render_conversation(example):
        try:
            return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False, enable_thinking=False)}
        except TypeError:
            return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)}

    dataset["train"] = dataset["train"].map(render_conversation, remove_columns=dataset["train"].column_names)
    dataset["validation"] = dataset["validation"].map(render_conversation, remove_columns=dataset["validation"].column_names)
    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none", task_type="CAUSAL_LM",
    )
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    train_args = SFTConfig(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        gradient_checkpointing=True,
        bf16=compute_dtype == torch.bfloat16,
        fp16=compute_dtype == torch.float16,
        max_length=2048,
        dataset_text_field="text",
        packing=False,
        report_to="none",
        seed=42,
    )
    trainer = SFTTrainer(
        model=model,
        args=train_args,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        processing_class=tokenizer,
        peft_config=lora,
    )
    trainer.train()
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"Saved Qwen adapter to: {output_dir.resolve()}")
    print("Training complete is not evidence of clinical accuracy. Run the held-out benchmark before enabling it for user records.")


if __name__ == "__main__":
    main()
