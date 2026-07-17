"""Memory-conscious PyTorch+PEFT LoRA/QLoRA training for SciPlotter Mini.

The loop is deliberately independent of pyarrow/datasets/TRL because managed
Windows research computers can block their native DLLs. Loss is masked over the
entire prompt and applied only to the target JSON completion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.common import (  # noqa: E402
    accumulation_group_size,
    load_jsonl,
    reject_acceptance_training,
    render_prompt,
    validate_records,
)
from training.preflight import inspect_environment  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument(
        "--resume-adapter",
        type=Path,
        help="continue training an existing LoRA adapter against the same base model",
    )
    parser.add_argument("--train", type=Path, default=REPO_ROOT / "training/data/train.jsonl")
    parser.add_argument("--validation", type=Path, default=REPO_ROOT / "training/data/validation.jsonl")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "training/output/sciplotter-mini-0.6b-lora")
    parser.add_argument("--mode", choices=("auto", "lora", "qlora"), default="auto")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=16)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=-1, help="optimizer steps; -1 uses all epochs")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--eval-limit", type=int, default=0)
    parser.add_argument(
        "--all-variants",
        action="store_true",
        help="train every paraphrase every epoch instead of rotating one per seed",
    )
    parser.add_argument("--allow-low-free-vram", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def tokenize_records(tokenizer, records: list[dict], max_length: int) -> tuple[list[dict], int]:
    rows = []
    longest = 0
    eos_id = tokenizer.eos_token_id
    if eos_id is None:
        raise ValueError("Tokenizer has no EOS token.")
    for record in records:
        prompt_ids = tokenizer(
            render_prompt(tokenizer, record["user"]), add_special_tokens=False
        )["input_ids"]
        completion_ids = tokenizer(record["target"], add_special_tokens=False)["input_ids"]
        if not completion_ids or completion_ids[-1] != eos_id:
            completion_ids.append(eos_id)
        length = len(prompt_ids) + len(completion_ids)
        longest = max(longest, length)
        if length > max_length:
            raise ValueError(
                f"{record['id']} needs {length} tokens but max_length={max_length}; "
                "refusing to truncate the JSON target"
            )
        rows.append(
            {
                "input_ids": prompt_ids + completion_ids,
                "labels": [-100] * len(prompt_ids) + completion_ids,
                "record_id": record["id"],
                "seed_id": record["seed_id"],
            }
        )
    return rows, longest


def main() -> None:
    args = parse_args()
    environment = inspect_environment()
    print(json.dumps(environment, ensure_ascii=False, indent=2))
    if args.preflight_only:
        raise SystemExit(0 if environment["ready"] else 2)
    if not environment["ready"]:
        raise SystemExit("Training environment is not ready; run training/setup_windows.ps1.")
    if environment["vram_free_gb"] < 3.0 and not args.allow_low_free_vram:
        raise SystemExit("Less than 3 GB VRAM is free. Close GPU applications or pass --allow-low-free-vram.")

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from torch.nn.utils.rnn import pad_sequence
    from torch.utils.data import DataLoader, Dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        get_cosine_schedule_with_warmup,
    )

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    train_records = load_jsonl(args.train)
    validation_records = load_jsonl(args.validation)
    reject_acceptance_training(train_records)
    validate_records(train_records + validation_records)

    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    train_rows, train_longest = tokenize_records(tokenizer, train_records, args.max_length)
    validation_rows, validation_longest = tokenize_records(
        tokenizer, validation_records, args.max_length
    )
    longest = max(train_longest, validation_longest)

    class Rows(Dataset):
        def __init__(self, values):
            self.values = values

        def __len__(self):
            return len(self.values)

        def __getitem__(self, index):
            return self.values[index]

    def collate(batch):
        inputs = [torch.tensor(item["input_ids"], dtype=torch.long) for item in batch]
        labels = [torch.tensor(item["labels"], dtype=torch.long) for item in batch]
        input_ids = pad_sequence(inputs, batch_first=True, padding_value=tokenizer.pad_token_id)
        label_ids = pad_sequence(labels, batch_first=True, padding_value=-100)
        return {
            "input_ids": input_ids,
            "attention_mask": input_ids.ne(tokenizer.pad_token_id).long(),
            "labels": label_ids,
        }

    def group_variants(rows):
        groups = {}
        for row in rows:
            groups.setdefault(row["seed_id"], []).append(row)
        return list(groups.values())

    train_groups = group_variants(train_rows)
    validation_groups = group_variants(validation_rows)

    def epoch_values(epoch: int):
        if args.all_variants:
            return train_rows
        return [group[(epoch + index) % len(group)] for index, group in enumerate(train_groups)]

    eval_values = (
        validation_rows
        if args.all_variants
        else [group[0] for group in validation_groups]
    )
    eval_values = eval_values[: args.eval_limit or None]
    eval_loader = DataLoader(Rows(eval_values), batch_size=1, shuffle=False, collate_fn=collate)

    mode = environment["recommended_mode"] if args.mode == "auto" else args.mode
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model_kwargs = {"dtype": dtype, "low_cpu_mem_usage": True, "device_map": {"": 0}}
    if mode == "qlora":
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_use_double_quant=True,
        )
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    model.config.use_cache = False
    if mode == "qlora":
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
    else:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    if args.resume_adapter:
        if not (args.resume_adapter / "adapter_config.json").is_file():
            raise SystemExit(f"Invalid LoRA adapter directory: {args.resume_adapter}")
        model = PeftModel.from_pretrained(
            model,
            args.resume_adapter,
            is_trainable=True,
        )
    else:
        model = get_peft_model(
            model,
            LoraConfig(
                r=args.lora_r,
                lora_alpha=args.lora_r * 2,
                lora_dropout=0.05,
                bias="none",
                task_type="CAUSAL_LM",
                target_modules="all-linear",
            ),
        )
    model.print_trainable_parameters()

    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=args.learning_rate, weight_decay=0.01)
    updates_per_epoch = math.ceil(
        len(epoch_values(0)) / (args.batch_size * args.gradient_accumulation)
    )
    total_updates = args.max_steps if args.max_steps > 0 else updates_per_epoch * args.epochs
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=max(1, int(total_updates * 0.05)),
        num_training_steps=max(1, total_updates),
    )

    def evaluate_loss() -> float:
        model.eval()
        losses = []
        with torch.inference_mode():
            for batch in eval_loader:
                batch = {key: value.to(model.device) for key, value in batch.items()}
                losses.append(float(model(**batch).loss.detach().cpu()))
        model.train()
        return sum(losses) / max(1, len(losses))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    optimizer.zero_grad(set_to_none=True)
    optimizer_step = 0
    micro_step = 0
    best_eval = float("inf")
    running_loss = 0.0
    stop = False
    model.train()
    if args.resume_adapter and not args.skip_eval:
        best_eval = evaluate_loss()
        print(json.dumps({"epoch": 0, "eval_loss": best_eval}), flush=True)
        model.save_pretrained(args.output_dir, safe_serialization=True)
        tokenizer.save_pretrained(args.output_dir)
    for epoch in range(args.epochs):
        generator = torch.Generator().manual_seed(args.seed + epoch)
        train_loader = DataLoader(
            Rows(epoch_values(epoch)),
            batch_size=args.batch_size,
            shuffle=True,
            generator=generator,
            collate_fn=collate,
        )
        for batch_index, batch in enumerate(train_loader, 1):
            batch = {key: value.to(model.device) for key, value in batch.items()}
            loss = model(**batch).loss
            group_size = accumulation_group_size(
                batch_index,
                len(train_loader),
                args.gradient_accumulation,
            )
            (loss / group_size).backward()
            running_loss += float(loss.detach().cpu())
            micro_step += 1
            should_update = (
                batch_index % args.gradient_accumulation == 0
                or batch_index == len(train_loader)
            )
            if not should_update:
                continue
            torch.nn.utils.clip_grad_norm_(parameters, 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            optimizer_step += 1
            if optimizer_step == 1 or optimizer_step % 5 == 0:
                print(
                    json.dumps(
                        {
                            "epoch": epoch + 1,
                            "optimizer_step": optimizer_step,
                            "loss": running_loss / max(1, micro_step),
                            "lr": scheduler.get_last_lr()[0],
                            "allocated_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
                        }
                    ),
                    flush=True,
                )
            if args.max_steps > 0 and optimizer_step >= args.max_steps:
                stop = True
                break
        if not args.skip_eval:
            eval_loss = evaluate_loss()
            print(json.dumps({"epoch": epoch + 1, "eval_loss": eval_loss}), flush=True)
            if eval_loss < best_eval:
                best_eval = eval_loss
                model.save_pretrained(args.output_dir, safe_serialization=True)
                tokenizer.save_pretrained(args.output_dir)
        if stop:
            break

    if args.skip_eval:
        model.save_pretrained(args.output_dir, safe_serialization=True)
        tokenizer.save_pretrained(args.output_dir)
    metadata = {
        "base_model": args.model,
        "resumed_from": str(args.resume_adapter) if args.resume_adapter else None,
        "mode": mode,
        "train_examples": len(train_records),
        "train_seed_groups": len(train_groups),
        "validation_examples": len(validation_records),
        "validation_seed_groups": len(validation_groups),
        "variant_schedule": "all_each_epoch" if args.all_variants else "rotate_one_per_seed",
        "longest_tokens": longest,
        "optimizer_steps": optimizer_step,
        "mean_microbatch_loss": running_loss / max(1, micro_step),
        "best_eval_loss": None if args.skip_eval else best_eval,
        "seed": args.seed,
        "lora_r": args.lora_r,
        "learning_rate": args.learning_rate,
        "epochs_requested": args.epochs,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "max_length": args.max_length,
        "tool_schema_version": train_records[0].get("schema_version"),
        "train_sha256": hashlib.sha256(args.train.read_bytes()).hexdigest(),
        "validation_sha256": hashlib.sha256(args.validation.read_bytes()).hexdigest(),
        "max_allocated_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
        "completion_only_loss": True,
    }
    (args.output_dir / "sciplotter_training.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
