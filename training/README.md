# SciPlotter Mini fine-tuning

This directory trains Qwen3 0.6B or 1.7B to route bilingual scientific requests into
SciPlotter's existing JSON tool protocol. The model does not calculate results;
the deterministic application tools still perform all scientific work.

Runtime note: Safe Router v2 executes only the model's selected tool name. It
rebuilds arguments from the user's text and the active Book, and discards any
`arguments` object emitted by these legacy schema-v1.4 adapters. The tracked
datasets and sealed acceptance files remain unchanged for reproducibility; do
not rebuild or reinterpret the unopened v3 gate while developing the router.
New selection-only candidates use the separate, versioned workflow in
`training/router_v2/README.md`; the legacy files below remain reproducible and
unchanged.

The tracked dataset contains synthetic but realistic column names, units and
parameters. It contains no customer or researcher measurements.

## Current training contract

- Bases: `Qwen/Qwen3-0.6B` and `Qwen/Qwen3-1.7B` (Apache-2.0)
- Objective: prompt/completion SFT in a PyTorch+PEFT loop; loss applies to the
  JSON completion only (no pyarrow/TRL dependency on managed Windows systems)
- Adapter: LoRA on all linear layers; rank 16 for 0.6B and rank 8 for the
  memory-constrained 1.7B track
- Local 4 GB GPU mode: NF4 QLoRA, batch 1; the tested 1.7B configuration uses
  gradient accumulation 8 and peaks near 3.61 GB VRAM
- Train/validation split: grouped by curated seed so paraphrases never cross
  the split
- Training rotates one paraphrase per seed per epoch; three epochs cover all
  variants without paying for duplicate semantics in every epoch
- Legacy adapter audit targets: exact JSON, exact tool name and exact arguments.
  Runtime release additionally requires Safe Router clarification/confirmation
  regression tests; model-authored arguments are never a trusted execution path.

## 1. Rebuild and audit data

```powershell
.venv\Scripts\python.exe training\build_dataset.py
.venv\Scripts\python.exe training\build_dataset.py --check
```

The builder fails if a tool is missing, an argument no longer matches the app
schema, a target tool is absent from the compact prompt, a prompt is duplicated,
or a seed leaks across train and validation.

It also maintains deliberately separate training and audit files:

- `repair_train.jsonl`: 56 Thai contrastive hard negatives across 14 failure
  groups, one replay record for each of the 44 tools, and all 18 direct-answer
  training records (118 records total).
- `acceptance_test_v1_consumed.jsonl`: the immutable 28-intent Thai audit used
  for v2/v3. Its SHA-256 is checked on every build.
- `final_acceptance_test.jsonl`: the immutable, consumed 26-intent bilingual
  v4 audit (14 tool calls and 12 direct answers). Its source and file hashes are
  sealed; changing it requires a new versioned gate.
- `release_acceptance_v3.jsonl`: a sealed 56-intent gate for the 1.7B track,
  with one case for every tool plus 12 direct answers and balanced Thai/English.
  It is not opened until the 1.7B candidate is frozen.

Both audit roles end in `acceptance_test`, so the trainer refuses to load them
as training data. Never use their failures to modify a later candidate.

## 2. Create the isolated Windows training environment

```powershell
powershell -ExecutionPolicy Bypass -File training\setup_windows.ps1
```

This installs a CUDA PyTorch wheel and Hugging Face training packages under
`training/.venv`; it does not modify SciPlotter's application environment.
Close browsers, Teams, AI desktop applications and GPU overlays until at least
3 GB VRAM is free, then verify:

```powershell
training\.venv\Scripts\python.exe training\preflight.py
```

## 3. Train the first adapter

```powershell
training\.venv\Scripts\python.exe training\train_lora.py --mode qlora
```

For an intentionally short pipeline smoke test, use
`--max-steps 1 --skip-eval`. A release
candidate should use the default three epochs, retain the best validation-loss
checkpoint, and be compared against the unmodified Qwen3 baseline.

To continue a reviewed adapter at a lower learning rate without losing the
starting checkpoint when validation regresses:

```powershell
training\.venv\Scripts\python.exe training\train_lora.py `
  --resume-adapter training\output\sciplotter-mini-0.6b-lora-v1 `
  --epochs 2 --learning-rate 5e-5 `
  --output-dir training\output\sciplotter-mini-0.6b-lora-v2
```

For the focused Thai repair pass:

```powershell
training\.venv\Scripts\python.exe training\train_lora.py `
  --resume-adapter training\output\sciplotter-mini-0.6b-lora-v2 `
  --train training\data\repair_train.jsonl `
  --epochs 3 --learning-rate 5e-5 `
  --output-dir training\output\sciplotter-mini-0.6b-lora-v3
```

The v4 balance-restoration pass starts from v3, replays all direct-answer
training records, and keeps the lower-loss epoch:

```powershell
training\.venv\Scripts\python.exe training\train_lora.py `
  --resume-adapter training\output\sciplotter-mini-0.6b-lora-v3 `
  --train training\data\repair_train.jsonl `
  --epochs 2 --learning-rate 3e-5 `
  --output-dir training\output\sciplotter-mini-0.6b-lora-v4
```

For a 4 GB GPU, first train the 1.7B base adapter for one full intent rotation:

```powershell
training\.venv\Scripts\python.exe training\train_lora.py `
  --model Qwen/Qwen3-1.7B --mode qlora `
  --epochs 1 --learning-rate 1e-4 --lora-r 8 `
  --max-length 1152 --gradient-accumulation 8 `
  --output-dir training\output\sciplotter-mini-1.7b-lora-v1
```

## 4. Evaluate before merging

```powershell
training\.venv\Scripts\python.exe training\evaluate_router.py `
  training\output\sciplotter-mini-0.6b-lora --load-in-4bit --one-per-seed
```

`--one-per-seed` is the fast intent-level gate. Run again without it before a
release to verify all held-out paraphrase wrappers.

Evaluate a fresh acceptance file only after the candidate is frozen. Record its
SHA-256 and result in `ACCEPTANCE_LOG.md`; after viewing the result, that test is
consumed for the candidate family and must not drive another training change.
The first two acceptance files are consumed. `release_acceptance_v3.jsonl` is
sealed but initially unopened; after its first evaluation it is also consumed
and a later candidate requires another versioned, prompt-disjoint gate.

Minimum release gates:

- valid JSON: 99% or higher
- correct tool: 97% or higher overall and 95% or higher in each language
- exact arguments: 92% or higher
- direct-answer accuracy: 95% or higher
- no regression in mutation/device confirmation tests
- manual review of every validation failure

The exact-arguments gate remains a diagnostic for the frozen v1.4 candidate
family. Under Safe Router v2 it is not an execution-safety boundary: deterministic
resolution and its behavioral tests are the authority for arguments.

Do not publish a model selected on training loss alone.

Current status: v4 is an experimental adapter, not a release model. It passed
the validation tool-selection gate but failed the untouched final acceptance
gates for tool selection, exact arguments and direct answers. Do not merge,
convert or distribute it as the downloadable product model.

The 1.7B experiment is also not release-ready. Its best validation candidates
reached 100% direct-answer routing but only 95.45% tool selection overall,
90.91% in Thai and at most 70.45% exact arguments. The sealed v3 acceptance set
was deliberately left unopened. See `ACCEPTANCE_LOG.md` for the complete audit.

## 5. Merge, convert and package

```powershell
training\.venv\Scripts\python.exe training\merge_adapter.py `
  training\output\sciplotter-mini-0.6b-lora `
  training\output\sciplotter-mini-0.6b-merged

training\.venv\Scripts\python.exe training\export_gguf.py `
  training\output\sciplotter-mini-0.6b-merged `
  C:\src\llama.cpp `
  training\output\SciPlotter-Mini-0.6B-Q8_0.gguf
```

The export emits a proposed catalogue entry containing the final size and
SHA-256. Review it, publish the immutable GGUF, replace the placeholder URLs,
add it as a new entry in `ai/model_catalog.py`, then build `.scimodel` with
`scripts/build_ai_model_pack.py`. Never overwrite an existing pack ID/hash.

## Data governance

Real research data is not necessary for intent routing. If opt-in telemetry or
customer examples are ever added, remove values and identifiers, obtain a
separate training consent, record provenance/license per example, and keep that
dataset outside the public product repository.
