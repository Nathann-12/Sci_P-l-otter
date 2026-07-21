"""Origin-style action enablement: toolbar commands are dimmed (disabled) until
they can actually run — data commands need an active Book with rows, graph tools
need a Graph window. Plus the FFT/PSD auto-create-graph behaviour and the
deduplicated, context-tagged command palette.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main

    w = app_main.MainWindow()
    yield w
    w.close()


def _seed(win, rows=24):
    t = np.arange(rows, dtype=float)
    df = pd.DataFrame({"t": t, "signal": np.sin(t / 3.0), "other": np.cos(t / 3.0)})
    win._stage_insert("s.csv", df, None)
    return df


# --------------------------------------------------------------- enablement ---
def test_data_and_graph_commands_are_dimmed_on_a_fresh_window(win):
    # sheet-first startup: no data yet, no Graph yet
    for key in ("plot", "plot_line", "moving_average", "fft", "stats",
                "dataset_group", "use_active_book"):
        assert win.toolbar_actions[key].isEnabled() is False, key
    for key in ("format_graph", "copy_format", "paste_format", "crosshair",
                "boxzoom", "reset_view", "export_figure", "ann_text"):
        assert win.toolbar_actions[key].isEnabled() is False, key
    # always-on essentials stay clickable
    for key in ("open", "batch_import", "settings", "add_row", "addtab",
                "workflow_history", "plot_equation"):
        assert win.toolbar_actions[key].isEnabled() is True, key


def test_data_commands_enable_once_a_book_has_data(win):
    _seed(win)
    for key in ("plot", "plot_line", "moving_average", "fft", "stats",
                "dataset_group", "use_active_book"):
        assert win.toolbar_actions[key].isEnabled() is True, key
    # graph tools stay dimmed until a Graph exists
    for key in ("format_graph", "copy_format", "paste_format",
                "export_figure", "ann_text"):
        assert win.toolbar_actions[key].isEnabled() is False, key


def test_graph_tools_enable_after_a_graph_is_created_and_disable_when_closed(win):
    _seed(win)
    win.plot_line()
    for key in ("format_graph", "copy_format", "crosshair", "boxzoom",
                "reset_view", "export_figure", "ann_text"):
        assert win.toolbar_actions[key].isEnabled() is True, key
    assert win.toolbar_actions["paste_format"].isEnabled() is False

    assert win.copy_graph_format() is True
    assert win.toolbar_actions["paste_format"].isEnabled() is True

    # closing every Graph re-dims the graph-only tools
    win.tabs.remove_all_tabs()
    win.update_action_states()
    assert win.toolbar_actions["format_graph"].isEnabled() is False
    assert win.toolbar_actions["copy_format"].isEnabled() is False
    assert win.toolbar_actions["paste_format"].isEnabled() is False


def test_typing_into_book1_lights_up_the_plot_bar(win):
    # Origin loop: plotting straight from a typed worksheet must work before the
    # user clicks 'Use Active Data', so the plot commands enable as soon as data
    # is typed (not only after a DataFrame is adopted).
    from widgets.workbook import META_ROW_COUNT

    wb = win.workbook
    assert win.toolbar_actions["plot"].isEnabled() is False
    wb.set_meta(0, long_name="t")
    wb.set_meta(1, long_name="signal")
    wb.table.item(META_ROW_COUNT + 0, 0).setText("0")
    wb.table.item(META_ROW_COUNT + 0, 1).setText("7")

    assert win.toolbar_actions["plot"].isEnabled() is True
    assert win.toolbar_actions["plot_line"].isEnabled() is True


def test_dimmed_action_keeps_a_helpful_tooltip(win):
    action = win.toolbar_actions["plot"]
    assert not action.isEnabled()
    assert "data" in action.toolTip().lower()


# --------------------------------------------------- FFT/PSD auto-create graph -
def test_fft_dialog_creates_a_graph_when_none_is_open(win, monkeypatch):
    _seed(win, rows=32)
    assert win.tabs.count() == 0

    monkeypatch.setattr(
        type(win), "ask_form",
        lambda self, *a, **k: {"y_col": "signal", "window": "none", "detrend": False},
        raising=False,
    )
    monkeypatch.setattr(type(win), "notify", lambda self, *a, **k: None, raising=False)
    informs = []
    monkeypatch.setattr(type(win), "inform",
                        lambda self, *a, **k: informs.append(a), raising=False)

    win.run_fft_dialog()

    # a Graph was created on demand and the spectrum drawn — no "No graph" reject
    assert win.tabs.count() == 1
    assert len(win.tabs.currentWidget().get_axes().get_lines()) == 1
    assert informs == []


# ------------------------------------------------------------ command palette -
def test_command_palette_is_deduplicated_and_context_tagged(win):
    cmds = win._collect_palette_commands()
    labels = [label for label, _trigger in cmds]
    # no blank entries
    assert all(label.strip() for label in labels)
    # unique labels (the 47 duplicate groups are collapsed)
    assert len(labels) == len(set(labels))
    # menu commands carry their home as context (e.g. "FFT   ·   Process › ...")
    assert any("·" in label for label in labels)
    fft_labels = [label for label in labels if label.startswith("FFT")]
    assert fft_labels and "·" in fft_labels[0]
