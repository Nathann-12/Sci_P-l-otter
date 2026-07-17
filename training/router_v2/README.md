# Safe Router v2 training

Current candidate metrics and the sealed-release decision are recorded in
[`STATUS.md`](STATUS.md).

This track trains the local model to choose only a tool name or return a direct
answer. Model-authored arguments are neither a target nor an execution input.
SciPlotter's deterministic resolver owns columns, enums, numbers, units and
clarification.

## Immutable inputs and generated data

`build_dataset.py` verifies SHA-256 hashes for the frozen schema-v1.4 train,
validation and repair sources before converting them. It uses the original
grouped split, adds the 56 Thai hard-negative records plus 52 contrastive
repair records derived only from validation evidence, and emits:

- `data/train.jsonl`: 522 selection-only training records (468 tools, 54 answers)
- `data/validation.jsonl`: 138 held-out records
- `data/release_acceptance_v4.jsonl`: 56 sealed, prompt-disjoint release cases

Rebuild or audit with:

```powershell
training\.venv\Scripts\python.exe -m training.router_v2.build_dataset
training\.venv\Scripts\python.exe -m training.router_v2.build_dataset --check
```

The v4 acceptance SHA-256 is
`5b48cb06b28e582bb2dc49417a9cec0158dd7a7b9685d1a103c91be648cc4361`.
Do not evaluate it until a frozen candidate passes all validation gates. Never
train on it, inspect its failures to repair the same candidate family, or
replace it in place.

## 1.7B QLoRA candidate

```powershell
training\.venv\Scripts\python.exe training\train_lora.py `
  --model Qwen/Qwen3-1.7B `
  --train training\router_v2\data\train.jsonl `
  --validation training\router_v2\data\validation.jsonl `
  --output-dir training\output\sciplotter-mini-1.7b-router-v2 `
  --mode qlora --epochs 3 --learning-rate 0.0001 `
  --max-length 1152 --batch-size 1 --gradient-accumulation 8 `
  --lora-r 8
```

Validate one prompt per held-out seed first:

```powershell
training\.venv\Scripts\python.exe training\evaluate_router.py `
  training\output\sciplotter-mini-1.7b-router-v2 `
  --data training\router_v2\data\validation.jsonl `
  --output-dir training\evaluation\router-v2-validation `
  --load-in-4bit --one-per-seed --max-new-tokens 96
```

Required before opening acceptance v4:

- valid selection-only JSON at least 99.5%
- correct tool at least 98% overall
- correct tool at least 95% in both Thai and English
- direct-answer accuracy at least 98%
- zero execution-safety regression in the application tests

If a candidate fails validation, improve it using training and validation
evidence only. The sealed acceptance file remains unopened.
