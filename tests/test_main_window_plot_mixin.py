from __future__ import annotations

import os
from pathlib import Path
import sys

import pandas as pd
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("PySide6")
pytest.importorskip("numexpr")

from PySide6.QtWidgets import QApplication, QWidget

from core.plot_request import HistogramRequest, PlotOptions, PlotRequest
from main_window_plot_mixin import MainWindowPlotMixin
from widgets.plot_tabs import TabManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Combo:
    def __init__(self, text: str):
        self._text = text

    def currentText(self) -> str:
        return self._text


class _StatusBar:
    def __init__(self):
        self.messages = []

    def showMessage(self, message: str, *_args) -> None:
        self.messages.append(message)


class DummyWindow(QWidget, MainWindowPlotMixin):
    def __init__(self):
        super().__init__()
        self.plot_mode = "REPLACE"
        self.tabs = TabManager(self)
        self.cbX = _Combo("time")
        self.cbY = _Combo("value")
        self._plot_options = PlotOptions(
            line_width=2,
            show_marker=True,
            histogram_bins=3,
            fit_normal=True,
        )
        self._status_bar = _StatusBar()
        self._current_path = "D:/data/sample.csv"
        self._datasets = {"Sample Data": {"path": self._current_path}}
        self._df = pd.DataFrame({"value": [1, 2, 2, 3, 5, 8]})

    def statusBar(self):
        return self._status_bar

    def _get_xy(self):
        return [1, 2, 3], [10, 20, 15]

    def build_plot_request(self):
        x, y = self._get_xy()
        return PlotRequest(x, y, self.cbX.currentText(), self.cbY.currentText())

    def build_histogram_request(self, column=None, options=None):
        return HistogramRequest(
            values=self._df["value"].to_numpy(),
            column=column or "value",
            options=options or self._plot_options,
        )

    def _is_datetime_column(self, _name):
        return False


def test_layer_meta_helpers_include_dataset_context(qapp):
    window = DummyWindow()

    assert window._get_dataset_name_for_path(window._current_path) == "Sample Data"
    assert window._get_dataset_name_for_path("missing.csv") == ""

    meta = window._build_layer_meta(
        "line",
        "value vs time",
        {"linewidth": 2, "marker": None},
        source="plot_line",
    )

    assert meta == {
        "style": "line",
        "label": "value vs time",
        "dataset_path": "D:/data/sample.csv",
        "dataset_name": "Sample Data",
        "x_column": "time",
        "y_column": "value",
        "source": "plot_line",
        "style_kwargs": {"linewidth": 2},
    }


def test_plot_line_then_scatter_updates_current_tab_headless(qapp):
    window = DummyWindow()
    tab_id = window.tabs.get_current_tab_id()
    graph_tab = window.tabs.tabs[tab_id]

    window.plot_line()

    assert len(graph_tab.layers) == 1
    assert len(graph_tab.get_axes().lines) == 1
    line_layer = next(iter(graph_tab.layers.values()))
    assert line_layer["style"] == "line"
    assert line_layer["meta"]["style_kwargs"] == {"linewidth": 2, "marker": "o"}
    assert window.statusBar().messages[-1] == "Line plot created."

    window.plot_mode = "OVERLAY"
    window.plot_scatter()

    assert len(graph_tab.layers) == 2
    assert len(graph_tab.get_axes().collections) == 1
    scatter_layer = next(info for info in graph_tab.layers.values() if info["style"] == "scatter")
    assert scatter_layer["kwargs"]["s"] == 10
    assert window.statusBar().messages[-1] == "Scatter plot created."


def test_plot_line_accepts_widget_independent_request(qapp):
    window = DummyWindow()
    request = PlotRequest(
        x=[0, 1],
        y=[7, 9],
        x_column="elapsed",
        y_column="temperature",
    )

    window.plot_line(request, PlotOptions(line_width=4, show_marker=False))

    graph_tab = window.tabs.tabs[window.tabs.get_current_tab_id()]
    layer = next(iter(graph_tab.layers.values()))
    assert layer["label"] == "temperature vs elapsed"
    assert layer["meta"]["x_column"] == "elapsed"
    assert layer["meta"]["y_column"] == "temperature"
    assert layer["meta"]["style_kwargs"] == {"linewidth": 4}
    assert graph_tab.get_axes().get_xlabel() == "elapsed"
    assert graph_tab.get_axes().get_ylabel() == "temperature"


def test_overlay_helpers_add_line_and_scatter_layers_headless(qapp):
    window = DummyWindow()
    tab_id = window.tabs.get_current_tab_id()
    graph_tab = window.tabs.tabs[tab_id]

    window.add_line_overlay()
    window.add_scatter_overlay()

    assert len(graph_tab.layers) == 2
    assert {info["style"] for info in graph_tab.layers.values()} == {"line", "scatter"}
    assert window.statusBar().messages[-2:] == [
        "Added line series (overlay)",
        "Added scatter series (overlay)",
    ]


def test_plot_histogram_and_bar_headless(qapp):
    window = DummyWindow()
    tab_id = window.tabs.get_current_tab_id()
    graph_tab = window.tabs.tabs[tab_id]

    window.plot_histogram()

    ax = graph_tab.get_axes()
    assert len(ax.patches) == 3
    assert ax.get_xlabel() == "value"
    assert ax.get_ylabel() == "Count"
    assert ax.get_title() == "Histogram of value (bins=3)"
    assert any(line.get_label().startswith("Normal fit mu=") for line in ax.lines)
    assert window.statusBar().messages[-1] == "Histogram created."

    window.plot_mode = "REPLACE"
    window.plot_bar(["alpha", "beta", "gamma"], [3, 1, 2], xlabel="group", ylabel="count", title="Counts")

    ax = graph_tab.get_axes()
    assert len(graph_tab.layers) == 1
    assert next(iter(graph_tab.layers.values()))["style"] == "bar"
    assert ax.get_xlabel() == "group"
    assert ax.get_ylabel() == "count"
    assert ax.get_title() == "Counts"
    assert [tick.get_text() for tick in ax.get_xticklabels()[:3]] == ["alpha", "beta", "gamma"]
