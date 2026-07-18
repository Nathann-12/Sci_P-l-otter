from __future__ import annotations

import json
import threading

import numpy as np
import pandas as pd
import pytest

from core.analysis_recipe import (
    AnalysisRecipe,
    AnalysisRecipeEngine,
    AnalysisRecipeError,
    ExecutionCancelled,
    NodeExecutionError,
    OperationRegistrationError,
    OperationRegistry,
    ParameterValidationError,
    RecalculationMode,
    RecipeFormatError,
    RecipeInput,
    RecipeNode,
    RecipeOutput,
    RecipeValidationError,
    ResultValidationError,
    dataframe_checksum,
    summarize_result,
)


SCALE_SCHEMA = {
    "type": "object",
    "required": ["factor"],
    "properties": {"factor": {"type": "number", "minimum": 0}},
    "additionalProperties": False,
}


def _source_node(
    node_id="scale",
    *,
    factor=2,
    mode=RecalculationMode.AUTO,
    operation="scale",
):
    return RecipeNode(
        node_id=node_id,
        operation=operation,
        inputs=[RecipeInput.source("data", "book")],
        outputs=[RecipeOutput(kind="dataframe")],
        parameters={"factor": factor},
        recalculation_mode=mode,
    )


def _summary_node(mode=RecalculationMode.AUTO):
    return RecipeNode(
        node_id="summary",
        operation="summary",
        inputs=[RecipeInput.node("data", "scale")],
        outputs=[RecipeOutput(kind="mapping")],
        parameters={},
        recalculation_mode=mode,
    )


def _registry(log=None):
    registry = OperationRegistry()

    def scale(inputs, params, context):
        if log is not None:
            log.append(context.node_id)
        result = inputs["data"].copy()
        result["y"] = result["y"] * params["factor"]
        return result

    def summary(inputs, params, context):
        if log is not None:
            log.append(context.node_id)
        return {"mean": float(inputs["data"]["y"].mean()), "rows": len(inputs["data"])}

    registry.register("scale", scale, schema=SCALE_SCHEMA, version="2.1")
    registry.register(
        "summary",
        summary,
        schema={"type": "object", "additionalProperties": False},
    )
    return registry


def _engine(*, summary_mode=RecalculationMode.AUTO, log=None):
    recipe = AnalysisRecipe(
        recipe_id="workflow-1",
        name="Scale then summarize",
        nodes=[_summary_node(summary_mode), _source_node()],
        metadata={"owner": "lab"},
    )
    return AnalysisRecipeEngine(recipe, _registry(log))


def test_versioned_dataclasses_and_convenience_bindings_are_json_safe():
    source = RecipeInput.source("raw", "book-1")
    dependency = RecipeInput.node("clean", "clean-node", "table")
    output = RecipeOutput("table", "dataframe", "Clean table")
    node = RecipeNode(
        "clean-node",
        "clean",
        inputs=[source],
        outputs=[output],
        parameters={"columns": ("x", "y"), "threshold": np.int64(3)},
        recalculation_mode="Manual",
    )

    assert source.kind == "source"
    assert dependency.kind == "node"
    assert dependency.output == "table"
    assert node.mode is RecalculationMode.MANUAL
    assert node.parameters == {"columns": ["x", "y"], "threshold": 3}
    assert json.loads(json.dumps(node.to_dict(), allow_nan=False))["version"] == 1


def test_pipeline_executes_in_deterministic_topological_order_and_targets_closure():
    calls = []
    engine = _engine(log=calls)
    assert engine.topological_order == ("scale", "summary")
    source = pd.DataFrame({"y": [1.0, 2.0, 3.0]})
    engine.set_source("book", source, auto_run=False)

    report = engine.run("summary")

    assert report.ok
    assert report.executed == ("scale", "summary")
    assert calls == ["scale", "summary"]
    assert engine.get_result("summary") == {"mean": 4.0, "rows": 3}
    pd.testing.assert_frame_equal(source, pd.DataFrame({"y": [1.0, 2.0, 3.0]}))


def test_parallel_ready_nodes_keep_recipe_order():
    calls = []
    registry = OperationRegistry()
    registry.register("constant", lambda i, p, c: calls.append(c.node_id) or p["value"])
    recipe = AnalysisRecipe(
        "r",
        "Stable",
        nodes=[
            RecipeNode("z", "constant", parameters={"value": 1}),
            RecipeNode("a", "constant", parameters={"value": 2}),
        ],
    )
    engine = AnalysisRecipeEngine(recipe, registry)
    engine.run()
    assert engine.topological_order == ("z", "a")
    assert calls == ["z", "a"]


def test_source_checksum_covers_values_index_column_order_and_dtype():
    base = pd.DataFrame({"a": pd.Series([1, 2], dtype="int64"), "b": [3, 4]})
    assert dataframe_checksum(base) == dataframe_checksum(base.copy())
    changed = base.copy()
    changed.loc[0, "a"] = 9
    assert dataframe_checksum(base) != dataframe_checksum(changed)
    assert dataframe_checksum(base) != dataframe_checksum(base.set_index(pd.Index([2, 3])))
    assert dataframe_checksum(base) != dataframe_checksum(base[["b", "a"]])
    assert dataframe_checksum(base) != dataframe_checksum(base.astype({"a": "float64"}))
    with pytest.raises(TypeError, match="DataFrame"):
        dataframe_checksum([1, 2])


def test_setting_identical_source_does_not_recompute():
    calls = []
    engine = _engine(log=calls)
    data = pd.DataFrame({"y": [1, 2]})
    first = engine.set_source("book", data)
    assert first is not None and first.executed == ("scale", "summary")
    calls.clear()

    assert engine.set_source("book", data.copy()) is None
    assert calls == []


def test_setting_unreferenced_source_does_not_run_unrelated_dirty_graph():
    calls = []
    engine = _engine(log=calls)
    assert engine.set_source("unrelated", pd.DataFrame({"x": [1]})) is None
    assert calls == []
    assert engine.get_state("scale").dirty


def test_source_snapshot_and_returned_result_cannot_mutate_engine_state():
    engine = _engine()
    source = pd.DataFrame({"y": [1.0, 2.0]})
    engine.set_source("book", source)
    source.loc[0, "y"] = 999
    cached = engine.get_result("scale")
    assert cached["y"].tolist() == [2.0, 4.0]
    cached.loc[0, "y"] = -10
    assert engine.get_result("scale")["y"].tolist() == [2.0, 4.0]


def test_manual_mode_stays_dirty_on_auto_change_and_explicit_run_refreshes():
    engine = _engine(summary_mode="manual")
    engine.set_source("book", pd.DataFrame({"y": [1, 3]}))
    assert engine.get_state("scale").status == "clean"
    assert engine.get_state("summary").dirty

    engine.run("summary")
    assert engine.get_result("summary")["mean"] == 4.0
    engine.set_source("book", pd.DataFrame({"y": [2, 4]}))
    state = engine.get_state("summary")
    assert state.dirty and state.stale
    assert engine.get_result("summary")["mean"] == 4.0
    with pytest.raises(AnalysisRecipeError, match="stale"):
        engine.get_result("summary", require_fresh=True)

    report = engine.recalculate("summary")
    assert report.executed == ("summary",)
    assert engine.get_result("summary")["mean"] == 6.0


def test_parameter_change_propagates_dirty_and_auto_recalculates_auto_nodes():
    engine = _engine(summary_mode="manual")
    engine.set_source("book", pd.DataFrame({"y": [2, 4]}))
    engine.run("summary")
    report = engine.update_node_params("scale", {"factor": 3})
    assert report is not None
    assert report.executed == ("scale",)
    assert engine.get_result("scale")["y"].tolist() == [6, 12]
    assert engine.get_state("summary").dirty
    assert engine.update_node_params("scale", {"factor": 3}) is None


def test_frozen_node_retains_cache_and_blocks_stale_downstream_until_force():
    registry = _registry()
    recipe = AnalysisRecipe(
        "r-frozen",
        "Frozen seam",
        nodes=[
            _source_node(mode="frozen"),
            _summary_node(mode="auto"),
        ],
    )
    engine = AnalysisRecipeEngine(recipe, registry)
    engine.set_source("book", pd.DataFrame({"y": [1, 2]}), auto_run=False)
    assert engine.run(force=True).executed == ("scale", "summary")
    old = engine.get_result("summary")

    automatic = engine.set_source("book", pd.DataFrame({"y": [10, 20]}))
    assert automatic is not None
    assert automatic.skipped["scale"] == "frozen recalculation mode"
    assert "stale" in automatic.blocked["summary"]
    assert engine.get_result("summary") == old
    assert engine.run("summary").blocked["summary"].startswith("dependency")

    forced = engine.run("summary", force=True)
    assert forced.executed == ("scale", "summary")
    assert engine.get_result("summary")["mean"] == 30.0


def test_failed_recompute_keeps_last_good_result_and_marks_error():
    registry = OperationRegistry()

    def flaky(inputs, params, context):
        if params["fail"]:
            raise RuntimeError("instrument fit did not converge")
        return {"estimate": float(inputs["data"]["y"].mean())}

    registry.register(
        "flaky",
        flaky,
        schema={
            "type": "object",
            "required": ["fail"],
            "properties": {"fail": {"type": "boolean"}},
            "additionalProperties": False,
        },
    )
    recipe = AnalysisRecipe(
        "r-flaky",
        "Last good",
        nodes=[
            RecipeNode(
                "fit",
                "flaky",
                inputs=[RecipeInput.source("data", "book")],
                outputs=[RecipeOutput(kind="mapping")],
                parameters={"fail": False},
            )
        ],
    )
    engine = AnalysisRecipeEngine(recipe, registry)
    engine.set_source("book", pd.DataFrame({"y": [2.0, 4.0]}))
    good_provenance = engine.get_state("fit").last_success
    engine.update_node_params("fit", {"fail": True}, auto_run=False)

    report = engine.run()
    state = engine.get_state("fit")
    assert "RuntimeError" in report.failed["fit"]
    assert state.status == "error" and state.dirty and state.stale
    assert state.last_success == good_provenance
    assert state.last_attempt is not None and not state.last_attempt.success
    assert "did not converge" in state.error
    assert engine.get_result("fit") == {"estimate": 3.0}


def test_raise_on_error_occurs_only_after_state_is_safely_recorded():
    registry = OperationRegistry()
    registry.register("explode", lambda i, p, c: (_ for _ in ()).throw(ValueError("boom")))
    engine = AnalysisRecipeEngine(
        AnalysisRecipe("r", "Raise", nodes=[RecipeNode("bad", "explode")]), registry
    )
    with pytest.raises(NodeExecutionError, match="bad"):
        engine.run(raise_on_error=True)
    assert engine.get_state("bad").status == "error"
    assert engine.recipe.provenance[-1].error == "ValueError: boom"


def test_failed_dependency_blocks_descendant_without_destroying_its_cache():
    engine = _engine()
    engine.set_source("book", pd.DataFrame({"y": [1, 2]}))
    previous = engine.get_result("summary")
    engine.update_node_params("scale", {"factor": -1}, auto_run=False)
    report = engine.run()
    assert "scale" in report.failed
    assert "summary" in report.blocked
    assert engine.get_result("summary") == previous


def test_unknown_operation_and_invalid_parameters_fail_clearly_in_report():
    unknown = AnalysisRecipeEngine(
        AnalysisRecipe("r1", "Unknown", nodes=[RecipeNode("x", "not-installed")]),
        OperationRegistry(),
    )
    report = unknown.run()
    assert "UnknownOperationError" in report.failed["x"]

    invalid = AnalysisRecipeEngine(
        AnalysisRecipe("r2", "Invalid", nodes=[_source_node(factor=-2)]), _registry()
    )
    invalid.set_source("book", pd.DataFrame({"y": [1]}), auto_run=False)
    report = invalid.run()
    assert "ParameterValidationError" in report.failed["scale"]
    assert "must be >= 0" in report.failed["scale"]


def test_missing_dataframe_source_is_reported_as_blocked():
    engine = _engine()
    report = engine.run("summary")
    assert report.blocked["scale"] == "missing source 'book'"
    assert "no cached output" in report.blocked["summary"]


def test_cycle_missing_dependency_and_missing_output_rejected_at_boundary():
    with pytest.raises(RecipeValidationError, match="missing dependency"):
        AnalysisRecipe(
            "missing",
            "Missing",
            nodes=[
                RecipeNode(
                    "a", "op", inputs=[RecipeInput.node("data", "nowhere")]
                )
            ],
        )
    with pytest.raises(RecipeValidationError, match="missing output"):
        AnalysisRecipe(
            "missing-output",
            "Missing output",
            nodes=[
                RecipeNode("a", "op"),
                RecipeNode(
                    "b", "op", inputs=[RecipeInput.node("data", "a", "other")]
                ),
            ],
        )
    with pytest.raises(RecipeValidationError, match="cycle"):
        AnalysisRecipe(
            "cycle",
            "Cycle",
            nodes=[
                RecipeNode("a", "op", inputs=[RecipeInput.node("x", "b")]),
                RecipeNode("b", "op", inputs=[RecipeInput.node("x", "a")]),
            ],
        )


def test_duplicate_node_input_and_output_names_rejected():
    with pytest.raises(RecipeValidationError, match="duplicate input"):
        RecipeNode(
            "a",
            "op",
            inputs=[RecipeInput.source("x", "one"), RecipeInput.source("x", "two")],
        )
    with pytest.raises(RecipeValidationError, match="duplicate output"):
        RecipeNode(
            "a", "op", outputs=[RecipeOutput("x"), RecipeOutput("x")]
        )
    with pytest.raises(RecipeValidationError, match="duplicate node"):
        AnalysisRecipe(
            "r", "Duplicate", nodes=[RecipeNode("a", "op"), RecipeNode("a", "op")]
        )


def test_registry_supports_decorator_schema_custom_validator_and_introspection():
    registry = OperationRegistry()

    @registry.operation(
        "power",
        schema={
            "type": "object",
            "required": ["exponent"],
            "properties": {"exponent": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
        validator=lambda params: "exponent too large" if params["exponent"] > 4 else None,
    )
    def power(inputs, params, context):
        return params["exponent"] ** 2

    assert registry.names() == ("power",)
    assert registry.schema_for("power")["required"] == ["exponent"]
    registry.validate("power", {"exponent": 3})
    with pytest.raises(ParameterValidationError, match="integer"):
        registry.validate("power", {"exponent": 2.5})
    with pytest.raises(ParameterValidationError, match="too large"):
        registry.validate("power", {"exponent": 5})
    with pytest.raises(OperationRegistrationError, match="already registered"):
        registry.register("power", power)
    with pytest.raises(OperationRegistrationError, match="must accept"):
        registry.register("bad-signature", lambda only_one: only_one)


@pytest.mark.parametrize(
    "schema, message",
    [
        ({"type": "mystery"}, "must use"),
        ({"type": "object", "required": "x"}, "array of strings"),
        ({"type": "object", "properties": {"x": {"unknown": True}}}, "unsupported"),
        ({"type": "string", "pattern": "["}, "pattern is invalid"),
    ],
)
def test_malformed_operation_schema_is_rejected_during_registration(schema, message):
    with pytest.raises(OperationRegistrationError, match=message):
        OperationRegistry().register("op", lambda i, p, c: 1, schema=schema)


def test_multiple_outputs_can_feed_named_dependency_and_numpy_scalar_normalises():
    registry = OperationRegistry()
    registry.register(
        "split",
        lambda i, p, c: {
            "table": i["data"].assign(y=i["data"]["y"] + 1),
            "count": np.int64(len(i["data"])),
        },
    )
    registry.register("consume", lambda i, p, c: {"rows": i["n"]})
    recipe = AnalysisRecipe(
        "multi",
        "Multiple outputs",
        nodes=[
            RecipeNode(
                "split",
                "split",
                inputs=[RecipeInput.source("data", "book")],
                outputs=[
                    RecipeOutput("table", "dataframe"),
                    RecipeOutput("count", "scalar"),
                ],
            ),
            RecipeNode(
                "consume",
                "consume",
                inputs=[RecipeInput.node("n", "split", "count")],
                outputs=[RecipeOutput(kind="mapping")],
            ),
        ],
    )
    engine = AnalysisRecipeEngine(recipe, registry)
    engine.set_source("book", pd.DataFrame({"y": [1, 2, 3]}))
    assert engine.get_result("split", "count") == 3
    assert engine.get_result("consume") == {"rows": 3}


@pytest.mark.parametrize(
    "returned, message",
    [
        ([1, 2], "DataFrame, mapping, or scalar"),
        ({"x": float("nan")}, "non-finite"),
        ({1: "bad"}, "non-string"),
    ],
)
def test_invalid_results_do_not_enter_cache(returned, message):
    registry = OperationRegistry()
    registry.register("bad", lambda i, p, c: returned)
    engine = AnalysisRecipeEngine(
        AnalysisRecipe("r", "Bad", nodes=[RecipeNode("bad", "bad")]), registry
    )
    report = engine.run()
    assert "ResultValidationError" in report.failed["bad"]
    assert message in report.failed["bad"]
    assert not engine.get_state("bad").has_result


def test_multi_output_shape_and_declared_kind_are_enforced():
    registry = OperationRegistry()
    registry.register("wrong-keys", lambda i, p, c: {"a": 1})
    node = RecipeNode(
        "multi",
        "wrong-keys",
        outputs=[RecipeOutput("a"), RecipeOutput("b")],
    )
    engine = AnalysisRecipeEngine(AnalysisRecipe("r", "Wrong keys", nodes=[node]), registry)
    assert "missing b" in engine.run().failed["multi"]

    registry.register("wrong-kind", lambda i, p, c: {"x": 1})
    engine = AnalysisRecipeEngine(
        AnalysisRecipe(
            "r2",
            "Wrong kind",
            nodes=[RecipeNode("kind", "wrong-kind", outputs=[RecipeOutput(kind="dataframe")])],
        ),
        registry,
    )
    assert "expected dataframe" in engine.run().failed["kind"]


def test_cooperative_cancellation_stops_run_and_preserves_last_good_cache():
    checks = {"cancel": False}
    registry = OperationRegistry()

    def cancellable(inputs, params, context):
        if checks["cancel"]:
            context.raise_if_cancelled()
        return {"value": params["value"]}

    registry.register("cancellable", cancellable)
    recipe = AnalysisRecipe(
        "cancel",
        "Cancellation",
        nodes=[RecipeNode("work", "cancellable", parameters={"value": 1})],
    )
    engine = AnalysisRecipeEngine(recipe, registry)
    engine.run()
    engine.update_node_params("work", {"value": 2}, auto_run=False)
    checks["cancel"] = True

    report = engine.run(cancel_check=lambda: checks["cancel"])
    # Cancellation was observed before entering this node; it remains dirty and
    # the previous output is available.
    assert report.cancelled and report.executed == ()
    assert engine.get_result("work") == {"value": 1}


def test_executor_can_observe_cancellation_during_work():
    registry = OperationRegistry()
    event = threading.Event()

    def executor(inputs, params, context):
        event.set()
        context.raise_if_cancelled()
        return 1

    registry.register("work", executor)
    engine = AnalysisRecipeEngine(
        AnalysisRecipe("r", "Cancel inside", nodes=[RecipeNode("work", "work")]), registry
    )
    # Engine boundary check, pre-executor context check, then the executor's
    # cooperative check.
    calls = iter([False, False, True])
    report = engine.run(cancel_check=lambda: next(calls, True))
    assert event.is_set()
    assert report.cancelled
    state = engine.get_state("work")
    assert state.status == "cancelled" and state.dirty
    assert state.last_attempt is not None and not state.last_attempt.success


def test_threading_event_is_a_supported_cancellation_hook():
    event = threading.Event()
    event.set()
    engine = AnalysisRecipeEngine(
        AnalysisRecipe("r", "Event", nodes=[RecipeNode("x", "none")]),
        OperationRegistry(),
    )
    assert engine.run(cancel_check=event).cancelled


def test_dataframe_and_mapping_summaries_are_bounded_and_json_safe():
    frame = pd.DataFrame({f"c{i}": [i] for i in range(105)})
    summary = summarize_result(frame)
    assert summary["kind"] == "dataframe"
    assert summary["columns"] == 105
    assert len(summary["column_names"]) == 100
    assert summary["column_names_truncated"]
    assert summary["checksum"].startswith("sha256:")
    assert len(summary["checksum"]) == len("sha256:") + 64
    mapping = summarize_result({"estimate": np.float64(2.5), "when": pd.Timestamp("2024-01-01")})
    assert mapping["kind"] == "mapping"
    json.dumps(mapping, allow_nan=False)


def test_recipe_json_round_trip_includes_safe_provenance_but_not_full_results(tmp_path):
    engine = _engine()
    engine.set_source("book", pd.DataFrame({"y": [1, 2, 3]}))
    payload = engine.recipe.to_dict()
    encoded = engine.recipe.to_json()
    assert payload["format"] == "sciplotter_analysis_recipe"
    assert payload["provenance"][-1]["success"] is True
    assert "result_summary" in payload["provenance"][-1]
    assert "outputs" not in payload["provenance"][-1]
    assert "2.0,4.0,6.0" not in encoded

    restored = AnalysisRecipe.from_dict(payload)
    assert restored.to_dict() == payload
    path = tmp_path / "workflow.scirecipe"
    assert engine.save(path) == path
    loaded = AnalysisRecipe.load(path)
    assert loaded.to_dict() == payload
    # Result data is intentionally an in-memory cache and must be recalculated.
    loaded_engine = AnalysisRecipeEngine(loaded, _registry())
    assert loaded_engine.get_state("scale").dirty
    assert not loaded_engine.get_state("scale").has_result


def test_loaded_audit_restores_last_attempt_and_earlier_last_success_metadata():
    engine = _engine()
    engine.set_source("book", pd.DataFrame({"y": [1, 2]}))
    successful = engine.get_state("scale").last_success
    engine.update_node_params("scale", {"factor": -1}, auto_run=False)
    engine.run("scale")
    failed = engine.get_state("scale").last_attempt
    assert successful is not None and failed is not None and not failed.success

    restored = AnalysisRecipeEngine(
        AnalysisRecipe.from_json(engine.recipe.to_json()), _registry()
    ).get_state("scale")
    assert restored.last_success == successful
    assert restored.last_attempt == failed
    assert restored.result_summary == successful.result_summary
    assert not restored.has_result
    assert restored.status == "error" and restored.error == failed.error


@pytest.mark.parametrize(
    "mutator, expected",
    [
        (lambda data: data.update({"format": "other"}), "unsupported recipe format"),
        (lambda data: data.update({"version": 99}), "unsupported recipe version"),
        (lambda data: data.update({"unexpected": True}), "unknown field"),
        (lambda data: data.pop("nodes"), "missing required"),
        (lambda data: data.update({"nodes": {}}), "must be arrays"),
    ],
)
def test_strict_recipe_document_validation(mutator, expected):
    data = AnalysisRecipe("r", "Strict").to_dict()
    mutator(data)
    with pytest.raises(RecipeFormatError, match=expected):
        AnalysisRecipe.from_dict(data)


def test_strict_nested_validation_and_nonfinite_json_rejected():
    data = AnalysisRecipe("r", "Strict", nodes=[RecipeNode("x", "op")]).to_dict()
    data["nodes"][0]["surprise"] = 1
    with pytest.raises(RecipeFormatError, match="unknown field"):
        AnalysisRecipe.from_dict(data)
    with pytest.raises(RecipeFormatError, match="non-finite"):
        AnalysisRecipe.from_json('{"value": NaN}')
    with pytest.raises(RecipeValidationError, match="non-finite"):
        AnalysisRecipe("r", "Bad metadata", metadata={"value": float("inf")})

    nested_version = AnalysisRecipe(
        "r2", "Version", nodes=[RecipeNode("x", "op")]
    ).to_dict()
    nested_version["nodes"][0]["version"] = "1"
    with pytest.raises(RecipeFormatError, match="RecipeNode"):
        AnalysisRecipe.from_dict(nested_version)


def test_remove_source_marks_consumers_and_descendants_dirty():
    engine = _engine()
    engine.set_source("book", pd.DataFrame({"y": [1, 2]}))
    engine.remove_source("book")
    assert engine.get_state("scale").dirty
    assert engine.get_state("summary").dirty
    report = engine.run()
    assert "missing source" in report.blocked["scale"]


def test_mode_alias_and_state_snapshot_are_ui_ready_json():
    engine = _engine()
    engine.set_mode("summary", "Frozen")
    assert engine.recipe.node("summary").mode is RecalculationMode.FROZEN
    state = engine.get_state("summary")
    payload = state.to_dict()
    assert payload["node_id"] == "summary"
    assert payload["stale"] is False
    json.dumps(payload, allow_nan=False)


def test_disabled_node_is_skipped_and_blocks_uncached_consumer():
    recipe = AnalysisRecipe(
        "disabled",
        "Disabled",
        nodes=[replace_node_enabled(_source_node(), False), _summary_node()],
    )
    engine = AnalysisRecipeEngine(recipe, _registry())
    engine.set_source("book", pd.DataFrame({"y": [1]}), auto_run=False)
    report = engine.run()
    assert report.skipped["scale"] == "disabled"
    assert "no cached output" in report.blocked["summary"]


def replace_node_enabled(node, enabled):
    """Small local helper avoids importing dataclasses.replace in this test."""
    return RecipeNode(
        node_id=node.node_id,
        operation=node.operation,
        inputs=node.inputs,
        outputs=node.outputs,
        parameters=node.parameters,
        recalculation_mode=node.recalculation_mode,
        enabled=enabled,
        label=node.label,
    )


def test_get_result_errors_name_available_outputs():
    registry = OperationRegistry()
    registry.register("value", lambda i, p, c: 3)
    engine = AnalysisRecipeEngine(
        AnalysisRecipe("r", "Value", nodes=[RecipeNode("x", "value")]), registry
    )
    with pytest.raises(AnalysisRecipeError, match="available: none"):
        engine.get_result("x")
    engine.run()
    with pytest.raises(AnalysisRecipeError, match="available: result"):
        engine.get_result("x", "other")


def test_operation_input_schema_supports_arrays_bounds_enum_and_patterns():
    registry = OperationRegistry()
    registry.register(
        "rich",
        lambda i, p, c: 1,
        schema={
            "type": "object",
            "required": ["columns", "method"],
            "properties": {
                "columns": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "pattern": r"^[A-Z]"},
                },
                "method": {"type": "string", "enum": ["mean", "median"]},
            },
            "additionalProperties": False,
        },
    )
    registry.validate("rich", {"columns": ["Signal"], "method": "mean"})
    with pytest.raises(ParameterValidationError, match="at least"):
        registry.validate("rich", {"columns": [], "method": "mean"})
    with pytest.raises(ParameterValidationError, match="pattern"):
        registry.validate("rich", {"columns": ["signal"], "method": "mean"})
    with pytest.raises(ParameterValidationError, match="one of"):
        registry.validate("rich", {"columns": ["Signal"], "method": "mode"})


def test_public_reports_and_provenance_identify_sources_dependencies_and_operation_version():
    engine = _engine()
    source = pd.DataFrame({"y": [1, 2]})
    report = engine.set_source("book", source)
    assert report is not None and report.to_dict()["ok"]
    scale = engine.get_state("scale").last_success
    summary = engine.get_state("summary").last_success
    assert scale is not None and scale.operation_version == "2.1"
    assert scale.source_checksums == {"book": dataframe_checksum(source)}
    assert summary is not None
    assert summary.dependency_runs == {"scale": scale.run_id}
    assert summary.source_checksums == scale.source_checksums
    json.dumps(summary.to_dict(), allow_nan=False)


def test_engine_fork_copies_last_good_runtime_without_sharing_mutable_state():
    engine = _engine()
    source = pd.DataFrame({"y": [1.0, 2.0, 3.0]})
    engine.set_source("book", source)

    forked = engine.fork()
    pd.testing.assert_frame_equal(
        forked.get_result("scale"), engine.get_result("scale")
    )
    assert forked.get_result("summary") == engine.get_result("summary")
    assert forked.get_state("scale") == engine.get_state("scale")

    forked_result = forked.get_result("scale")
    forked_result.loc[0, "y"] = 999.0
    assert engine.get_result("scale").loc[0, "y"] == 2.0

    changed = source.copy()
    changed.loc[0, "y"] = 10.0
    forked.set_source("book", changed, auto_run=False)
    assert forked.get_state("scale").dirty
    assert not engine.get_state("scale").dirty
    assert engine.source_checksum("book") == dataframe_checksum(source)


def test_failed_fork_recomputation_keeps_original_and_fork_last_good_results():
    engine = _engine()
    engine.set_source("book", pd.DataFrame({"y": [1.0, 2.0]}))
    original = engine.get_result("scale")

    forked = engine.fork()
    forked.update_node_params("scale", {"factor": -1}, auto_run=False)
    report = forked.run("scale")
    assert not report.ok
    pd.testing.assert_frame_equal(forked.get_result("scale"), original)
    pd.testing.assert_frame_equal(engine.get_result("scale"), original)
    assert forked.get_state("scale").last_attempt.success is False
    assert engine.get_state("scale").last_attempt.success is True


def test_run_auto_does_not_force_dirty_manual_dependency():
    recipe = AnalysisRecipe(
        "mixed", "Mixed modes",
        nodes=[
            _source_node(mode=RecalculationMode.MANUAL),
            _summary_node(mode=RecalculationMode.AUTO),
        ],
    )
    engine = AnalysisRecipeEngine(recipe, _registry())
    engine.set_source("book", pd.DataFrame({"y": [1.0, 2.0]}), auto_run=False)
    report = engine.run_auto("summary")
    assert report.skipped["scale"] == "manual recalculation mode"
    assert "no cached output" in report.blocked["summary"]
