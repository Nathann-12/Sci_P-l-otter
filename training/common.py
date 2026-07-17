"""Shared dataset/prompt helpers without importing training frameworks."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent import LocalAssistant  # noqa: E402
from ai.app_tools import build_app_registry  # noqa: E402
from ai.tool_catalog import TOOL_SCHEMA_VERSION, select_tool_names  # noqa: E402


def accumulation_group_size(batch_index: int, total_batches: int, accumulation: int) -> int:
    """Return the loss divisor for the current accumulation group."""
    if batch_index < 1 or total_batches < batch_index or accumulation < 1:
        raise ValueError("invalid gradient-accumulation position")
    group_start = ((batch_index - 1) // accumulation) * accumulation
    return min(accumulation, total_batches - group_start)


def reject_acceptance_training(records: Iterable[dict]) -> None:
    """Make accidental tuning on the final acceptance set a hard failure."""
    leaked = [
        record.get("id", "?")
        for record in records
        if str(record.get("dataset_role", "")).endswith("acceptance_test")
    ]
    if leaked:
        raise ValueError(
            "Acceptance-test records are evaluation-only and cannot be used for training: "
            + ", ".join(leaked[:5])
        )


def load_jsonl(path: str | Path) -> list[dict]:
    records = []
    with Path(path).open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records


def validate_records(records: Iterable[dict]) -> None:
    registry = build_app_registry(object())
    names = registry.names()
    seen = set()
    for record in records:
        required = {"id", "seed_id", "language", "kind", "user", "target", "schema_version"}
        missing = required - set(record)
        if missing:
            raise ValueError(f"{record.get('id', '?')}: missing fields {sorted(missing)}")
        if record["id"] in seen:
            raise ValueError(f"duplicate record id: {record['id']}")
        seen.add(record["id"])
        if record["schema_version"] != TOOL_SCHEMA_VERSION:
            raise ValueError(f"{record['id']}: stale tool schema version")
        target = json.loads(record["target"])
        router_v2 = str(record.get("router_protocol", "")) == "2.0"
        if record["kind"] == "tool_call":
            tool = str(target.get("tool") or "")
            if not registry.has(tool):
                raise ValueError(f"{record['id']}: invalid tool target")
            if router_v2:
                if target != {"tool": tool}:
                    raise ValueError(
                        f"{record['id']}: router v2 target must contain only the tool"
                    )
            else:
                arguments = target.get("arguments")
                if not isinstance(arguments, dict):
                    raise ValueError(f"{record['id']}: invalid tool arguments")
                error = registry.validate_arguments(tool, arguments)
                if error:
                    raise ValueError(f"{record['id']}: {error}")
            offered = select_tool_names(record["user"], names)
            if tool not in offered:
                raise ValueError(f"{record['id']}: target tool is not offered")
        elif not isinstance(target.get("answer"), str):
            raise ValueError(f"{record['id']}: invalid answer target")
        elif router_v2 and set(target) != {"answer"}:
            raise ValueError(
                f"{record['id']}: router v2 answer target must contain only answer"
            )


def system_prompt(user_text: str) -> str:
    registry = build_app_registry(object())
    return LocalAssistant(registry, client=None).system_prompt(user_text)


def render_prompt(tokenizer, user_text: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt(user_text)},
        {"role": "user", "content": user_text},
    ]
    kwargs = {"tokenize": False, "add_generation_prompt": True}
    try:
        return tokenizer.apply_chat_template(messages, enable_thinking=False, **kwargs)
    except TypeError:
        # Older compatible tokenizer templates use the explicit switch included
        # in SciPlotter's system prompt instead of this keyword.
        return tokenizer.apply_chat_template(messages, **kwargs)


def to_prompt_completion(tokenizer, records: Iterable[dict]) -> list[dict]:
    eos = tokenizer.eos_token or ""
    return [
        {
            "prompt": render_prompt(tokenizer, record["user"]),
            "completion": record["target"] + eos,
            "record_id": record["id"],
        }
        for record in records
    ]
