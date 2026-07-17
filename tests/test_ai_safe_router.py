from __future__ import annotations

import json

import pandas as pd

from ai.agent import LocalAssistant
from ai.app_tools import build_app_registry
from ai.tool_registry import ToolRegistry


class _Client:
    def __init__(self, tool_name: str, invented_arguments=None):
        self.replies = [
            json.dumps(
                {
                    "tool": tool_name,
                    "arguments": dict(invented_arguments or {}),
                }
            ),
            json.dumps({"answer": "done"}),
        ]

    def chat(self, _messages, *, format_json=False):
        assert format_json is True
        return self.replies.pop(0)


def _registry(columns):
    return ToolRegistry(context_provider=lambda: {"columns": list(columns)})


def test_argument_context_is_marshaled_through_the_registry_executor():
    calls = []
    registry = ToolRegistry(context_provider=lambda: {"columns": ["Time"]})
    registry.set_executor(
        lambda handler, arguments: calls.append(dict(arguments)) or handler(arguments)
    )

    assert registry.argument_context() == {"columns": ["Time"]}
    assert calls == [{}]


def test_app_registry_context_uses_the_active_books_real_columns():
    class _Window:
        def _resolve_active_dataframe(self):
            return pd.DataFrame({"Time (s)": [0.0], "Sample": ["A"]})

    context = build_app_registry(_Window()).argument_context()

    assert context["columns"] == ["Time (s)", "Sample"]
    assert context["numeric_columns"] == ["Time (s)"]
    assert "Linear" in context["parameter_values"]["fit_curve.model"]
    assert context["parameter_values"]["plot_chart.chart_type"]


def test_resolver_uses_real_column_and_enum_not_model_arguments():
    calls = []
    registry = _registry(["Time", "Voltage"])
    registry.add(
        "smooth_data",
        "smooth a column",
        {
            "method": {"type": "string", "enum": ["median", "gaussian"]},
            "column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "smoothed",
    )

    result = LocalAssistant(
        registry,
        _Client("smooth_data", {"column": "Invented", "method": "gaussian"}),
    ).ask("Smooth Voltage with median")

    assert calls == [{"method": "median", "column": "Voltage"}]
    assert result.trace[0][1] == calls[0]


def test_mutation_confirmation_receives_only_resolved_arguments():
    approvals = []
    calls = []
    registry = ToolRegistry(
        context_provider=lambda: {"columns": ["Signal"]},
        approval_callback=lambda tool, arguments: approvals.append(
            (tool.name, dict(arguments))
        ) or False,
    )
    registry.add(
        "smooth_data",
        "smooth a column",
        {"column": {"type": "string"}},
        lambda arguments: calls.append(arguments) or "smoothed",
    )

    result = LocalAssistant(
        registry,
        _Client("smooth_data", {"column": "Invented"}),
    ).ask("Smooth Signal")

    assert approvals == [("smooth_data", {"column": "Signal"})]
    assert calls == []
    assert "confirmation declined" in result.trace[0][2].casefold()


def test_resolver_never_copies_an_unstated_optional_number_from_model():
    calls = []
    registry = _registry(["Signal"])
    registry.add(
        "find_anomalies",
        "find anomalies",
        {
            "method": {"type": "string", "enum": ["zscore", "iqr"]},
            "threshold": {"type": "number"},
            "column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "checked",
    )

    LocalAssistant(
        registry,
        _Client("find_anomalies", {"threshold": 2.5, "column": "Fake"}),
    ).ask("Find anomalies in Signal using IQR")

    assert calls == [{"method": "iqr", "column": "Signal"}]


def test_unknown_quoted_column_asks_instead_of_running():
    calls = []
    registry = _registry(["Time", "Voltage"])
    registry.add(
        "smooth_data",
        "smooth a column",
        {"column": {"type": "string"}},
        lambda arguments: calls.append(arguments) or "smoothed",
    )

    result = LocalAssistant(registry, _Client("smooth_data")).ask(
        'Smooth column "Voltge"'
    )

    assert calls == []
    assert result.trace == []
    assert "not in the active Book" in result.answer
    assert "Voltage" in result.answer


def test_ambiguous_quoted_column_lists_real_candidates():
    calls = []
    registry = _registry(["Signal A", "Signal B"])
    registry.add(
        "smooth_data",
        "smooth a column",
        {"column": {"type": "string"}},
        lambda arguments: calls.append(arguments) or "smoothed",
    )

    result = LocalAssistant(registry, _Client("smooth_data")).ask(
        'Smooth "Signal"'
    )

    assert calls == []
    assert "Signal A" in result.answer and "Signal B" in result.answer
    assert "ambiguous" in result.answer


def test_overlapping_column_names_prefer_the_longest_exact_name():
    calls = []
    registry = _registry(["Signal", "Signal Raw"])
    registry.add(
        "smooth_data",
        "smooth a column",
        {"column": {"type": "string"}},
        lambda arguments: calls.append(arguments) or "smoothed",
    )

    LocalAssistant(registry, _Client("smooth_data")).ask("Smooth Signal Raw")

    assert calls == [{"column": "Signal Raw"}]


def test_required_sampling_rate_is_not_guessed_from_an_unrelated_request():
    calls = []
    registry = _registry(["Voltage"])
    registry.add(
        "filter_signal",
        "filter a signal",
        {
            "fs": {"type": "number", "required": True},
            "kind": {"type": "string", "enum": ["lowpass", "highpass"]},
            "cutoff": {"type": "number"},
            "column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "filtered",
    )

    result = LocalAssistant(registry, _Client("filter_signal", {"fs": 1000})).ask(
        "Lowpass filter Voltage"
    )

    assert calls == []
    assert "sampling rate" in result.answer


def test_labeled_numbers_are_extracted_without_model_help():
    calls = []
    registry = _registry(["Voltage"])
    registry.add(
        "filter_signal",
        "filter a signal",
        {
            "fs": {"type": "number", "required": True},
            "kind": {"type": "string", "enum": ["lowpass", "highpass"]},
            "cutoff": {"type": "number"},
            "column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "filtered",
    )

    LocalAssistant(registry, _Client("filter_signal")).ask(
        "Lowpass filter Voltage, sampling rate 1 kHz, cutoff 50 Hz"
    )

    assert calls == [
        {"fs": 1000.0, "kind": "lowpass", "cutoff": 50.0, "column": "Voltage"}
    ]


def test_thai_column_and_descending_direction_are_resolved():
    calls = []
    registry = _registry(["เวลา", "อุณหภูมิ"])
    registry.add(
        "sort_data",
        "sort data",
        {
            "column": {"type": "string", "required": True},
            "ascending": {"type": "boolean"},
        },
        lambda arguments: calls.append(arguments) or "sorted",
    )

    LocalAssistant(registry, _Client("sort_data")).ask(
        "เรียงคอลัมน์อุณหภูมิจากมากไปน้อย"
    )

    assert calls == [{"column": "อุณหภูมิ", "ascending": False}]


def test_y_vs_x_and_dynamic_fit_model_are_resolved_explicitly():
    calls = []
    registry = ToolRegistry(
        context_provider=lambda: {
            "columns": ["Time", "Voltage"],
            "parameter_values": {
                "fit_curve.model": ["Linear", "Gaussian"],
            },
        }
    )
    registry.add(
        "fit_curve",
        "fit a curve",
        {
            "model": {"type": "string", "required": True},
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "fitted",
    )

    LocalAssistant(registry, _Client("fit_curve")).ask(
        "Fit Voltage vs Time using Gaussian"
    )

    assert calls == [
        {"model": "Gaussian", "x_column": "Time", "y_column": "Voltage"}
    ]


def test_scientific_units_are_converted_to_the_schema_base_units():
    calls = []
    registry = _registry(["Voltage", "Current"])
    registry.add(
        "iv_conductivity",
        "calculate conductivity",
        {
            "length_m": {"type": "number", "required": True},
            "area_m2": {"type": "number", "required": True},
            "voltage_column": {"type": "string"},
            "current_column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "calculated",
    )

    LocalAssistant(registry, _Client("iv_conductivity")).ask(
        "Calculate conductivity from Voltage and Current, length 5 cm, area 2 mm2"
    )

    assert calls == [
        {
            "length_m": 0.05,
            "area_m2": 2e-6,
            "voltage_column": "Voltage",
            "current_column": "Current",
        }
    ]


def test_incompatible_scientific_unit_is_rejected_before_execution():
    calls = []
    registry = _registry(["Voltage", "Current"])
    registry.add(
        "iv_conductivity",
        "calculate conductivity",
        {
            "length_m": {"type": "number", "required": True},
            "area_m2": {"type": "number", "required": True},
            "voltage_column": {"type": "string"},
            "current_column": {"type": "string"},
        },
        lambda arguments: calls.append(arguments) or "calculated",
    )

    result = LocalAssistant(registry, _Client("iv_conductivity")).ask(
        "Calculate conductivity from Voltage and Current, length 5 kg, area 2 mm2"
    )

    assert calls == []
    assert "unsupported unit 'kg'" in result.answer
    assert "sample length" in result.answer


def test_missing_required_column_returns_thai_clarification():
    calls = []
    registry = _registry(["เวลา", "สัญญาณ"])
    registry.add(
        "sort_data",
        "sort data",
        {"column": {"type": "string", "required": True}},
        lambda arguments: calls.append(arguments) or "sorted",
    )

    result = LocalAssistant(registry, _Client("sort_data")).ask("ช่วยเรียงข้อมูล")

    assert calls == []
    assert "ยังไม่รันคำสั่ง" in result.answer
    assert "column" in result.answer
