"""Build an auditable bilingual prompt-to-JSON dataset from real app contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.agent import LocalAssistant  # noqa: E402
from ai.app_tools import build_app_registry  # noqa: E402
from ai.tool_catalog import TOOL_SCHEMA_VERSION, select_tool_names  # noqa: E402
from training.acceptance_cases import acceptance_seeds  # noqa: E402
from training.hard_negative_cases import (  # noqa: E402
    HARD_NEGATIVE_GROUPS,
    hard_negative_seeds,
)
from training.final_acceptance_cases import (  # noqa: E402
    final_answer_seeds,
    final_tool_seeds,
)
from training.release_acceptance_v3_cases import (  # noqa: E402
    release_answer_seeds,
    release_tool_seeds,
)
from training.tool_cases import PROMPT_VALUE, answer_seeds, tool_seeds  # noqa: E402

DATASET_VERSION = "1.4"
CONSUMED_ACCEPTANCE_V1_SHA256 = "72209a4c318682463ef2636c992e3d83817f2d64b3f63bb68e52b8bfaea360b6"
CONSUMED_FINAL_ACCEPTANCE_V2_SHA256 = "e2ef1f374b0fbe3318ca2d6e7c61aa4d1097f089a3feb3b27be9c4a229e6eeb1"
SEALED_RELEASE_ACCEPTANCE_V3_SHA256 = "90eb17f0f844d497c56ea418a5c108c13da71ec4eccd1833b56b369e75d7bcc0"

WRAPPERS = {
    "en": (
        lambda text: text,
        lambda text: f"Please use the active Book. {text}",
        lambda text: f"In SciPlotter, {text[0].lower() + text[1:]}",
    ),
    "th": (
        lambda text: text,
        lambda text: f"ช่วยใช้ข้อมูลในบุ๊กที่เปิดอยู่แล้ว{text}",
        lambda text: f"ใน SciPlotter {text}",
    ),
}


class DatasetContractError(ValueError):
    pass


def _replace_prompt(value: Any, prompt: str) -> Any:
    if value == PROMPT_VALUE:
        return prompt
    if isinstance(value, list):
        return [_replace_prompt(item, prompt) for item in value]
    if isinstance(value, dict):
        return {key: _replace_prompt(item, prompt) for key, item in value.items()}
    return value


def _target_json(tool: str | None, arguments: Dict[str, Any], answer: str = "") -> str:
    payload = {"tool": tool, "arguments": arguments} if tool else {"answer": answer}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_records() -> tuple[list[dict], list[dict]]:
    registry = build_app_registry(object())
    assistant = LocalAssistant(registry, client=None)
    available = registry.names()
    seeds = tool_seeds()
    expected = set(available)
    observed = {seed.tool for seed in seeds}
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise DatasetContractError(f"Tool coverage mismatch; missing={missing}, extra={extra}")

    by_tool: dict[str, list] = {name: [] for name in available}
    for seed in seeds:
        by_tool[seed.tool].append(seed)
    wrong_count = {name: len(items) for name, items in by_tool.items() if len(items) != 4}
    if wrong_count:
        raise DatasetContractError(f"Each tool needs four curated seeds: {wrong_count}")

    train: list[dict] = []
    validation: list[dict] = []
    seen_prompts: set[str] = set()
    for tool_index, tool_name in enumerate(available):
        tool = registry.get(tool_name)
        assert tool is not None
        held_out_seed = tool_index % 4
        for seed_index, seed in enumerate(by_tool[tool_name]):
            split = validation if seed_index == held_out_seed else train
            seed_key = f"{tool_name}:{seed_index}"
            for variant, wrapper in enumerate(WRAPPERS[seed.language]):
                prompt = wrapper(seed.text).strip()
                normalized = " ".join(prompt.casefold().split())
                if normalized in seen_prompts:
                    raise DatasetContractError(f"Duplicate prompt: {prompt}")
                seen_prompts.add(normalized)
                arguments = _replace_prompt(seed.arguments, prompt)
                error = registry.validate_arguments(tool_name, arguments)
                if error:
                    raise DatasetContractError(f"{seed_key} has invalid arguments: {error}")
                offered = select_tool_names(prompt, available)
                if tool_name not in offered:
                    raise DatasetContractError(
                        f"{seed_key} target {tool_name!r} is absent from offered tools {offered}"
                    )
                record = {
                    "id": f"tool-{tool_index:02d}-{seed_index}-{variant}",
                    "seed_id": seed_key,
                    "language": seed.language,
                    "domain": seed.domain,
                    "kind": "tool_call",
                    "user": prompt,
                    "tool": tool_name,
                    "arguments": arguments,
                    "risk": tool.risk,
                    "offered_tools": offered,
                    "target": _target_json(tool_name, arguments),
                    "schema_version": TOOL_SCHEMA_VERSION,
                }
                # Catch drift between the selected catalogue and the exact
                # prompt the trainer will reconstruct.
                system = assistant.system_prompt(prompt)
                if not all(f'"name":"{name}"' in system for name in offered):
                    raise DatasetContractError(f"Prompt catalogue drift for {seed_key}")
                split.append(record)

    for index, seed in enumerate(answer_seeds()):
        destination = validation if index % 5 == 0 else train
        for variant, wrapper in enumerate(WRAPPERS[seed.language][:2]):
            prompt = wrapper(seed.text).strip()
            normalized = " ".join(prompt.casefold().split())
            if normalized in seen_prompts:
                raise DatasetContractError(f"Duplicate answer prompt: {prompt}")
            seen_prompts.add(normalized)
            destination.append(
                {
                    "id": f"answer-{index:02d}-{variant}",
                    "seed_id": f"answer:{index}",
                    "language": seed.language,
                    "domain": seed.category,
                    "kind": "answer",
                    "user": prompt,
                    "tool": None,
                    "arguments": {},
                    "risk": "read",
                    "offered_tools": select_tool_names(prompt, available),
                    "target": _target_json(None, {}, seed.answer),
                    "schema_version": TOOL_SCHEMA_VERSION,
                }
            )

    # Every paraphrase of one seed must stay in one split.
    train_seeds = {record["seed_id"] for record in train}
    validation_seeds = {record["seed_id"] for record in validation}
    overlap = train_seeds & validation_seeds
    if overlap:
        raise DatasetContractError(f"Seed leakage across splits: {sorted(overlap)}")
    return train, validation


def _auxiliary_record(
    seed,
    *,
    record_id: str,
    seed_id: str,
    role: str,
    schema_version: str = TOOL_SCHEMA_VERSION,
) -> dict:
    registry = build_app_registry(object())
    assistant = LocalAssistant(registry, client=None)
    available = registry.names()
    prompt = seed.text.strip()
    arguments = _replace_prompt(seed.arguments, prompt)
    error = registry.validate_arguments(seed.tool, arguments)
    if error:
        raise DatasetContractError(f"{seed_id} has invalid arguments: {error}")
    offered = select_tool_names(prompt, available)
    if seed.tool not in offered:
        raise DatasetContractError(
            f"{seed_id} target {seed.tool!r} is absent from offered tools {offered}"
        )
    system = assistant.system_prompt(prompt)
    if not all(f'"name":"{name}"' in system for name in offered):
        raise DatasetContractError(f"Prompt catalogue drift for {seed_id}")
    tool = registry.get(seed.tool)
    assert tool is not None
    return {
        "id": record_id,
        "seed_id": seed_id,
        "contrast_group": seed.group,
        "dataset_role": role,
        "language": seed.language,
        "domain": seed.domain,
        "kind": "tool_call",
        "user": prompt,
        "tool": seed.tool,
        "arguments": arguments,
        "risk": tool.risk,
        "offered_tools": offered,
        "target": _target_json(seed.tool, arguments),
        "schema_version": schema_version,
    }


def build_auxiliary_records(
    train: list[dict] | None = None,
    validation: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Build repair training plus a permanently training-excluded test set."""
    if train is None or validation is None:
        train, validation = build_records()

    # Replay one untouched record per tool plus every direct-answer training
    # record. The v3 audit showed that a single answer replay was insufficient.
    replay_by_tool = {}
    for record in train:
        if record["kind"] == "tool_call":
            replay_by_tool.setdefault(record["tool"], record)
    repair = [
        {**record, "dataset_role": "repair_replay"}
        for record in replay_by_tool.values()
    ]
    repair.extend(
        {
            **record,
            "seed_id": f"answer-replay:{record['id']}",
            "dataset_role": "answer_replay",
        }
        for record in train
        if record["kind"] == "answer"
    )
    repair.extend(
        _auxiliary_record(
            seed,
            record_id=f"hard-{index:03d}",
            seed_id=f"hard:{seed.group}:{index}",
            role="hard_negative_train",
        )
        for index, seed in enumerate(hard_negative_seeds())
    )
    acceptance = [
        _auxiliary_record(
            seed,
            record_id=f"accept-{index:03d}",
            seed_id=f"accept:{seed.group}:{index}",
            role="acceptance_test",
        )
        for index, seed in enumerate(acceptance_seeds())
    ]

    def prompts(records: Iterable[dict]) -> set[str]:
        return {" ".join(record["user"].casefold().split()) for record in records}

    base_prompts = prompts(train + validation)
    hard_prompts = prompts(
        [record for record in repair if record["dataset_role"] == "hard_negative_train"]
    )
    acceptance_prompts = prompts(acceptance)
    if base_prompts & hard_prompts:
        raise DatasetContractError("Hard-negative prompt duplicates the base dataset")
    if acceptance_prompts & (base_prompts | hard_prompts):
        raise DatasetContractError("Acceptance prompt leaked into training data")
    if len(acceptance_prompts) != len(acceptance):
        raise DatasetContractError("Duplicate prompt inside acceptance test")
    return repair, acceptance


def _final_answer_record(seed, *, index: int, schema_version: str = "1.3") -> dict:
    available = build_app_registry(object()).names()
    prompt = seed.text.strip()
    return {
        "id": f"final-answer-{index:03d}",
        "seed_id": f"final-answer:{index}",
        "dataset_role": "final_acceptance_test",
        "language": seed.language,
        "domain": seed.category,
        "kind": "answer",
        "user": prompt,
        "tool": None,
        "arguments": {},
        "risk": "read",
        "offered_tools": select_tool_names(prompt, available),
        "target": _target_json(None, {}, seed.answer),
        "schema_version": schema_version,
    }


def build_final_acceptance_records(
    train: list[dict] | None = None,
    validation: list[dict] | None = None,
    repair: list[dict] | None = None,
    consumed_acceptance: list[dict] | None = None,
) -> list[dict]:
    """Build the sealed post-v3 gate without feeding it to training paths."""
    if train is None or validation is None:
        train, validation = build_records()
    if repair is None or consumed_acceptance is None:
        repair, consumed_acceptance = build_auxiliary_records(train, validation)
    records = [
        _auxiliary_record(
            seed,
            record_id=f"final-tool-{index:03d}",
            seed_id=f"final-tool:{seed.group}:{index}",
            role="final_acceptance_test",
            schema_version="1.3",
        )
        for index, seed in enumerate(final_tool_seeds())
    ]
    records.extend(
        _final_answer_record(seed, index=index, schema_version="1.3")
        for index, seed in enumerate(final_answer_seeds())
    )
    occupied = {
        " ".join(record["user"].casefold().split())
        for record in train + validation + repair + consumed_acceptance
    }
    final_prompts = {" ".join(record["user"].casefold().split()) for record in records}
    if len(final_prompts) != len(records):
        raise DatasetContractError("Duplicate prompt inside final acceptance test")
    if occupied & final_prompts:
        raise DatasetContractError("Final acceptance prompt leaked into an earlier dataset")
    return records


def _release_answer_record(seed, *, index: int) -> dict:
    available = build_app_registry(object()).names()
    prompt = seed.text.strip()
    return {
        "id": f"release3-answer-{index:03d}",
        "seed_id": f"release3-answer:{index}",
        "dataset_role": "release_acceptance_test",
        "language": seed.language,
        "domain": seed.category,
        "kind": "answer",
        "user": prompt,
        "tool": None,
        "arguments": {},
        "risk": "read",
        "offered_tools": select_tool_names(prompt, available),
        "target": _target_json(None, {}, seed.answer),
        "schema_version": TOOL_SCHEMA_VERSION,
    }


def build_release_acceptance_v3_records(
    train: list[dict] | None = None,
    validation: list[dict] | None = None,
    repair: list[dict] | None = None,
    consumed_acceptance: list[dict] | None = None,
    consumed_final: list[dict] | None = None,
) -> list[dict]:
    """Build the broad, sealed gate for the 1.7B release track."""
    if train is None or validation is None:
        train, validation = build_records()
    if repair is None or consumed_acceptance is None:
        repair, consumed_acceptance = build_auxiliary_records(train, validation)
    if consumed_final is None:
        consumed_final = build_final_acceptance_records(
            train, validation, repair, consumed_acceptance
        )
    tool_records = [
        _auxiliary_record(
            seed,
            record_id=f"release3-tool-{index:03d}",
            seed_id=f"release3-tool:{seed.tool}:{index}",
            role="release_acceptance_test",
        )
        for index, seed in enumerate(release_tool_seeds())
    ]
    registry_tools = set(build_app_registry(object()).names())
    covered_tools = {record["tool"] for record in tool_records}
    if covered_tools != registry_tools or len(tool_records) != len(registry_tools):
        raise DatasetContractError(
            "Release acceptance v3 must contain exactly one case per registered tool"
        )
    records = tool_records + [
        _release_answer_record(seed, index=index)
        for index, seed in enumerate(release_answer_seeds())
    ]
    occupied = {
        " ".join(record["user"].casefold().split())
        for record in train
        + validation
        + repair
        + consumed_acceptance
        + consumed_final
    }
    release_prompts = {
        " ".join(record["user"].casefold().split()) for record in records
    }
    if len(release_prompts) != len(records):
        raise DatasetContractError("Duplicate prompt inside release acceptance v3")
    if occupied & release_prompts:
        raise DatasetContractError(
            "Release acceptance v3 prompt leaked into an earlier dataset"
        )
    return records


def _jsonl_bytes(records: Iterable[dict]) -> bytes:
    return (
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        )
    ).encode("utf-8")


def _git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def _read_verified_archive(path: Path, expected_sha256: str, label: str) -> bytes:
    if not path.is_file():
        raise DatasetContractError(f"{label} archive is missing")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise DatasetContractError(f"{label} archive hash changed")
    return content


def _seal_or_verify_release_v3(path: Path, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    if SEALED_RELEASE_ACCEPTANCE_V3_SHA256:
        if digest != SEALED_RELEASE_ACCEPTANCE_V3_SHA256:
            raise DatasetContractError(
                "Sealed release acceptance v3 source changed; create a new versioned gate"
            )
        _read_verified_archive(
            path,
            SEALED_RELEASE_ACCEPTANCE_V3_SHA256,
            "Sealed release acceptance v3",
        )
        return digest
    if path.is_file() and path.read_bytes() != content:
        raise DatasetContractError("Unsealed release acceptance v3 file differs from source")
    if not path.is_file():
        path.write_bytes(content)
    return digest


def write_dataset(output_dir: Path) -> dict:
    train, validation = build_records()
    repair, consumed_acceptance = build_auxiliary_records(train, validation)
    final_acceptance = build_final_acceptance_records(
        train, validation, repair, consumed_acceptance
    )
    release_acceptance = build_release_acceptance_v3_records(
        train, validation, repair, consumed_acceptance, final_acceptance
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    train_bytes = _jsonl_bytes(train)
    validation_bytes = _jsonl_bytes(validation)
    repair_bytes = _jsonl_bytes(repair)
    final_acceptance_bytes = _jsonl_bytes(final_acceptance)
    release_acceptance_bytes = _jsonl_bytes(release_acceptance)
    (output_dir / "train.jsonl").write_bytes(train_bytes)
    (output_dir / "validation.jsonl").write_bytes(validation_bytes)
    (output_dir / "repair_train.jsonl").write_bytes(repair_bytes)
    consumed_bytes = _read_verified_archive(
        output_dir / "acceptance_test_v1_consumed.jsonl",
        CONSUMED_ACCEPTANCE_V1_SHA256,
        "Consumed acceptance v1",
    )
    final_hash = hashlib.sha256(final_acceptance_bytes).hexdigest()
    if final_hash != CONSUMED_FINAL_ACCEPTANCE_V2_SHA256:
        raise DatasetContractError(
            "Consumed final acceptance v2 source changed; create a new versioned gate instead"
        )
    _read_verified_archive(
        output_dir / "final_acceptance_test.jsonl",
        CONSUMED_FINAL_ACCEPTANCE_V2_SHA256,
        "Consumed final acceptance v2",
    )
    release_hash = _seal_or_verify_release_v3(
        output_dir / "release_acceptance_v3.jsonl",
        release_acceptance_bytes,
    )
    consumed_hash = hashlib.sha256(consumed_bytes).hexdigest()
    all_records = train + validation
    manifest = {
        "dataset_version": DATASET_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "source_revision": _git_revision(),
        "privacy": "synthetic scientific prompts; no researcher data",
        "counts": {
            "train": len(train),
            "validation": len(validation),
            "repair_train": len(repair),
            "acceptance_test_v1_consumed": len(consumed_acceptance),
            "final_acceptance_test_v2_consumed": len(final_acceptance),
            "release_acceptance_v3_sealed": len(release_acceptance),
            "hard_negative_groups": len(HARD_NEGATIVE_GROUPS),
            "tools": len({record["tool"] for record in all_records if record["tool"]}),
            "languages": dict(Counter(record["language"] for record in all_records)),
            "kinds": dict(Counter(record["kind"] for record in all_records)),
            "risks": dict(Counter(record["risk"] for record in all_records)),
        },
        "sha256": {
            "train.jsonl": hashlib.sha256(train_bytes).hexdigest(),
            "validation.jsonl": hashlib.sha256(validation_bytes).hexdigest(),
            "repair_train.jsonl": hashlib.sha256(repair_bytes).hexdigest(),
            "acceptance_test_v1_consumed.jsonl": consumed_hash,
            "final_acceptance_test.jsonl": final_hash,
            "release_acceptance_v3.jsonl": release_hash,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=REPO_ROOT / "training" / "data"
    )
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args()
    if args.check:
        train, validation = build_records()
        repair, consumed_acceptance = build_auxiliary_records(train, validation)
        final_acceptance = build_final_acceptance_records(
            train, validation, repair, consumed_acceptance
        )
        release_acceptance = build_release_acceptance_v3_records(
            train, validation, repair, consumed_acceptance, final_acceptance
        )
        final_hash = hashlib.sha256(_jsonl_bytes(final_acceptance)).hexdigest()
        if final_hash != CONSUMED_FINAL_ACCEPTANCE_V2_SHA256:
            raise DatasetContractError(
                "Consumed final acceptance v2 source changed; create a new versioned gate instead"
            )
        _read_verified_archive(
            args.output_dir / "acceptance_test_v1_consumed.jsonl",
            CONSUMED_ACCEPTANCE_V1_SHA256,
            "Consumed acceptance v1",
        )
        _read_verified_archive(
            args.output_dir / "final_acceptance_test.jsonl",
            CONSUMED_FINAL_ACCEPTANCE_V2_SHA256,
            "Consumed final acceptance v2",
        )
        release_hash = hashlib.sha256(_jsonl_bytes(release_acceptance)).hexdigest()
        if SEALED_RELEASE_ACCEPTANCE_V3_SHA256:
            if release_hash != SEALED_RELEASE_ACCEPTANCE_V3_SHA256:
                raise DatasetContractError(
                    "Sealed release acceptance v3 source changed; create a new versioned gate"
                )
            _read_verified_archive(
                args.output_dir / "release_acceptance_v3.jsonl",
                SEALED_RELEASE_ACCEPTANCE_V3_SHA256,
                "Sealed release acceptance v3",
            )
        print(json.dumps({
            "train": len(train),
            "validation": len(validation),
            "repair_train": len(repair),
            "acceptance_test_v1_consumed": len(consumed_acceptance),
            "final_acceptance_test_v2_consumed": len(final_acceptance),
            "release_acceptance_v3_sealed": len(release_acceptance),
            "release_acceptance_v3_sha256": release_hash,
        }))
    else:
        print(json.dumps(write_dataset(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
