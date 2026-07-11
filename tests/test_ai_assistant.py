"""Behavioural tests for the local AI assistant (no network / no model)."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from ai.agent import LocalAssistant, _parse_reply
from ai.app_tools import build_app_registry
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


def test_parse_reply_extracts_json_from_noise():
    assert _parse_reply('```json\n{"answer": "hi"}\n```') == {"answer": "hi"}
    assert _parse_reply("") == {"answer": ""}
    assert _parse_reply("plain") == {"answer": "plain"}


# ------------------------------------------------------------------- app tools
class _FakeWindow:
    def __init__(self, df):
        self._df = df
        self.plotted = []

    def _resolve_active_dataframe(self):
        return self._df

    def _active_book_label(self):
        return "Book1"

    def plot_from_workbook(self, style="line", new_graph=True):
        self.plotted.append((style, new_graph))


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


def test_app_tools_fit_curve_needs_two_numeric_columns():
    reg = build_app_registry(_FakeWindow(pd.DataFrame({"only": [1, 2, 3]})))
    out = reg.execute("fit_curve", {"model": "linear"})
    assert "two numeric columns" in out.lower()


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


# ------------------------------------------------------------------- dock wiring
from main_window_ai_mixin import MainWindowAIMixin  # noqa: E402


class _AiHost(MainWindowAIMixin, _FakeWindow):
    """MainWindow-like host: mixin + a real AI dock, no full app needed."""

    def __init__(self, df, dock):
        _FakeWindow.__init__(self, df)
        self.ai_dock = dock


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
    assert "AI: Your data has time and voltage." in transcript
    assert host._ai_busy is False


def test_assistant_disabled_in_config_skips_wiring(qapp, monkeypatch):
    from UI.docks.ai_dock import AiAssistantDock
    from settings import AIConfig, settings_manager

    monkeypatch.setattr(settings_manager, "get_ai", lambda: AIConfig(enabled=False))
    host = _AiHost(None, AiAssistantDock())
    assert host.init_ai_assistant() is False
