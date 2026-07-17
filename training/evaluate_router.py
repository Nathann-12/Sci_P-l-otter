"""Measure exact JSON routing, tool choice and arguments on held-out seeds."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent import _parse_reply  # noqa: E402
from training.common import load_jsonl, render_prompt, validate_records  # noqa: E402


def has_complete_json_object(text: str) -> bool:
    """Return true once a top-level JSON object closes outside a string."""
    depth = 0
    in_string = False
    escaped = False
    started = False
    for character in str(text).lstrip():
        if escaped:
            escaped = False
            continue
        if in_string and character == "\\":
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if character == "{":
            depth += 1
            started = True
        elif character == "}" and started:
            depth -= 1
            if depth == 0:
                return True
    return False


def one_record_per_seed(records: list[dict]) -> list[dict]:
    """Keep one deterministic wrapper per held-out semantic intent."""
    selected = {}
    for record in records:
        selected.setdefault(record["seed_id"], record)
    return list(selected.values())


def score_prediction(record: dict, raw_prediction: str) -> dict:
    parsed = _parse_reply(raw_prediction)
    target = json.loads(record["target"])
    expected_tool = target.get("tool")
    predicted_tool = parsed.get("tool")
    try:
        strict = json.loads(raw_prediction.strip())
        strict_json = isinstance(strict, dict)
    except Exception:
        strict_json = False
    valid_protocol = strict_json and (
        isinstance(parsed.get("answer"), str)
        or (isinstance(predicted_tool, str) and isinstance(parsed.get("arguments"), dict))
    )
    if record["kind"] == "tool_call":
        tool_correct = predicted_tool == expected_tool
        arguments_correct = parsed.get("arguments") == target.get("arguments")
        exact = tool_correct and arguments_correct
        answer_correct = False
    else:
        tool_correct = predicted_tool is None
        arguments_correct = True
        answer_correct = isinstance(parsed.get("answer"), str) and bool(parsed["answer"].strip())
        exact = tool_correct and answer_correct
    return {
        "valid_protocol": bool(valid_protocol),
        "tool_correct": bool(tool_correct),
        "arguments_correct": bool(arguments_correct),
        "answer_correct": bool(answer_correct),
        "exact": bool(exact),
        "parsed": parsed,
    }


def summarize(scored: list[dict]) -> dict:
    total = len(scored)
    tool_calls = [item for item in scored if item["record"]["kind"] == "tool_call"]
    answers = [item for item in scored if item["record"]["kind"] == "answer"]

    def rate(items: list[dict], key: str) -> float | None:
        if not items:
            return None
        return sum(bool(item["score"][key]) for item in items) / len(items)

    metrics = {
        "valid_protocol": rate(scored, "valid_protocol"),
        "exact": rate(scored, "exact"),
        "tool_call_count": len(tool_calls),
        "tool_correct": rate(tool_calls, "tool_correct"),
        "arguments_correct": rate(tool_calls, "arguments_correct"),
        "tool_exact": rate(tool_calls, "exact"),
        "answer_count": len(answers),
        "answer_exact": rate(answers, "exact"),
    }
    per_language = {}
    for language in sorted({item["record"]["language"] for item in scored}):
        subset = [item for item in scored if item["record"]["language"] == language]
        language_tools = [item for item in subset if item["record"]["kind"] == "tool_call"]
        language_answers = [item for item in subset if item["record"]["kind"] == "answer"]
        per_language[language] = {
            "count": len(subset),
            "exact": rate(subset, "exact"),
            "tool_call_count": len(language_tools),
            "tool_correct": rate(language_tools, "tool_correct"),
            "tool_exact": rate(language_tools, "exact"),
            "answer_count": len(language_answers),
            "answer_exact": rate(language_answers, "exact"),
        }
    failures = Counter(
        item["record"].get("tool") or "answer"
        for item in scored
        if not item["score"]["exact"]
    )
    return {
        "count": total,
        **metrics,
        "per_language": per_language,
        "failures_by_target": dict(failures.most_common()),
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("model", help="LoRA adapter directory or merged HF model")
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "training/data/validation.jsonl")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "training/evaluation")
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--kind",
        choices=("tool_call", "answer"),
        help="evaluate only one protocol kind",
    )
    parser.add_argument(
        "--one-per-seed",
        action="store_true",
        help="evaluate one deterministic paraphrase per held-out semantic seed",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        StoppingCriteria,
        StoppingCriteriaList,
    )

    class CompleteJsonCriteria(StoppingCriteria):
        def __init__(self, prompt_length: int):
            self.prompt_length = prompt_length

        def __call__(self, input_ids, scores, **kwargs):
            generated = input_ids[:, self.prompt_length :]
            texts = tokenizer.batch_decode(generated, skip_special_tokens=True)
            return all(has_complete_json_object(text) for text in texts)

    model_path = Path(args.model)
    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)
    kwargs: dict[str, Any] = {"device_map": {"": 0}, "low_cpu_mem_usage": True}
    if args.load_in_4bit:
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=dtype,
        )
    if (model_path / "adapter_config.json").is_file():
        from peft import AutoPeftModelForCausalLM

        model = AutoPeftModelForCausalLM.from_pretrained(args.model, **kwargs)
    else:
        model = AutoModelForCausalLM.from_pretrained(args.model, **kwargs)
    model.eval()
    started = time.perf_counter()
    generated_tokens = 0

    records = load_jsonl(args.data)
    validate_records(records)
    if args.kind:
        records = [record for record in records if record["kind"] == args.kind]
    if args.one_per_seed:
        records = one_record_per_seed(records)
    if args.limit > 0:
        records = records[: args.limit]
    scored = []
    for index, record in enumerate(records, 1):
        prompt = render_prompt(tokenizer, record["user"])
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
                stopping_criteria=StoppingCriteriaList(
                    [CompleteJsonCriteria(inputs["input_ids"].shape[1])]
                ),
            )
        generated = output[0, inputs["input_ids"].shape[1] :]
        generated_tokens += int(generated.numel())
        raw = tokenizer.decode(generated, skip_special_tokens=True).strip()
        scored.append(
            {"record": record, "prediction": raw, "score": score_prediction(record, raw)}
        )
        print(f"[{index}/{len(records)}] {record['id']} exact={scored[-1]['score']['exact']}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions = args.output_dir / "predictions.jsonl"
    predictions.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in scored),
        encoding="utf-8",
    )
    report = summarize(scored)
    elapsed = time.perf_counter() - started
    report["elapsed_seconds"] = round(elapsed, 3)
    report["generated_tokens"] = generated_tokens
    report["tokens_per_second"] = round(generated_tokens / max(elapsed, 1e-9), 3)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
