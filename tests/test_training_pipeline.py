from __future__ import annotations

import hashlib
import json

import pytest

from ai.app_tools import build_app_registry
from ai.tool_catalog import TOOL_SCHEMA_VERSION, select_tool_names
from training.acceptance_cases import acceptance_seeds
from training.build_dataset import (
    CONSUMED_FINAL_ACCEPTANCE_V2_SHA256,
    SEALED_RELEASE_ACCEPTANCE_V3_SHA256,
    _jsonl_bytes,
    build_auxiliary_records,
    build_final_acceptance_records,
    build_release_acceptance_v3_records,
    build_records,
)
from training.common import (
    accumulation_group_size,
    load_jsonl,
    reject_acceptance_training,
    validate_records,
)
from training.evaluate_router import (
    has_complete_json_object,
    one_record_per_seed,
    score_prediction,
    summarize,
)
from training.hard_negative_cases import HARD_NEGATIVE_GROUPS, hard_negative_seeds
from training.router_v2.build_dataset import (
    ROUTER_PROTOCOL_VERSION,
    SEALED_ACCEPTANCE_V4_SHA256,
    _jsonl_bytes as router_v2_jsonl_bytes,
    build_acceptance_v4_records,
    build_records as build_router_v2_records,
)
from training.tool_cases import answer_seeds, tool_seeds


def test_curated_training_seeds_cover_every_app_tool_four_times():
    names = build_app_registry(object()).names()
    seeds = tool_seeds()
    assert {seed.tool for seed in seeds} == set(names)
    assert len(seeds) == len(names) * 4
    assert {seed.language for seed in seeds} == {"en", "th"}


def test_built_dataset_is_balanced_grouped_and_contract_valid():
    train, validation = build_records()
    records = train + validation
    validate_records(records)

    assert len(train) == 414
    assert len(validation) == 138
    assert sum(record["language"] == "en" for record in records) == 276
    assert sum(record["language"] == "th" for record in records) == 276
    assert len({record["tool"] for record in records if record["tool"]}) == 44
    assert {record["seed_id"] for record in train}.isdisjoint(
        {record["seed_id"] for record in validation}
    )
    assert all(record["schema_version"] == TOOL_SCHEMA_VERSION for record in records)


def test_compact_router_prioritises_specific_late_group_tools():
    names = build_app_registry(object()).names()
    assert "sort_data" in select_tool_names("Sort the data by time_s", names)
    assert "iv_conductivity" in select_tool_names(
        "หาการนำไฟฟ้าจาก V กับ I เมื่อทราบพื้นที่", names
    )
    # The word plot must not match merely because the product is named SciPlotter.
    assert "plot_columns" not in select_tool_names("In SciPlotter, say hello", names)


def test_evaluator_scores_exact_tool_arguments_and_strict_json():
    record = {
        "kind": "tool_call",
        "language": "en",
        "tool": "sort_data",
        "target": '{"tool":"sort_data","arguments":{"column":"time_s","ascending":true}}',
    }
    exact = score_prediction(record, record["target"])
    wrong = score_prediction(record, '{"tool":"sort_data","arguments":{"column":"time_s","ascending":false}}')
    noisy = score_prediction(record, "```json\n" + record["target"] + "\n```")

    assert exact["exact"] and exact["valid_protocol"]
    assert wrong["tool_correct"] and not wrong["arguments_correct"]
    assert not noisy["valid_protocol"]


def test_router_v2_dataset_is_selection_only_and_keeps_splits_disjoint():
    train, validation = build_router_v2_records()
    validate_records(train + validation)

    assert len(train) == 522
    assert len(validation) == 138
    assert sum(record["kind"] == "tool_call" for record in train) == 468
    assert sum(record["kind"] == "answer" for record in train) == 54
    assert {record["router_protocol"] for record in train + validation} == {
        ROUTER_PROTOCOL_VERSION
    }
    assert {record["seed_id"] for record in train}.isdisjoint(
        {record["seed_id"] for record in validation}
    )
    for record in train + validation:
        target = json.loads(record["target"])
        if record["kind"] == "tool_call":
            assert target == {"tool": record["tool"]}
        else:
            assert set(target) == {"answer"}


def test_router_v2_evaluator_rejects_legacy_argument_output():
    record = {
        "kind": "tool_call",
        "language": "th",
        "tool": "sort_data",
        "router_protocol": "2.0",
        "target": '{"tool":"sort_data"}',
    }

    exact = score_prediction(record, record["target"])
    legacy = score_prediction(
        record,
        '{"tool":"sort_data","arguments":{"column":"time_s"}}',
    )

    assert exact["exact"] and exact["valid_protocol"]
    assert legacy["tool_correct"]
    assert not legacy["valid_protocol"]
    assert not legacy["arguments_correct"]
    assert not legacy["exact"]


def test_router_v2_acceptance_v4_is_balanced_sealed_and_training_rejected():
    train, validation = build_router_v2_records()
    acceptance = build_acceptance_v4_records(train, validation)

    assert len(acceptance) == 56
    assert sum(record["kind"] == "tool_call" for record in acceptance) == 44
    assert sum(record["kind"] == "answer" for record in acceptance) == 12
    assert sum(record["language"] == "en" for record in acceptance) == 28
    assert sum(record["language"] == "th" for record in acceptance) == 28
    assert {record["tool"] for record in acceptance if record["tool"]} == set(
        build_app_registry(object()).names()
    )
    assert (
        hashlib.sha256(router_v2_jsonl_bytes(acceptance)).hexdigest()
        == SEALED_ACCEPTANCE_V4_SHA256
    )
    with pytest.raises(ValueError, match="evaluation-only"):
        reject_acceptance_training(acceptance)


def test_evaluator_summary_reports_language_and_failures():
    base = {
        "kind": "tool_call",
        "tool": "list_columns",
        "target": '{"tool":"list_columns","arguments":{}}',
    }
    scored = []
    for language, prediction in (
        ("en", base["target"]),
        ("th", '{"answer":"ไม่ทราบ"}'),
    ):
        record = {**base, "language": language}
        scored.append({"record": record, "score": score_prediction(record, prediction)})
    report = summarize(scored)
    assert report["exact"] == 0.5
    assert report["per_language"]["en"]["exact"] == 1.0
    assert report["tool_call_count"] == 2
    assert report["tool_correct"] == 0.5
    assert report["answer_count"] == 0
    assert report["answer_exact"] is None
    assert report["failures_by_target"] == {"list_columns": 1}


def test_gradient_accumulation_scales_the_partial_group_per_epoch():
    sizes = [accumulation_group_size(index, 141, 16) for index in range(1, 142)]
    assert sizes[:16] == [16] * 16
    assert sizes[128:141] == [13] * 13
    updates = [index for index in range(1, 142) if index % 16 == 0 or index == 141]
    assert len(updates) == 9


def test_evaluator_can_measure_one_wrapper_per_semantic_seed():
    records = [
        {"id": "a0", "seed_id": "a"},
        {"id": "a1", "seed_id": "a"},
        {"id": "b0", "seed_id": "b"},
    ]
    assert [record["id"] for record in one_record_per_seed(records)] == ["a0", "b0"]


def test_thai_hard_negatives_cover_all_14_failure_groups_in_pairs():
    seeds = hard_negative_seeds()
    assert len(HARD_NEGATIVE_GROUPS) == 14
    assert len(seeds) == 56
    assert {seed.language for seed in seeds} == {"th"}
    assert all(sum(item.group == group for item in seeds) == 4 for group in HARD_NEGATIVE_GROUPS)


def test_repair_and_acceptance_sets_are_contract_valid_and_disjoint():
    train, validation = build_records()
    repair, acceptance = build_auxiliary_records(train, validation)
    validate_records(repair + validation)
    validate_records(acceptance)

    assert len(repair) == 118  # one replay per tool, all 18 answers and 56 repairs
    assert len({
        record["seed_id"]
        for record in repair
        if record["dataset_role"] == "answer_replay"
    }) == 18
    assert len(acceptance) == 28
    assert len({seed.group for seed in acceptance_seeds()}) == 14
    assert {record["language"] for record in acceptance} == {"th"}
    assert {record["dataset_role"] for record in acceptance} == {"acceptance_test"}

    training_prompts = {record["user"].casefold() for record in train + validation + repair}
    acceptance_prompts = {record["user"].casefold() for record in acceptance}
    assert training_prompts.isdisjoint(acceptance_prompts)
    assert {record["seed_id"] for record in repair}.isdisjoint(
        {record["seed_id"] for record in acceptance}
    )


def test_training_loop_rejects_acceptance_records():
    _, acceptance = build_auxiliary_records(*build_records())
    with pytest.raises(ValueError, match="evaluation-only"):
        reject_acceptance_training(acceptance)


def test_fresh_final_acceptance_is_balanced_sealed_and_training_rejected():
    train, validation = build_records()
    repair, consumed = build_auxiliary_records(train, validation)
    final = build_final_acceptance_records(train, validation, repair, consumed)

    assert len(final) == 26
    assert sum(record["kind"] == "tool_call" for record in final) == 14
    assert sum(record["kind"] == "answer" for record in final) == 12
    assert sum(record["language"] == "en" for record in final) == 13
    assert sum(record["language"] == "th" for record in final) == 13
    assert {record["dataset_role"] for record in final} == {"final_acceptance_test"}
    assert hashlib.sha256(_jsonl_bytes(final)).hexdigest() == CONSUMED_FINAL_ACCEPTANCE_V2_SHA256
    with pytest.raises(ValueError, match="evaluation-only"):
        reject_acceptance_training(final)


def test_release_acceptance_v3_covers_every_tool_and_is_training_rejected():
    train, validation = build_records()
    repair, consumed = build_auxiliary_records(train, validation)
    final = build_final_acceptance_records(train, validation, repair, consumed)
    release = build_release_acceptance_v3_records(
        train, validation, repair, consumed, final
    )
    validate_records(release)

    assert len(release) == 56
    assert sum(record["kind"] == "tool_call" for record in release) == 44
    assert sum(record["kind"] == "answer" for record in release) == 12
    assert sum(record["language"] == "en" for record in release) == 28
    assert sum(record["language"] == "th" for record in release) == 28
    assert {record["tool"] for record in release if record["tool"]} == set(
        build_app_registry(object()).names()
    )
    assert {record["dataset_role"] for record in release} == {
        "release_acceptance_test"
    }
    assert (
        hashlib.sha256(_jsonl_bytes(release)).hexdigest()
        == SEALED_RELEASE_ACCEPTANCE_V3_SHA256
    )
    with pytest.raises(ValueError, match="evaluation-only"):
        reject_acceptance_training(release)


def test_json_stopper_waits_for_nested_object_and_escaped_text():
    assert not has_complete_json_object('{"tool":"x","arguments":{"a":1}')
    assert has_complete_json_object('{"tool":"x","arguments":{"a":1}}')
    assert has_complete_json_object('{"answer":"brace } and quote \\\" are text"}')
