"""Build the Safe Router v2 selection-only dataset from frozen v1.4 sources."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.app_tools import build_app_registry  # noqa: E402
from ai.tool_catalog import TOOL_SCHEMA_VERSION, select_tool_names  # noqa: E402
from training.common import load_jsonl, validate_records  # noqa: E402
from training.router_v2.acceptance_v4_cases import (  # noqa: E402
    ANSWER_CASES,
    TOOL_CASES,
)
from training.router_v2.repair_cases import (  # noqa: E402
    ANSWER_REPAIR_CASES,
    TOOL_REPAIR_CASES,
)


ROUTER_PROTOCOL_VERSION = "2.0"
DATASET_VERSION = "2.0"
DATA_DIR = Path(__file__).resolve().parent / "data"
LEGACY_DIR = REPO_ROOT / "training" / "data"
SEALED_ACCEPTANCE_V4_SHA256 = (
    "59a716f8e721ee4a07824edebfd8dd50d79ab294897e068623e8f383571dc6f9"
)

SOURCE_FILES = {
    "train": (
        LEGACY_DIR / "train.jsonl",
        "53ce0c5c8d7ce918b2c161785cfc8b88286417996d1e58c20054ca0981267e34",
    ),
    "validation": (
        LEGACY_DIR / "validation.jsonl",
        "dc842a20f2a9f5df73785bb249c5fdfd0a3d8563afa7a9f1f2ed807bd3886eed",
    ),
    "repair": (
        LEGACY_DIR / "repair_train.jsonl",
        "d8822a892ae36f5b88d604d7442038aac4fcbc9711c4c7044a21f1593ae25707",
    ),
}


class RouterDatasetError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_sources() -> dict[str, str]:
    hashes = {}
    for name, (path, expected) in SOURCE_FILES.items():
        actual = _sha256(path)
        if actual != expected:
            raise RouterDatasetError(
                f"Frozen source {path.name} changed: expected {expected}, got {actual}"
            )
        hashes[name] = actual
    return hashes


def _selection_target(record: dict) -> str:
    if record["kind"] == "tool_call":
        payload = {"tool": record["tool"]}
    else:
        legacy_target = json.loads(record["target"])
        payload = {"answer": str(legacy_target.get("answer", ""))}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _convert(record: dict, *, prefix: str, role: str) -> dict:
    value = {
        "id": f"router2-{prefix}-{record['id']}",
        "seed_id": f"router2:{record['seed_id']}",
        "source_id": record["id"],
        "dataset_role": role,
        "language": record["language"],
        "domain": record.get("domain", "general"),
        "kind": record["kind"],
        "user": record["user"],
        "tool": record.get("tool"),
        "risk": record.get("risk", "read"),
        "offered_tools": list(record.get("offered_tools", [])),
        "target": _selection_target(record),
        "schema_version": TOOL_SCHEMA_VERSION,
        "router_protocol": ROUTER_PROTOCOL_VERSION,
    }
    if record.get("contrast_group"):
        value["contrast_group"] = record["contrast_group"]
    return value


def build_records() -> tuple[list[dict], list[dict]]:
    _verify_sources()
    legacy_train = load_jsonl(SOURCE_FILES["train"][0])
    legacy_validation = load_jsonl(SOURCE_FILES["validation"][0])
    repair = load_jsonl(SOURCE_FILES["repair"][0])
    hard_negatives = [
        record
        for record in repair
        if record.get("dataset_role") == "hard_negative_train"
    ]

    train = [
        _convert(record, prefix="train", role="router_v2_train")
        for record in legacy_train
    ]
    train.extend(
        _convert(record, prefix="hard", role="router_v2_hard_negative")
        for record in hard_negatives
    )
    train.extend(_router_v2_repair_records())
    validation = [
        _convert(record, prefix="validation", role="router_v2_validation")
        for record in legacy_validation
    ]
    _audit(train, validation)
    return train, validation


def _router_v2_repair_records() -> list[dict]:
    registry = build_app_registry(object())
    available = registry.names()
    records = []
    for index, (tool_name, language, prompt) in enumerate(TOOL_REPAIR_CASES):
        offered = select_tool_names(prompt, available)
        if tool_name not in offered:
            raise RouterDatasetError(
                f"router-v2-repair-tool-{index}: {tool_name} is not offered"
            )
        tool = registry.get(tool_name)
        assert tool is not None
        records.append(
            {
                "id": f"router2-repair-tool-{index:03d}",
                "seed_id": f"router2:repair:tool:{index}",
                "dataset_role": "router_v2_repair",
                "language": language,
                "domain": tool.category,
                "kind": "tool_call",
                "user": prompt,
                "tool": tool_name,
                "risk": tool.risk,
                "offered_tools": offered,
                "target": json.dumps(
                    {"tool": tool_name}, ensure_ascii=False, separators=(",", ":")
                ),
                "schema_version": TOOL_SCHEMA_VERSION,
                "router_protocol": ROUTER_PROTOCOL_VERSION,
            }
        )
    for index, (language, prompt, answer, category) in enumerate(ANSWER_REPAIR_CASES):
        records.append(
            {
                "id": f"router2-repair-answer-{index:03d}",
                "seed_id": f"router2:repair:answer:{index}",
                "dataset_role": "router_v2_repair",
                "language": language,
                "domain": category,
                "kind": "answer",
                "user": prompt,
                "tool": None,
                "risk": "read",
                "offered_tools": select_tool_names(prompt, available),
                "target": json.dumps(
                    {"answer": answer}, ensure_ascii=False, separators=(",", ":")
                ),
                "schema_version": TOOL_SCHEMA_VERSION,
                "router_protocol": ROUTER_PROTOCOL_VERSION,
            }
        )
    return records


def build_acceptance_v4_records(
    train: list[dict] | None = None,
    validation: list[dict] | None = None,
) -> list[dict]:
    """Build the sealed, never-training Router v2 release gate."""
    if train is None or validation is None:
        train, validation = build_records()
    registry = build_app_registry(object())
    available = registry.names()
    if [tool for tool, _language, _text in TOOL_CASES] != available:
        raise RouterDatasetError("Acceptance v4 must contain every tool once in registry order")

    records = []
    for index, (tool_name, language, prompt) in enumerate(TOOL_CASES):
        offered = select_tool_names(prompt, available)
        if tool_name not in offered:
            raise RouterDatasetError(
                f"acceptance-v4-tool-{index}: {tool_name} is not offered"
            )
        tool = registry.get(tool_name)
        assert tool is not None
        records.append(
            {
                "id": f"router2-acceptance-v4-tool-{index:03d}",
                "seed_id": f"router2-acceptance-v4:{tool_name}",
                "dataset_role": "router_v2_release_acceptance_test",
                "language": language,
                "domain": tool.category,
                "kind": "tool_call",
                "user": prompt,
                "tool": tool_name,
                "risk": tool.risk,
                "offered_tools": offered,
                "target": json.dumps(
                    {"tool": tool_name}, ensure_ascii=False, separators=(",", ":")
                ),
                "schema_version": TOOL_SCHEMA_VERSION,
                "router_protocol": ROUTER_PROTOCOL_VERSION,
            }
        )
    for index, (language, prompt, answer) in enumerate(ANSWER_CASES):
        records.append(
            {
                "id": f"router2-acceptance-v4-answer-{index:03d}",
                "seed_id": f"router2-acceptance-v4:answer:{index}",
                "dataset_role": "router_v2_release_acceptance_test",
                "language": language,
                "domain": "direct_answer",
                "kind": "answer",
                "user": prompt,
                "tool": None,
                "risk": "read",
                "offered_tools": select_tool_names(prompt, available),
                "target": json.dumps(
                    {"answer": answer}, ensure_ascii=False, separators=(",", ":")
                ),
                "schema_version": TOOL_SCHEMA_VERSION,
                "router_protocol": ROUTER_PROTOCOL_VERSION,
            }
        )
    validate_records(records)
    _audit_acceptance_disjoint(records, train, validation)
    return records


def _audit_acceptance_disjoint(
    acceptance: list[dict], train: list[dict], validation: list[dict]
) -> None:
    if len(acceptance) != 60:
        raise RouterDatasetError("Acceptance v4 must contain 48 tools and 12 answers")
    if Counter(record["language"] for record in acceptance) != {"en": 30, "th": 30}:
        raise RouterDatasetError("Acceptance v4 must be balanced 30 English / 30 Thai")
    acceptance_prompts = {
        " ".join(record["user"].casefold().split()) for record in acceptance
    }
    if len(acceptance_prompts) != len(acceptance):
        raise RouterDatasetError("Acceptance v4 contains duplicate prompts")

    prior_paths = (
        LEGACY_DIR / "acceptance_test_v1_consumed.jsonl",
        LEGACY_DIR / "final_acceptance_test.jsonl",
        LEGACY_DIR / "release_acceptance_v3.jsonl",
    )
    development_records = list(train) + list(validation)
    for path in prior_paths:
        development_records.extend(load_jsonl(path))
    development_prompts = {
        " ".join(record["user"].casefold().split())
        for record in development_records
    }
    overlap = acceptance_prompts & development_prompts
    if overlap:
        raise RouterDatasetError(
            f"Acceptance v4 prompt overlap: {sorted(overlap)[:3]}"
        )


def _audit(train: list[dict], validation: list[dict]) -> None:
    validate_records(train)
    validate_records(validation)
    train_seeds = {record["seed_id"] for record in train}
    validation_seeds = {record["seed_id"] for record in validation}
    overlap = train_seeds & validation_seeds
    if overlap:
        raise RouterDatasetError(
            f"Seed leakage across router v2 splits: {sorted(overlap)[:5]}"
        )
    normalized_prompts = [
        " ".join(record["user"].casefold().split())
        for record in train + validation
    ]
    duplicates = [
        prompt for prompt, count in Counter(normalized_prompts).items() if count > 1
    ]
    if duplicates:
        raise RouterDatasetError(f"Duplicate prompts in router v2 data: {duplicates[:3]}")

    registry = build_app_registry(object())
    available = registry.names()
    tool_records = [
        record for record in train + validation if record["kind"] == "tool_call"
    ]
    covered = {record["tool"] for record in tool_records}
    if covered != set(available):
        raise RouterDatasetError(
            f"Tool coverage mismatch: missing={sorted(set(available) - covered)}"
        )
    for record in tool_records:
        offered = select_tool_names(record["user"], available)
        if record["tool"] not in offered:
            raise RouterDatasetError(
                f"{record['id']}: target {record['tool']} is not offered"
            )
        if json.loads(record["target"]) != {"tool": record["tool"]}:
            raise RouterDatasetError(f"{record['id']}: target is not selection-only")


def _jsonl_bytes(records: Iterable[dict]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8")


def _manifest(
    train: list[dict], validation: list[dict], acceptance: list[dict]
) -> dict:
    train_bytes = _jsonl_bytes(train)
    validation_bytes = _jsonl_bytes(validation)
    acceptance_bytes = _jsonl_bytes(acceptance)
    return {
        "dataset_version": DATASET_VERSION,
        "router_protocol": ROUTER_PROTOCOL_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "source_sha256": _verify_sources(),
        "counts": {
            "train": len(train),
            "validation": len(validation),
            "train_tools": sum(r["kind"] == "tool_call" for r in train),
            "train_answers": sum(r["kind"] == "answer" for r in train),
            "validation_tools": sum(r["kind"] == "tool_call" for r in validation),
            "validation_answers": sum(r["kind"] == "answer" for r in validation),
            "acceptance_v4": len(acceptance),
        },
        "sha256": {
            "train": hashlib.sha256(train_bytes).hexdigest(),
            "validation": hashlib.sha256(validation_bytes).hexdigest(),
            "acceptance_v4": hashlib.sha256(acceptance_bytes).hexdigest(),
        },
    }


def build(*, check: bool = False) -> dict:
    train, validation = build_records()
    acceptance = build_acceptance_v4_records(train, validation)
    outputs = {
        DATA_DIR / "train.jsonl": _jsonl_bytes(train),
        DATA_DIR / "validation.jsonl": _jsonl_bytes(validation),
        DATA_DIR / "release_acceptance_v4.jsonl": _jsonl_bytes(acceptance),
    }
    manifest = _manifest(train, validation, acceptance)
    actual_acceptance_hash = manifest["sha256"]["acceptance_v4"]
    if (
        SEALED_ACCEPTANCE_V4_SHA256
        and actual_acceptance_hash != SEALED_ACCEPTANCE_V4_SHA256
    ):
        raise RouterDatasetError(
            "Sealed acceptance v4 changed: "
            f"expected {SEALED_ACCEPTANCE_V4_SHA256}, got {actual_acceptance_hash}"
        )
    outputs[DATA_DIR / "manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    if check:
        drift = [
            str(path)
            for path, expected in outputs.items()
            if not path.is_file() or path.read_bytes() != expected
        ]
        if drift:
            raise RouterDatasetError("Router v2 generated data drift: " + ", ".join(drift))
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for path, content in outputs.items():
            path.write_bytes(content)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(check=args.check), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
