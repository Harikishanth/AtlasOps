t"""Supervised fine-tuning entrypoint for AtlasOps.

Uses QLoRA (4-bit quantised base + LoRA adapters) so all 4 agent roles
can be trained as separate lightweight adapters on top of one shared
Qwen2.5-7B base — enabling co-hosting on a single AMD MI300X.
"""

import argparse
from pathlib import Path

from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from trl import SFTTrainer


# One LoRA config shared across all 4 agent roles.
# r=16 / alpha=32 is a solid default for 7B instruction-following tasks.
LORA_CONFIG = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    bias="none",
)

BNBCONFIG = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
    bnb_4bit_use_double_quant=True,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",      required=True, help="Base model id/path")
    parser.add_argument("--data",       required=True, help="Path to jsonl SFT corpus")
    parser.add_argument("--output",     required=True, help="Output directory (LoRA adapter)")
    parser.add_argument("--role",       default="all",  help="Agent role tag (triage/diagnosis/remediation/comms/all)")
    parser.add_argument("--epochs",     type=int,   default=1)
    parser.add_argument("--lr",         type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int,   default=2)
    parser.add_argument("--grad-accum", type=int,   default=4)
    parser.add_argument("--max-seq-len",type=int,   default=2048)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Filter corpus to specific agent role if requested
    dataset = load_dataset("json", data_files=args.data, split="train")
    if args.role != "all":
        dataset = dataset.filter(lambda x: x.get("role") == args.role)

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # QLoRA: 4-bit quantised base model
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=BNBCONFIG,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LORA_CONFIG)
    model.print_trainable_parameters()

    train_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to=[],
        optim="paged_adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=train_args,
        max_seq_length=args.max_seq_len,
    )
    trainer.train()
    # Save only the LoRA adapter (~40 MB), not the full 7B weights
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"LoRA adapter saved to {output_dir}")


if __name__ == "__main__":
    main()
