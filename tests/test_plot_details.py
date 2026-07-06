"""Tests for the Plot Details dialog + the plotstyle mixin end-to-end through
the real MainWindow (headless)."""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from dialogs.plot_details_dialog import PlotDetailsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------- dialog ----------------

def test_dialog_reads_back_edited_style(qapp):
    style = {
        "axes": {"title": "", "xlabel": "", "ylabel": "", "title_size": 12,
                 "label_size": 10, "tick_size": 10, "x_autoscale": True,
                 "xmin": 0, "xmax": 1, "y_autoscale": True, "ymin": 0, "ymax": 1,
                 "xscale": "linear", "yscale": "linear"},
        "grid": {"major": False}, "legend": {"visible": False},
        "figure": {"facecolor": "#1e2126"},
    }
    lines = [{"label": "s1", "color": "#112233", "linewidth": 1.0,
              "linestyle": "-", "marker": "None", "markersize": 6, "alpha": 1.0}]
    dlg = PlotDetailsDialog(style, lines)

    dlg.ed_title.setText("Result")
    dlg.ed_xlabel.setText("Time")
    dlg.chk_yauto.setChecked(False)
    dlg.sp_ymin.setValue(-5.0)
    dlg.sp_ymax.setValue(5.0)
    dlg.cb_yscale.setCurrentText("log")
    dlg.chk_grid.setChecked(True)
    dlg.chk_legend.setChecked(True)

    out = dlg.get_style()
    assert out["axes"]["title"] == "Result"
    assert out["axes"]["xlabel"] == "Time"
    assert out["axes"]["y_autoscale"] is False
    assert out["axes"]["ymin"] == -5.0 and out["axes"]["ymax"] == 5.0
    assert out["axes"]["yscale"] == "log"
    assert out["grid"]["major"] is True
    assert out["legend"]["visible"] is True


def test_dialog_edits_per_line_style(qapp):
    lines = [
        {"label": "a", "color": "#111111", "linewidth": 1.0, "linestyle": "-",
         "marker": "None", "markersize": 6, "alpha": 1.0},
        {"label": "b", "color": "#222222", "linewidth": 2.0, "linestyle": "--",
         "marker": "o", "markersize": 8, "alpha": 0.5},
    ]
    dlg = PlotDetailsDialog({"axes": {}, "grid": {}, "legend": {}, "figure": {}}, lines)

    # edit first curve
    dlg.sp_linewidth.setValue(4.0)
    dlg.cb_marker.setCurrentText("s")
    # switch to second curve then back — edits must persist
    dlg.cb_line.setCurrentIndex(1)
    dlg.cb_line.setCurrentIndex(0)
    result = dlg.get_line_styles()
    assert result[0]["linewidth"] == 4.0
    assert result[0]["marker"] == "s"
    assert result[1]["linestyle"] == "--"  # untouched curve keeps its style


# ---------------- mixin through MainWindow ----------------

@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def _plot_something(win):
    df = pd.DataFrame({"t": [0.0, 1.0, 2.0, 3.0], "y": [1.0, 4.0, 9.0, 16.0]})
    win._stage_insert("g.csv [ตาราง]", df, None)
    win.plot_from_workbook("line")


def test_apply_plot_details_changes_the_axes(win):
    _plot_something(win)
    ax, fig, lines = win._active_graph_axes()
    assert ax is not None and lines

    style = {
        "axes": {"title": "Styled", "xlabel": "T", "ylabel": "Y",
                 "x_autoscale": False, "xmin": 0, "xmax": 5,
                 "yscale": "linear"},
        "grid": {"major": True, "color": "#3a3f44", "linestyle": "--", "alpha": 0.3},
        "legend": {"visible": True, "loc": "best", "fontsize": 10, "frame": True, "ncol": 1},
        "figure": {},
    }
    line_styles = [{"color": "#ff8800", "linewidth": 3.0, "linestyle": "-",
                    "marker": "o", "markersize": 7, "alpha": 1.0, "label": "curve"}]

    class _Dlg:
        def get_style(self): return style
        def get_line_styles(self): return line_styles

    win._apply_plot_details(ax, fig, lines, _Dlg())

    assert ax.get_title() == "Styled"
    assert ax.get_xlim() == (0.0, 5.0)
    assert lines[0].get_linewidth() == 3.0
    assert lines[0].get_marker() == "o"
    assert ax.get_legend() is not None


def test_format_action_wired(win):
    assert callable(getattr(win, "open_plot_details_dialog", None))
    assert hasattr(win, "actFormatGraph")
    # double-click binding present on the current graph canvas
    win.bind_graph_dblclick()
    tab = win.tabs.currentWidget()
    assert getattr(tab.canvas, "_plotdetails_bound", False) is True


def test_open_plot_details_on_empty_graph_is_polite(win, monkeypatch):
    infos = []
    monkeypatch.setattr(type(win), "inform",
                        lambda self, t, x: infos.append(t), raising=False)
    win.open_plot_details_dialog()  # no curves yet
    assert infos  # informed, did not crash
