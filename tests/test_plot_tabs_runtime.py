from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from widgets.plot_tabs import TabManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class DummyMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.plot_mode = "REPLACE"


def test_plot_to_tabs_replaces_then_overlays_layers_headless(qapp):
    main_window = DummyMainWindow()
    tabs = TabManager(main_window)
    tab_id = tabs.get_current_tab_id()
    graph_tab = tabs.tabs[tab_id]

    first = tabs.plot_to_tabs([tab_id], [1, 2, 3], [10, 20, 30], label="Primary", color="red")

    assert len(first) == 1
    assert len(graph_tab.layers) == 1
    assert len(graph_tab.get_axes().lines) == 1
    assert list(graph_tab.layers.values())[0]["kwargs"]["color"] == "red"

    main_window.plot_mode = "OVERLAY"
    second = tabs.plot_to_tabs([tab_id], [1, 2, 3], [30, 20, 10], label="Overlay", style="scatter")

    assert len(second) == 1
    assert len(graph_tab.layers) == 2
    assert len(graph_tab.get_axes().lines) == 1
    assert len(graph_tab.get_axes().collections) == 1

    main_window.plot_mode = "REPLACE"
    third = tabs.plot_to_tabs([tab_id], [5, 6], [50, 60], label="Replacement")

    assert len(third) == 1
    assert len(graph_tab.layers) == 1
    assert [line.get_label() for line in graph_tab.get_axes().lines] == ["Replacement"]


@pytest.mark.filterwarnings(
    "ignore:Could not infer format, so each element will be parsed individually.*:UserWarning"
)
def test_add_series_to_tabs_supports_bar_and_histogram_headless(qapp):
    tabs = TabManager(DummyMainWindow())
    tab_id = tabs.get_current_tab_id()
    graph_tab = tabs.tabs[tab_id]

    bar_layers = tabs.add_series_to_tabs(
        [tab_id],
        ["alpha", "beta", "gamma"],
        [1, 3, 2],
        label="Bars",
        style="bar",
    )

    assert len(bar_layers) == 1
    assert len(graph_tab.layers) == 1
    assert [tick.get_text() for tick in graph_tab.get_axes().get_xticklabels()[:3]] == [
        "alpha",
        "beta",
        "gamma",
    ]

    hist_layers = tabs.add_series_to_tabs(
        [tab_id],
        [0, 1, 2, 3],
        [1.0, float("nan"), 2.5, None],
        label="Histogram",
        style="histogram",
        bins=2,
    )

    assert len(hist_layers) == 1
    assert len(graph_tab.layers) == 2
    histogram_layer = next(info for info in graph_tab.layers.values() if info["style"] == "histogram")
    assert histogram_layer["kwargs"]["bins"] == 2
    assert histogram_layer["artists"]
