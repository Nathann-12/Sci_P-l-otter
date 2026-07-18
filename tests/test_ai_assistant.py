"""Behavioural tests for the local AI assistant (no network / no model)."""
from __future__ import annotations

import json
import threading
import time

import pandas as pd
import pytest
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication

from ai.agent import LocalAssistant, _parse_reply
from ai.app_tools import build_app_registry
from ai.command_router import route_command
from ai.tool_registry import ToolRegistry


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class ScriptedClient:
    """Fake chat client returning pre-scripted JSON replies in order."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def chat(self, messages, *, format_json=False):
        self.calls.append((messages, format_json))
        return self._replies.pop(0)


class BoomClient:
    def chat(self, *args, **kwargs):
        raise RuntimeError("no server")


def _basic_registry():
    reg = ToolRegistry()
    reg.add("list_columns", "list", {}, lambda a: "columns: time, voltage")
    reg.add("plot_columns", "plot", {"style": {"type": "string"}},
            lambda a: f"plotted {a.get('style', 'line')}")
    return reg


# --------------------------------------------------------------------- registry
def test_registry_specs_and_execute():
    reg = _basic_registry()
    assert reg.names() == ["list_columns", "plot_columns"]
    specs = reg.specs()
    assert {s["name"] for s in specs} == {"list_columns", "plot_columns"}
    assert reg.execute("plot_columns", {"style": "scatter"}) == "plotted scatter"


def test_registry_unknown_tool_is_recoverable_text():
    reg = _basic_registry()
    out = reg.execute("nope", {})
    assert "unknown tool" in out.lower()
    assert "list_columns" in out  # lists what IS available


def test_registry_tool_error_becomes_observation():
    reg = ToolRegistry()
    reg.add("boom", "x", {}, lambda a: 1 / 0)
    out = reg.execute("boom", {})
    assert out.lower().startswith("error running 'boom'")


# ------------------------------------------------------------------------ agent
def test_agent_runs_multi_step_tool_loop():
    reg = _basic_registry()
    client = ScriptedClient([
        json.dumps({"tool": "list_columns", "arguments": {}}),
        json.dumps({"tool": "plot_columns", "arguments": {"style": "scatter"}}),
        json.dumps({"answer": "done"}),
    ])
    result = LocalAssistant(reg, client, max_steps=5).ask("make a scatter")
    assert result.answer == "done"
    assert [t[0] for t in result.trace] == ["list_columns", "plot_columns"]
    assert result.steps == 3
    # tool calls must request JSON-forced output for small-model reliability
    assert all(format_json for _msgs, format_json in client.calls)


def test_agent_reports_each_tool_as_it_starts():
    registry = _basic_registry()
    client = ScriptedClient([
        json.dumps({"tool": "list_columns", "arguments": {}}),
        json.dumps({"answer": "done"}),
    ])
    started = []

    LocalAssistant(registry, client).ask(
        "inspect this data",
        on_tool_start=lambda name, arguments: started.append((name, arguments)),
    )

    assert started == [("list_columns", {})]


def test_agent_recovers_from_unknown_tool():
    reg = _basic_registry()
    client = ScriptedClient([
        json.dumps({"tool": "does_not_exist", "arguments": {}}),
        json.dumps({"answer": "recovered"}),
    ])
    result = LocalAssistant(reg, client).ask("x")
    assert result.answer == "recovered"
    assert "unknown tool" in result.trace[0][2].lower()


def test_agent_treats_plain_text_as_answer():
    result = LocalAssistant(_basic_registry(), ScriptedClient(["just text"])) .ask("hi")
    assert result.answer == "just text"


def test_agent_respects_step_limit():
    reg = _basic_registry()
    replies = [json.dumps({"tool": "list_columns", "arguments": {}})] * 6
    result = LocalAssistant(reg, ScriptedClient(replies), max_steps=3).ask("loop")
    assert result.steps == 3
    assert "step limit" in result.answer.lower()


def test_agent_handles_client_failure_gracefully():
    result = LocalAssistant(_basic_registry(), BoomClient()).ask("hi")
    assert "unavailable" in result.answer.lower()
    assert result.error == "no server"


def test_agent_never_starts_model_selected_tool_after_cancellation():
    cancelled = []
    tool_calls = []
    registry = ToolRegistry()
    registry.add(
        "list_columns",
        "list",
        {},
        lambda _arguments: tool_calls.append(True) or "columns",
    )

    class _CancellingClient:
        def chat(self, _messages, **_kwargs):
            cancelled.append(True)
            return json.dumps({"tool": "list_columns"})

    result = LocalAssistant(registry, _CancellingClient()).ask(
        "please help with this dataset",
        cancelled=lambda: bool(cancelled),
    )

    assert result.cancelled is True
    assert tool_calls == []
    assert result.trace == []


@pytest.mark.parametrize("cancel_stage", ("approval", "executor"))
def test_cancellation_guard_closes_approval_and_gui_execution_race(cancel_stage):
    cancelled = []
    mutations = []

    def approval(_tool, _arguments):
        if cancel_stage == "approval":
            cancelled.append(True)
        return True

    def executor(handler, arguments):
        if cancel_stage == "executor":
            cancelled.append(True)
        return handler(arguments)

    registry = ToolRegistry(
        executor=executor,
        approval_callback=approval,
    )
    registry.add(
        "mutate_fixture",
        "mutate fixture",
        {},
        lambda _arguments: mutations.append(True) or "changed",
        risk="mutate",
    )
    client = ScriptedClient([json.dumps({"tool": "mutate_fixture"})])

    result = LocalAssistant(registry, client).ask(
        "perform the requested fixture action",
        cancelled=lambda: bool(cancelled),
    )

    assert result.cancelled is True
    assert mutations == []


def test_cancellation_during_started_tool_never_restarts_model_loop():
    cancelled = []
    registry = ToolRegistry()

    def handler(_arguments):
        cancelled.append(True)
        return "completed before cancellation was observed"

    registry.add("slow_fixture", "slow fixture", {}, handler)
    client = ScriptedClient(
        [
            json.dumps({"tool": "slow_fixture"}),
            json.dumps({"answer": "must not be requested"}),
        ]
    )

    result = LocalAssistant(registry, client).ask(
        "perform the slow fixture action",
        cancelled=lambda: bool(cancelled),
    )

    assert result.cancelled is True
    assert len(client.calls) == 1
    assert result.trace == [
        ("slow_fixture", {}, "completed before cancellation was observed")
    ]


def test_parse_reply_extracts_json_from_noise():
    assert _parse_reply('```json\n{"answer": "hi"}\n```') == {"answer": "hi"}
    assert _parse_reply("") == {"answer": ""}
    assert _parse_reply("plain") == {"answer": "plain"}


def test_plot_command_fast_path_does_not_depend_on_the_model():
    calls = []
    registry = ToolRegistry()
    registry.add(
        "plot_columns",
        "plot",
        {},
        lambda arguments: calls.append(arguments) or "Created a scatter graph.",
    )

    result = LocalAssistant(registry, BoomClient()).ask(
        "plot voltage vs time as scatter"
    )

    assert result.answer == "Created a scatter graph."
    assert result.trace[0][0] == "plot_columns"
    assert result.trace[0][1]["style"] == "scatter"
    assert calls and calls[0]["instruction"] == "plot voltage vs time as scatter"


def test_plot_command_router_supports_thai_and_avoids_advice_questions():
    routed = route_command("พล็อต voltage เทียบ time แบบจุด")
    assert routed is not None
    assert routed[0] == "plot_columns"
    assert routed[1]["style"] == "scatter"
    assert route_command("อธิบายว่ากราฟ scatter เหมาะกับอะไร") is None
    assert route_command("How do I plot voltage against time?") is None
    assert route_command("Don't plot voltage; just describe it") is None
    assert route_command("Do not create a graph yet") is None
    assert route_command("อย่าพล็อต voltage ตอนนี้") is None


def test_analyze_and_columns_commands_use_direct_data_tools():
    analyze = route_command("วิเคราะห์")
    columns = route_command("มีคอลัมน์อะไรบ้าง")
    peaks = route_command("หาพีค")

    assert analyze == (
        "summarize_data",
        {"language": "th", "instruction": "วิเคราะห์"},
    )
    assert columns == ("list_columns", {"language": "th"})
    assert peaks == ("detect_peaks", {"language": "th", "auto": True})


# ------------------------------------------------------------------- app tools
class _FakeWindow:
    def __init__(self, df):
        self._df = df
        self.plotted = []
        self.added = []
        self.result_books = []
        self.charts = []

    def _resolve_active_dataframe(self):
        return self._df

    def _active_book_label(self):
        return "Book1"

    def plot_from_workbook(self, style="line", new_graph=True):
        self.plotted.append((style, new_graph))

    def smooth_column(self, col, method="savitzky-golay", **kwargs):
        self.smoothed = (col, method, kwargs)
        return f"{col}_sm"

    def filter_column_butterworth(self, col, fs, kind="lowpass", cutoff=None):
        self.filtered = (col, fs, kind, cutoff)
        return f"{col}_{kind}"

    def add_y_column_option(self, name):
        self.added.append(name)

    def _swap_dataframe(self, new_df):
        self._df = new_df

    def selected_x_column(self):
        return ""

    def _open_signal_result_book(self, name, df):
        self.result_books.append((name, df))
        return name

    def _dataset_names(self, include_active=True):
        return ["Book1", "Book2"]

    def active_axes(self):
        if getattr(self, "_ax", None) is None:
            # Build a standalone figure WITHOUT pyplot or ``matplotlib.use``.
            # Calling ``matplotlib.use("Agg")`` here permanently switched the
            # global backend from ``qtagg`` to ``Agg`` on the first format_graph
            # test, and every later test that built a real Qt canvas then ran
            # under a mismatched backend and segfaulted the offscreen suite.
            from matplotlib.figure import Figure

            self._fig = Figure()
            self._ax = self._fig.add_subplot(111)
        return self._ax

    def plot_from_gallery(self, entry):
        self.charts.append(entry.get("key"))


class _ExplicitPlotWindow(_FakeWindow):
    def __init__(self, df):
        super().__init__(df)
        self.explicit_plots = []

    def plot_explicit_columns(
        self, style, x_column, y_columns, *, new_graph=True
    ):
        self.explicit_plots.append((style, x_column, list(y_columns), new_graph))
        return {"graph_id": "graph_1", "artists_added": len(y_columns)}


def test_app_tools_read_and_drive_the_window():
    df = pd.DataFrame({"time": [1, 2, 3], "voltage": [0.1, 0.2, 0.3]})
    window = _FakeWindow(df)
    reg = build_app_registry(window)

    cols = reg.execute("list_columns", {})
    assert "time" in cols and "voltage" in cols and "3 rows" in cols

    stats = reg.execute("describe_data", {})
    assert "voltage" in stats

    plotted = reg.execute("plot_columns", {"style": "scatter"})
    assert window.plotted == [("scatter", True)]
    assert "scatter" in plotted

    assert "Book1" in reg.execute("active_book", {})


def test_app_tools_handle_no_active_data():
    reg = build_app_registry(_FakeWindow(None))
    assert "no active data" in reg.execute("list_columns", {}).lower()


def test_app_tools_reject_unknown_plot_style():
    df = pd.DataFrame({"a": [1, 2]})
    reg = build_app_registry(_FakeWindow(df))
    out = reg.execute("plot_columns", {"style": "bogus"})
    assert "unknown style" in out.lower()


def test_plot_tool_maps_named_columns_from_plain_language():
    window = _ExplicitPlotWindow(
        pd.DataFrame(
            {
                "time": [0, 1, 2],
                "voltage": [1.0, 3.0, 2.0],
                "current": [0.2, 0.4, 0.1],
            }
        )
    )

    out = build_app_registry(window).execute(
        "plot_columns",
        {"style": "scatter", "instruction": "plot voltage vs time as scatter"},
    )

    assert window.explicit_plots == [("scatter", "time", ["voltage"], True)]
    assert "voltage vs time" in out


def test_plot_tool_defaults_to_time_and_all_numeric_y_columns():
    window = _ExplicitPlotWindow(
        pd.DataFrame(
            {
                "time_s": [0, 1, 2],
                "voltage": [1.0, 3.0, 2.0],
                "current": [0.2, 0.4, 0.1],
            }
        )
    )

    build_app_registry(window).execute("plot_columns", {"style": "line"})

    assert window.explicit_plots == [
        ("line", "time_s", ["voltage", "current"], True)
    ]


def test_plot_tool_accepts_case_insensitive_explicit_columns():
    window = _ExplicitPlotWindow(
        pd.DataFrame({"Elapsed Time": [0, 1], "Signal": [2.0, 5.0]})
    )

    out = build_app_registry(window).execute(
        "plot_columns",
        {"style": "line+symbol", "x_column": "elapsed time", "y_columns": ["SIGNAL"]},
    )

    assert window.explicit_plots == [
        ("linesymbol", "Elapsed Time", ["Signal"], True)
    ]
    assert "line + symbol" in out


def test_plot_tool_reports_missing_column_instead_of_claiming_success():
    window = _ExplicitPlotWindow(pd.DataFrame({"time": [0, 1], "signal": [2, 3]}))

    out = build_app_registry(window).execute(
        "plot_columns", {"x_column": "missing", "y_columns": ["signal"]}
    )

    assert "was not found" in out
    assert "time, signal" in out
    assert window.explicit_plots == []


def test_summary_tool_analyzes_xrd_like_data_and_reports_real_peaks():
    import numpy as np

    theta = np.linspace(10.0, 80.0, 1401)
    intensity = (
        120.0
        + 900.0 * np.exp(-0.5 * ((theta - 38.2) / 0.28) ** 2)
        + 520.0 * np.exp(-0.5 * ((theta - 44.4) / 0.35) ** 2)
    )
    window = _FakeWindow(pd.DataFrame({"2-Theta": theta, "Intensity": intensity}))

    out = build_app_registry(window).execute(
        "summarize_data", {"language": "th"}
    )

    assert "1,401 แถว" in out
    assert "จุดสูงสุด" in out and "38.2" in out
    assert "พีคเด่น" in out
    assert "XRD" in out and "ฐานข้อมูลอ้างอิง" in out


def test_summary_tool_ignores_infinite_values_and_compacts_wide_tables():
    import numpy as np

    data = {"time": [0.0, 1.0, 2.0]}
    data.update(
        {
            f"extra_{index}": [index, index + 1, index + 2]
            for index in range(8)
        }
    )
    data["signal"] = [1.0, np.inf, 3.0]

    out = build_app_registry(_FakeWindow(pd.DataFrame(data))).execute(
        "summarize_data", {"language": "en"}
    )

    assert "+2 more" in out
    assert "Maximum signal: 3 at time = 2" in out
    assert "inf" not in out.casefold()


def test_bare_thai_analyze_command_never_calls_model_or_refuses():
    window = _FakeWindow(
        pd.DataFrame({"time": [0, 1, 2, 3], "signal": [1.0, 4.0, 2.0, 5.0]})
    )

    result = LocalAssistant(build_app_registry(window), BoomClient()).ask("วิเคราะห์")

    assert result.trace[0][0] == "summarize_data"
    assert "4 แถว" in result.answer
    assert "signal" in result.answer
    assert "ขอโทษ" not in result.answer


def test_bare_thai_find_peaks_uses_adaptive_tool_and_opens_result_book():
    import numpy as np

    x = np.linspace(0, 20, 401)
    y = np.exp(-0.5 * ((x - 7.0) / 0.25) ** 2)
    window = _FakeWindow(pd.DataFrame({"x": x, "intensity": y}))

    result = LocalAssistant(build_app_registry(window), BoomClient()).ask("หาพีค")

    assert result.trace[0][0] == "detect_peaks"
    assert "พบ" in result.answer and "พีค" in result.answer
    assert window.result_books and window.result_books[0][0] == "Peaks_intensity"


def test_app_tools_list_fit_models():
    reg = build_app_registry(_FakeWindow(pd.DataFrame({"a": [1, 2, 3]})))
    out = reg.execute("list_fit_models", {})
    assert "linear" in out.lower()


def test_app_tools_fit_curve_returns_params_and_r2():
    # perfect line y = 2x + 1 -> linear fit, R^2 = 1
    df = pd.DataFrame({"x": [0, 1, 2, 3, 4], "y": [1, 3, 5, 7, 9]})
    reg = build_app_registry(_FakeWindow(df))
    out = reg.execute("fit_curve", {"model": "linear"})
    assert "R^2 = 1.0" in out
    assert "linear" in out.lower()


def test_app_tools_fit_curve_supports_uncertainty_weighting_and_metrics():
    import numpy as np

    x = np.arange(6.0)
    y = 2.0 * x + 1.0
    y[-1] = 30.0
    df = pd.DataFrame(
        {
            "x": x,
            "y": y,
            "uncertainty": [0.1, 0.1, 0.1, 0.1, 0.1, 100.0],
        }
    )
    reg = build_app_registry(_FakeWindow(df))

    out = reg.execute(
        "fit_curve",
        {
            "model": "linear",
            "x_column": "x",
            "y_column": "y",
            "weight_column": "uncertainty",
            "weighting": "sigma",
        },
    )

    assert "Weighted fit 'linear'" in out
    assert "m=2" in out
    assert "chi^2_red" in out
    assert "95% CI available" in out


def test_app_tools_fit_curve_needs_two_numeric_columns():
    reg = build_app_registry(_FakeWindow(pd.DataFrame({"only": [1, 2, 3]})))
    out = reg.execute("fit_curve", {"model": "linear"})
    assert "two numeric columns" in out.lower()


def test_app_tools_gas_live_control_is_non_modal_and_reports_actions():
    class GasWindow(_FakeWindow):
        def __init__(self):
            super().__init__(pd.DataFrame({"x": [1.0]}))
            self.live_calls = []

        def gs_live_status(self):
            return {
                "connected": True,
                "port": "COM7",
                "baud": 115200,
                "samples": 25,
                "sample_rate_hz": 10.0,
                "parse_errors": 1,
                "book": "Live Gas Test",
            }

        def gs_live_connect(self, port, baud):
            self.live_calls.append(("connect", port, baud))
            return True, f"Connected to {port} @ {baud}"

        def gs_live_disconnect(self):
            self.live_calls.append(("disconnect",))
            return True, "Disconnected by user"

        def gs_live_mark(self, state, label=""):
            self.live_calls.append(("mark", state, label))
            return True, f"Marked gas {state.upper()}"

    window = GasWindow()
    reg = build_app_registry(window)

    assert "25" in reg.execute("gas_live_control", {"action": "status"})
    assert "Connected" in reg.execute(
        "gas_live_control", {"action": "connect", "port": "COM7", "baud": 115200}
    )
    assert "Marked gas ON" in reg.execute(
        "gas_live_control", {"action": "mark_on", "label": "ethanol"}
    )
    assert "Disconnected" in reg.execute("gas_live_control", {"action": "disconnect"})
    assert window.live_calls == [
        ("connect", "COM7", 115200),
        ("mark", "on", "ethanol"),
        ("disconnect",),
    ]


def test_app_tools_gas_live_control_supports_ni_daq_without_modal():
    class DaqWindow(_FakeWindow):
        def __init__(self):
            super().__init__(pd.DataFrame({"x": [1.0]}))
            self.daq_calls = []

        def gs_live_status(self):
            return {
                "transport": "ni_daq",
                "connected": True,
                "device": "Dev1",
                "channels": ["Dev1/ai0"],
                "configured_rate_hz": 20.0,
                "sample_rate_hz": 19.8,
                "samples": 100,
                "acquisition_errors": 0,
                "book": "Live Gas DAQ",
            }

        def gs_live_connect_daq(self, *args):
            self.daq_calls.append(args)
            return True, "Connected to Dev1"

    window = DaqWindow()
    reg = build_app_registry(window)
    status = reg.execute("gas_live_control", {"action": "status"})
    assert "transport=ni_daq" in status and "Dev1/ai0" in status and "100" in status
    result = reg.execute("gas_live_control", {
        "action": "connect",
        "transport": "ni_daq",
        "device": "Dev1",
        "channel": "Dev1/ai0",
        "sample_rate_hz": 20,
        "min_voltage": -10,
        "max_voltage": 10,
        "terminal_config": "DIFFERENTIAL",
    })
    assert result == "Connected to Dev1"
    assert window.daq_calls == [
        ("Dev1", "Dev1/ai0", 20.0, -10.0, 10.0, "DIFFERENTIAL")
    ]


def test_app_tools_gas_live_control_configures_visual_flow_non_modally():
    class FlowWindow(_FakeWindow):
        def __init__(self):
            super().__init__(pd.DataFrame({"x": [1.0]}))
            self.flow_updates = []

        def gs_live_flow_status(self):
            return {
                "running": False,
                "summary": "input → voltage_to_resistance → live_book → rolling_graph",
                "wiring": [["source", "divider"], ["divider", "book"], ["book", "graph"]],
            }

        def gs_live_configure_flow(self, config=None, **updates):
            self.flow_updates.append((config, updates))
            return True, "input → voltage_to_resistance → moving_average → live_book"

        def gs_live_configure_wiring(self, edges):
            self.flow_updates.append(("wiring", edges))
            return True, "Flow wiring updated"

    window = FlowWindow()
    reg = build_app_registry(window)
    assert "voltage_to_resistance" in reg.execute(
        "gas_live_control", {"action": "flow_status"}
    )
    result = reg.execute("gas_live_control", {
        "action": "configure_flow",
        "preset": "smoothed",
        "supply_voltage_v": 5.0,
        "reference_resistance_ohm": 10_000,
        "smoothing_window": 7,
    })
    assert "moving_average" in result
    assert window.flow_updates == [(None, {
        "voltage_to_resistance": True,
        "smoothing": True,
        "smoothing_field": "resistance_ohm",
        "supply_voltage_v": 5.0,
        "reference_resistance_ohm": 10_000,
        "smoothing_window": 7,
    })]
    sensors = [
        {"source_field": "ai0_voltage_v", "alias": "MQ-2 A"},
        {"source_field": "ai1_voltage_v", "alias": "MQ-135 B", "smoothing": True},
    ]
    reg.execute("gas_live_control", {
        "action": "configure_flow", "sensor_channels": sensors,
    })
    assert window.flow_updates[-1] == (None, {"sensor_channels": sensors})
    wiring_result = reg.execute("gas_live_control", {
        "action": "configure_wiring",
        "edges": "source>book,book>graph",
    })
    assert wiring_result == "Flow wiring updated"
    assert window.flow_updates[-1] == (
        "wiring", [["source", "book"], ["book", "graph"]]
    )


def test_app_tools_open_file_loads_into_book(tmp_path):
    csv = tmp_path / "sample.csv"
    csv.write_text("time,voltage\n0,0.1\n1,0.5\n2,0.9\n", encoding="utf-8")
    window = _FakeWindow(None)
    window.staged = []
    window._stage_insert = lambda name, df, path: window.staged.append((name, len(df)))
    reg = build_app_registry(window)
    out = reg.execute("open_file", {"path": str(csv)})
    assert "3 rows" in out and "2 columns" in out
    assert window.staged and window.staged[0][1] == 3


def test_app_tools_open_file_missing_path():
    reg = build_app_registry(_FakeWindow(None))
    assert "not found" in reg.execute("open_file", {"path": "/no/such/file.csv"}).lower()


def test_app_tools_smooth_drives_core_and_defaults_column():
    df = pd.DataFrame({"t": [1, 2, 3], "voltage": [0.1, 0.9, 0.2]})
    window = _FakeWindow(df)
    reg = build_app_registry(window)
    out = reg.execute("smooth_data", {"method": "median"})
    # defaulted to the last numeric column
    assert window.smoothed[0] == "voltage" and window.smoothed[1] == "median"
    assert "voltage_sm" in out


def test_app_tools_filter_requires_fs():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0]})
    reg = build_app_registry(_FakeWindow(df))
    assert "fs" in reg.execute("filter_signal", {"kind": "lowpass"}).lower()


def test_app_tools_filter_drives_core_with_fs():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0]})
    window = _FakeWindow(df)
    reg = build_app_registry(window)
    out = reg.execute("filter_signal", {"fs": 100, "kind": "lowpass", "cutoff": 10})
    assert window.filtered == ("y", 100.0, "lowpass", 10)
    assert "y_lowpass" in out


# --- transform / clean tools calling the shared pure functions directly ------
def test_app_tools_moving_average_adds_column():
    window = _FakeWindow(pd.DataFrame({"t": range(30), "y": range(30)}))
    out = build_app_registry(window).execute("moving_average", {"window": 5})
    new_cols = [c for c in window._df.columns if c not in ("t", "y")]
    assert new_cols and new_cols[0] in window.added
    assert "moving average" in out.lower()


def test_app_tools_fill_missing_adds_column():
    import numpy as np
    window = _FakeWindow(pd.DataFrame({"y": [1.0, np.nan, 3.0, np.nan, 5.0]}))
    out = build_app_registry(window).execute("fill_missing", {"method": "mean"})
    assert any(c != "y" for c in window._df.columns)
    assert "filled" in out.lower()


def test_app_tools_normalize_zscore_adds_column():
    window = _FakeWindow(pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0, 5.0]}))
    out = build_app_registry(window).execute("normalize", {"method": "zscore"})
    assert "y_zscore" in window._df.columns
    assert "normalized" in out.lower()


def test_app_tools_detrend_adds_column():
    window = _FakeWindow(pd.DataFrame({"y": [2.0, 4.0, 6.0, 8.0, 10.0]}))
    out = build_app_registry(window).execute("detrend", {"order": 1})
    assert any(c != "y" for c in window._df.columns)
    assert "trend" in out.lower()


def test_app_tools_remove_outliers_swaps_dataframe():
    window = _FakeWindow(pd.DataFrame({"y": [1.0] * 12 + [50.0]}))
    out = build_app_registry(window).execute("remove_outliers", {"method": "zscore", "threshold": 2})
    assert len(window._df) < 13
    assert "outlier" in out.lower()


def test_app_tools_find_anomalies_reports_without_changing_data():
    window = _FakeWindow(pd.DataFrame({"y": [1.0] * 15 + [500.0]}))
    out = build_app_registry(window).execute(
        "find_anomalies", {"method": "zscore", "threshold": 3}
    )
    # read-only: the active DataFrame is untouched
    assert len(window._df) == 16
    assert "anomal" in out.lower()
    assert "500" in out
    assert "row 15" in out


def test_app_tools_find_anomalies_reports_none_when_clean():
    window = _FakeWindow(pd.DataFrame({"y": [1.0, 2.0, 3.0, 2.0, 1.0]}))
    out = build_app_registry(window).execute("find_anomalies", {})
    assert "no anomal" in out.lower()


def test_app_tools_remove_duplicates_swaps_dataframe():
    window = _FakeWindow(pd.DataFrame({"a": [1, 1, 2, 2], "b": [3, 3, 4, 4]}))
    out = build_app_registry(window).execute("remove_duplicates", {})
    assert len(window._df) == 2
    assert "duplicate" in out.lower()


def test_app_tools_sort_data_requires_valid_column():
    window = _FakeWindow(pd.DataFrame({"a": [3, 1, 2]}))
    reg = build_app_registry(window)
    assert "valid 'column'" in reg.execute("sort_data", {}).lower()
    out = reg.execute("sort_data", {"column": "a", "ascending": True})
    assert list(window._df["a"]) == [1, 2, 3]
    assert "sorted" in out.lower()


def test_app_tools_run_fft_opens_result_book_and_reports_peak():
    import numpy as np
    t = np.linspace(0, 1, 256, endpoint=False)
    y = np.sin(2 * np.pi * 10 * t)  # 10 Hz tone
    window = _FakeWindow(pd.DataFrame({"t": t, "y": y}))
    out = build_app_registry(window).execute("run_fft", {"column": "y", "x_column": "t"})
    assert window.result_books and window.result_books[0][0] == "FFT_y"
    assert "10" in out  # dominant frequency ~10 Hz
    assert "dominant" in out.lower()


def test_app_tools_list_books_reports_active():
    window = _FakeWindow(pd.DataFrame({"y": [1, 2, 3]}))
    out = build_app_registry(window).execute("list_books", {})
    assert "Book1" in out and "Book2" in out
    assert "active" in out.lower()


def test_app_tools_envelope_adds_column():
    import numpy as np
    t = np.linspace(0, 1, 200)
    window = _FakeWindow(pd.DataFrame({"y": np.sin(2 * np.pi * 20 * t)}))
    out = build_app_registry(window).execute("envelope", {"column": "y"})
    assert "y_envelope" in window._df.columns
    assert "envelope" in out.lower()


def test_app_tools_signal_quality_reports_snr():
    import numpy as np
    rng = np.random.RandomState(0)
    t = np.linspace(0, 1, 500)
    window = _FakeWindow(pd.DataFrame({"y": np.sin(2 * np.pi * 5 * t) + 0.05 * rng.randn(500)}))
    out = build_app_registry(window).execute("signal_quality", {"fs": 500})
    assert "snr" in out.lower() and "db" in out.lower()


def test_app_tools_power_spectrum_opens_book():
    import numpy as np
    t = np.linspace(0, 1, 256, endpoint=False)
    window = _FakeWindow(pd.DataFrame({"y": np.sin(2 * np.pi * 8 * t)}))
    out = build_app_registry(window).execute("power_spectrum", {"fs": 256, "column": "y"})
    assert window.result_books and window.result_books[0][0] == "PSD_y"
    assert "psd" in out.lower() or "power" in out.lower()


def test_app_tools_autocorrelation_opens_book():
    import numpy as np
    window = _FakeWindow(pd.DataFrame({"y": np.sin(np.linspace(0, 20, 200))}))
    out = build_app_registry(window).execute("autocorrelation", {"column": "y"})
    assert window.result_books and window.result_books[0][0] == "Autocorr_y"
    assert "correlation" in out.lower()


def test_app_tools_instantaneous_frequency_adds_column():
    import numpy as np
    t = np.linspace(0, 1, 300)
    window = _FakeWindow(pd.DataFrame({"y": np.sin(2 * np.pi * 15 * t)}))
    out = build_app_registry(window).execute("instantaneous_frequency", {"fs": 300, "column": "y"})
    assert "y_inst_freq" in window._df.columns
    assert "instantaneous" in out.lower()


def test_app_tools_harmonic_analysis_opens_book():
    import numpy as np
    t = np.linspace(0, 1, 512, endpoint=False)
    y = np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 10 * t)
    window = _FakeWindow(pd.DataFrame({"y": y}))
    out = build_app_registry(window).execute("harmonic_analysis", {"fs": 512, "column": "y"})
    assert window.result_books and window.result_books[0][0] == "Harmonics_y"
    assert "component" in out.lower()


# --- peak / cross-correlation analysis ---------------------------------------
def test_app_tools_peak_metrics_reports_main_peak():
    import numpy as np
    x = np.linspace(-5, 5, 200)
    y = np.exp(-((x - 1.0) ** 2) / 0.5)  # gaussian peak at x=1
    window = _FakeWindow(pd.DataFrame({"x": x, "y": y}))
    out = build_app_registry(window).execute("peak_metrics", {"column": "y"})
    assert "fwhm" in out.lower() and "height" in out.lower()


def test_app_tools_detect_peaks_opens_table():
    import numpy as np
    t = np.linspace(0, 1, 400)
    y = np.sin(2 * np.pi * 6 * t)  # 6 clear peaks
    window = _FakeWindow(pd.DataFrame({"y": y}))
    out = build_app_registry(window).execute("detect_peaks", {"prominence": 0.5})
    assert window.result_books and window.result_books[0][0] == "Peaks_y"
    assert "peaks" in out.lower()


def test_app_tools_cross_correlation_reports_lag():
    import numpy as np
    base = np.sin(np.linspace(0, 20, 300))
    shifted = np.roll(base, 10)
    window = _FakeWindow(pd.DataFrame({"a": base, "b": shifted}))
    out = build_app_registry(window).execute("cross_correlation", {"column_a": "a", "column_b": "b"})
    assert window.result_books and window.result_books[0][0].startswith("XCorr_")
    assert "lag" in out.lower()


# --- graph decoration + advanced charts --------------------------------------
def test_app_tools_format_graph_sets_title_and_grid():
    window = _FakeWindow(pd.DataFrame({"y": [1, 2, 3]}))
    out = build_app_registry(window).execute(
        "format_graph", {"title": "My Plot", "xlabel": "Time", "grid": True}
    )
    ax = window.active_axes()
    assert ax.get_title() == "My Plot"
    assert ax.get_xlabel() == "Time"
    assert "title" in out.lower()


def test_app_tools_format_graph_without_axes():
    window = _FakeWindow(pd.DataFrame({"y": [1, 2, 3]}))
    window.active_axes = lambda: None
    assert "no active graph" in build_app_registry(window).execute("format_graph", {"title": "x"}).lower()


def test_app_tools_list_and_plot_chart():
    window = _FakeWindow(pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}))
    reg = build_app_registry(window)
    listed = reg.execute("list_charts", {})
    assert "chart types" in listed.lower()
    # first available key should plot without a dialog
    from plots.registry import all_plots
    key = all_plots()[0]["key"]
    out = reg.execute("plot_chart", {"chart_type": key})
    assert window.charts == [key]
    assert "chart" in out.lower()


def test_app_tools_plot_chart_unknown_type():
    window = _FakeWindow(pd.DataFrame({"a": [1, 2, 3]}))
    out = build_app_registry(window).execute("plot_chart", {"chart_type": "definitely_not_a_chart"})
    assert "unknown chart" in out.lower()


# ------------------------------------------------------------------- dock wiring
from main_window_ai_mixin import MainWindowAIMixin  # noqa: E402


class _AiHost(QObject, MainWindowAIMixin, _FakeWindow):
    """MainWindow-like host: mixin + a real AI dock, no full app needed."""

    def __init__(self, df, dock):
        QObject.__init__(self)
        _FakeWindow.__init__(self, df)
        self.ai_dock = dock


def test_gui_tool_executor_marshals_worker_calls_to_qt_main_thread(qapp):
    from main_window_ai_mixin import _GuiToolExecutor

    executor = _GuiToolExecutor()
    registry = ToolRegistry(executor=executor)
    handler_threads = []
    results = []
    registry.add(
        "thread_probe",
        "probe",
        {},
        lambda _arguments: handler_threads.append(QThread.currentThread()) or "ok",
    )

    worker = threading.Thread(
        target=lambda: results.append(registry.execute("thread_probe", {})),
        daemon=True,
    )
    worker.start()
    deadline = time.monotonic() + 3.0
    while worker.is_alive() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    worker.join(timeout=0.1)

    assert not worker.is_alive()
    assert results == ["ok"]
    assert handler_threads == [qapp.thread()]


def test_dock_message_drives_assistant_and_shows_reply(qapp):
    from UI.docks.ai_dock import AiAssistantDock

    dock = AiAssistantDock()
    host = _AiHost(pd.DataFrame({"time": [1, 2], "voltage": [3, 4]}), dock)

    client = ScriptedClient([
        json.dumps({"tool": "list_columns", "arguments": {}}),
        json.dumps({"answer": "Your data has time and voltage."}),
    ])
    assert host.init_ai_assistant(client=client) is True
    host._ai_synchronous = True  # keep the test deterministic (no worker thread)

    dock.input_edit.setText("what columns do I have?")
    dock._submit()  # emits message_submitted -> mixin -> assistant

    transcript = dock.transcript_text()
    assert "You: what columns do I have?" in transcript
    assert "AI: Active data has 2 rows and 2 columns: time, voltage." in transcript
    assert client.calls == []
    assert host._ai_busy is False


def test_assistant_disabled_in_config_skips_wiring(qapp, monkeypatch):
    from UI.docks.ai_dock import AiAssistantDock
    from settings import AIConfig, settings_manager

    monkeypatch.setattr(settings_manager, "get_ai", lambda: AIConfig(enabled=False))
    host = _AiHost(None, AiAssistantDock())
    assert host.init_ai_assistant() is False


def test_ai_dock_exposes_local_model_manager_action(qapp):
    from UI.docks.ai_dock import AiAssistantDock

    dock = AiAssistantDock()
    requested = []
    dock.manage_models_requested.connect(lambda: requested.append(True))

    dock.models_button.click()

    assert requested == [True]
    assert "local" in dock.models_button.toolTip().casefold()


def test_ai_dock_run_button_becomes_cancel_and_shows_resolved_inputs(qapp):
    from UI.docks.ai_dock import AiAssistantDock
    from ai.agent import AssistantResult

    dock = AiAssistantDock()
    cancelled = []
    dock.cancel_requested.connect(lambda: cancelled.append(True))

    dock.set_busy(True, "Understanding request")
    assert dock.send_button.text() == "Cancel"
    assert dock.send_button.isEnabled()
    dock.send_button.click()
    assert cancelled == [True]

    dock.complete_request(
        AssistantResult(
            answer="done",
            trace=[("smooth_data", {"column": "Signal", "method": "median"}, "ok")],
        )
    )
    assert "column=Signal" in dock.action_label.text()
    assert '"column": "Signal"' in dock.action_label.toolTip()


def test_ai_dock_marks_clarification_as_needs_input(qapp):
    from UI.docks.ai_dock import AiAssistantDock
    from ai.agent import AssistantResult

    dock = AiAssistantDock()
    dock.set_busy(True)
    dock.complete_request(
        AssistantResult(answer="Please specify sampling rate.", needs_input=True)
    )

    assert dock.status_label.text() == "Needs input"
    assert dock.input_edit.isEnabled()


def test_ai_worker_cancel_interrupts_client_and_unlocks_dock(qapp):
    from UI.docks.ai_dock import AiAssistantDock

    class _CancellableClient:
        model = "test"

        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.cancel_calls = 0

        def chat(self, _messages, *, format_json=False):
            self.started.set()
            self.release.wait(timeout=3)
            return json.dumps({"answer": "late reply"})

        def cancel(self):
            self.cancel_calls += 1
            self.release.set()

    dock = AiAssistantDock()
    host = _AiHost(pd.DataFrame({"time": [1, 2], "signal": [3, 4]}), dock)
    client = _CancellableClient()
    assert host.init_ai_assistant(client=client) is True

    dock.input_edit.setText("explain this dataset")
    dock._submit()
    deadline = time.monotonic() + 3
    while not client.started.is_set() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    dock.send_button.click()
    while getattr(host, "_ai_worker", None) is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert client.cancel_calls == 1
    assert host._ai_busy is False
    assert dock.send_button.text() == "Run"
    assert "Cancelled" in dock.transcript_text()


class _RecipeWindow(_FakeWindow):
    def analysis_recipe_summaries(self):
        return [{"name": "One-sample t-test", "status": "Clean", "mode": "Auto"}]


def test_scientific_tools_are_registered():
    reg = build_app_registry(_FakeWindow(pd.DataFrame({"a": [1.0, 2.0, 3.0]})))
    for name in ("run_statistics", "global_fit", "analyze_peaks", "list_analysis_recipes"):
        assert reg.has(name), name


def test_run_statistics_reports_significance_and_opens_book():
    import numpy as np

    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "control": rng.normal(0.0, 1.0, 40),
        "treated": rng.normal(3.0, 1.0, 40),
    })
    window = _FakeWindow(df)
    out = build_app_registry(window).execute(
        "run_statistics",
        {"test": "independent_t_test", "columns": ["control", "treated"]},
    )
    assert "independent_t_test" in out
    assert "significant" in out
    assert any(name.startswith("Stats_") for name, _ in window.result_books)


def test_run_statistics_rejects_unknown_test():
    reg = build_app_registry(_FakeWindow(pd.DataFrame({"a": [1.0, 2.0, 3.0]})))
    out = reg.execute("run_statistics", {"test": "made_up_test"})
    assert "Unknown test" in out


def test_global_fit_tool_reports_convergence_and_opens_books():
    import numpy as np

    x = np.linspace(-4, 4, 120)
    df = pd.DataFrame({
        "x": x,
        "run1": 1 + 3 * np.exp(-0.5 * ((x - 0.3) / 0.8) ** 2),
        "run2": 2 + 5 * np.exp(-0.5 * ((x - 0.3) / 0.8) ** 2),
    })
    window = _FakeWindow(df)
    out = build_app_registry(window).execute(
        "global_fit",
        {"x_column": "x", "y_columns": ["run1", "run2"], "model": "gaussian",
         "shared": ["center", "sigma"]},
    )
    assert "converged" in out
    names = [name for name, _ in window.result_books]
    assert any(n.startswith("GlobalFit_") for n in names)
    assert any(n.endswith("_curves") for n in names)


def test_analyze_peaks_tool_fits_single_peak():
    import numpy as np

    x = np.linspace(0, 10, 300)
    y = 0.1 * x + 2 * np.exp(-0.5 * ((x - 4) / 0.35) ** 2)
    window = _FakeWindow(pd.DataFrame({"x": x, "y": y}))
    out = build_app_registry(window).execute(
        "analyze_peaks",
        {"x_column": "x", "y_column": "y", "prominence": 0.5},
    )
    assert "1 peak" in out
    assert "converged" in out


def test_scientific_tools_handle_no_active_data():
    reg = build_app_registry(_FakeWindow(None))
    assert "No active data" in reg.execute("run_statistics", {"test": "one_sample_t_test"})
    assert "No active data" in reg.execute("global_fit", {})
    assert "No active data" in reg.execute("analyze_peaks", {})


def test_list_analysis_recipes_enumerates_saved_recipes():
    reg = build_app_registry(_RecipeWindow(pd.DataFrame({"a": [1.0, 2.0, 3.0]})))
    out = reg.execute("list_analysis_recipes", {})
    assert "One-sample t-test" in out
    assert "Clean" in out


def _window_with_plotted_axes(n_series=3):
    import numpy as np
    window = _FakeWindow(pd.DataFrame({"a": [1, 2, 3]}))
    ax = window.active_axes()
    x = np.linspace(0, 10, 30)
    for i in range(n_series):
        ax.plot(x, np.sin(x) + i, label=f"s{i}")
    ax.legend()
    return window, ax


def test_format_graph_applies_journal_preset_by_fuzzy_name():
    window, ax = _window_with_plotted_axes()
    out = build_app_registry(window).execute("format_graph", {"journal_preset": "nature"})
    assert "Nature" in out and "preset" in out
    assert ax.spines["top"].get_visible() is False  # open-frame journal styling
    assert ax.xaxis.label.get_family() == ["sans-serif"]


def test_format_graph_recolors_colorblind_safe():
    from core.plot_style import COLORBLIND_SAFE_PALETTES, SCIENTIFIC_PALETTES
    window, ax = _window_with_plotted_axes(3)
    out = build_app_registry(window).execute("format_graph", {"colorblind": True})
    assert "palette" in out
    safe = SCIENTIFIC_PALETTES[COLORBLIND_SAFE_PALETTES[0]]
    assert ax.get_lines()[0].get_color().upper() == safe[0].upper()


def test_format_graph_named_palette_and_line_width():
    from core.plot_style import SCIENTIFIC_PALETTES
    window, ax = _window_with_plotted_axes(2)
    out = build_app_registry(window).execute(
        "format_graph", {"palette": "Tol Bright (CB-safe)", "line_width": 2.0}
    )
    assert "Tol Bright" in out
    assert ax.get_lines()[0].get_color().upper() == SCIENTIFIC_PALETTES["Tol Bright (CB-safe)"][0].upper()
    assert ax.get_lines()[0].get_linewidth() == 2.0


def test_format_graph_rejects_unknown_preset_and_palette():
    window, _ = _window_with_plotted_axes(1)
    reg = build_app_registry(window)
    assert "Unknown journal preset" in reg.execute("format_graph", {"journal_preset": "wat"})
    assert "Unknown palette" in reg.execute("format_graph", {"palette": "wat"})


def test_format_graph_fill_value_labels_and_errorbars():
    window, ax = _window_with_plotted_axes(2)
    reg = build_app_registry(window)
    out = reg.execute("format_graph", {"fill": "under", "fill_alpha": 0.3})
    assert "fill under" in out
    fills = [c for c in ax.collections if str(c.get_gid() or "").startswith("_ps_fill")]
    assert len(fills) == 2
    out = reg.execute("format_graph", {"value_labels": True, "label_format": "%.2f"})
    assert "value labels" in out
    assert any(str(t.get_gid() or "").startswith("_ps_vlab") for t in ax.texts)
    out = reg.execute("format_graph", {"errorbars": "5%"})
    assert "error bars 5%" in out
    assert any(getattr(c, "_ps_gid", None) for c in ax.containers)
    out = reg.execute("format_graph", {"errorbars": "off", "fill": "off",
                                       "value_labels": False})
    assert not any(getattr(c, "_ps_gid", None) for c in ax.containers)


def test_format_graph_inset_zoom_defaults_to_middle_third():
    window, ax = _window_with_plotted_axes(1)
    out = build_app_registry(window).execute("format_graph", {"inset": True})
    assert "zoom inset" in out
    axins = getattr(ax, "_ps_inset_ax", None)
    assert axins is not None
    lo, hi = axins.get_xlim()
    assert 2.0 < lo < 4.5 and 5.5 < hi < 8.0  # middle third of 0..10
    out = build_app_registry(window).execute("format_graph", {"inset": False})
    assert "inset removed" in out
    assert getattr(ax, "_ps_inset_ax", None) is None


def test_format_graph_colormap_on_heatmap_and_line_plot():
    import numpy as np

    window, ax = _window_with_plotted_axes(1)
    out = build_app_registry(window).execute("format_graph", {"colormap": "viridis"})
    assert "no image/heatmap" in out  # line plots have no mappable

    window2 = _FakeWindow(pd.DataFrame({"a": [1.0]}))
    ax2 = window2.active_axes()
    image = ax2.imshow(np.random.default_rng(1).random((4, 4)))
    out = build_app_registry(window2).execute(
        "format_graph", {"colormap": "cividis", "colorbar": True,
                         "colorbar_label": "Counts"}
    )
    assert "colormap/colorbar" in out
    assert image.get_cmap().name == "cividis"
