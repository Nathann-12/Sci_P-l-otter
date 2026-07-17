"""Merge a reviewed LoRA adapter into Qwen3 before GGUF conversion."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.license_texts import APACHE_2_LICENSE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("adapter", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dtype", choices=("float16", "bfloat16"), default="float16")
    args = parser.parse_args()

    import torch
    from peft import PeftConfig, PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    config = PeftConfig.from_pretrained(args.adapter)
    dtype = torch.float16 if args.dtype == "float16" else torch.bfloat16
    base = AutoModelForCausalLM.from_pretrained(
        config.base_model_name_or_path,
        dtype=dtype,
        device_map={"": "cpu"},
        low_cpu_mem_usage=True,
    )
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()
    args.output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.output, safe_serialization=True, max_shard_size="2GB")
    tokenizer = AutoTokenizer.from_pretrained(args.adapter, use_fast=True)
    tokenizer.save_pretrained(args.output)
    (args.output / "LICENSE").write_text(APACHE_2_LICENSE, encoding="utf-8")
    metadata = {
        "base_model": config.base_model_name_or_path,
        "adapter": str(args.adapter.resolve()),
        "dtype": args.dtype,
        "merged": True,
    }
    (args.output / "sciplotter_merge.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
