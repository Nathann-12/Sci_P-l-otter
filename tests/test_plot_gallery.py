"""Registry + gallery-seam tests for the Origin-style plot library.

- Pure checks on :mod:`plots.registry` (aggregation, uniqueness, contract).
- Behavioral checks that ``plot_from_gallery`` draws every registered plot into
  a fresh Graph through the real MainWindow wiring (offscreen), including the
  multi-panel path and twin-axis plots.
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

import matplotlib
matplotlib.use("Agg")

from plots.registry import all_plots, plots_by_category, get_plot


# ------------------------- registry (pure) -------------------------

def test_registry_aggregates_all_modules():
    plots = all_plots()
    # Multiple plot modules contribute a substantial Origin-like catalog.
    assert len(plots) >= 40
    keys = [p["key"] for p in plots]
    assert len(keys) == len(set(keys)), "plot keys must be unique"
    for p in plots:
        assert {"key", "title", "category", "func"}.issubset(p)
        assert callable(p["func"])


def test_registry_has_expected_categories_and_signature_plots():
    cats = plots_by_category()
    # sidebar order: Distribution first
    assert list(cats)[0] == "Distribution"
    present = {p["key"] for p in all_plots()}
    # a representative plot from each contributing module must exist
    for key in (
        "box", "violin", "corr_heatmap", "scatter_matrix",
        "qq_plot", "run_chart", "control_xbar", "pareto",
        "filled_contour", "stacked_lines_y_offset", "polar_line",
        "nyquist_plot", "subplot_grid",
    ):
        assert key in present, key
        assert get_plot(key) is not None


# ------------------------- gallery seam (behavioral) -------------------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    df = pd.DataFrame({
        "a": np.random.default_rng(0).normal(size=200),
        "b": np.random.default_rng(1).normal(1.0, 2.0, size=200),
        "c": np.abs(np.random.default_rng(2).normal(size=200)),
    })
    w._df = df
    w._suppress_plot_mapping_dialog = True
    yield w
    w.close()


def _graph_count(win):
    try:
        return win.tabs.count()
    except Exception:
        return None


@pytest.mark.parametrize("spec", all_plots(), ids=lambda s: s["key"])
def test_plot_from_gallery_draws_each_plot(win, spec):
    """Every registered plot draws through the real seam without raising and
    leaves visible content on the resulting figure."""
    before = _graph_count(win)
    win.plot_from_gallery(spec)
    # a new Graph window was opened (Origin loop)
    if before is not None:
        assert _graph_count(win) == before + 1

    tab = win.tabs.currentWidget()
    fig = tab.canvas.fig
    assert tab.canvas.ax in fig.axes
    if spec.get("multi"):
        assert len(fig.axes) >= 1
        # multi-panel plots build several axes
        assert len(fig.axes) > 1 or len(fig.axes[0].get_children()) > 4
    else:
        ax = fig.axes[0]
        if spec.get("projection"):
            assert ax.name == spec["projection"]
        drew = (ax.lines or ax.collections or ax.patches or ax.images
                or ax.containers)
        assert drew, f"{spec['key']} produced no artists"


def test_apply_plot_switches_projection_without_stale_canvas_axes(win):
    win.tabs.add_tab()

    win.apply_plot(lambda ax: ax.plot([0.0, np.pi / 2.0], [1.0, 2.0]), projection="polar")
    tab = win.tabs.currentWidget()
    polar_axes = tab.canvas.ax
    assert polar_axes.name == "polar"
    assert polar_axes in tab.canvas.fig.axes

    win.apply_plot(lambda ax: ax.plot([0.0, 1.0], [1.0, 2.0]))
    rect_axes = tab.canvas.ax
    assert rect_axes.name == "rectilinear"
    assert rect_axes in tab.canvas.fig.axes
    assert polar_axes not in tab.canvas.fig.axes


def test_plot_from_gallery_cancels_when_graph_creation_fails(win, monkeypatch):
    win.tabs.add_tab()
    before = _graph_count(win)
    current_tab = win.tabs.currentWidget()
    current_axes = list(current_tab.canvas.fig.axes)
    messages = []

    def fail_add_tab(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(win.tabs, "add_tab", fail_add_tab)
    monkeypatch.setattr(win, "notify", lambda msg, **kwargs: messages.append((msg, kwargs)))

    win.plot_from_gallery(get_plot("polar_line"))

    assert _graph_count(win) == before
    assert current_tab.canvas.fig.axes == current_axes
    assert messages
    assert "Could not create a new Graph window" in messages[0][0]


def test_plot_from_gallery_uses_mapping_dialog_dataframe(win, monkeypatch):
    import dialogs.plot_data_mapping_dialog as mapping_dialog

    source = pd.DataFrame({
        "wrong": [100.0, 200.0, 300.0],
        "x": [1.0, 2.0, 3.0],
        "y": [2.0, 4.0, 8.0],
    })
    mapped = source[["x", "y"]]
    seen = {}
    win._df = source
    win._suppress_plot_mapping_dialog = False

    class _Dialog:
        Accepted = 1

        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return self.Accepted

        def mapped_dataframe(self):
            return mapped

    def draw(ax, frame):
        seen["columns"] = list(frame.columns)
        ax.plot(frame["x"], frame["y"])

    monkeypatch.setattr(mapping_dialog, "PlotDataMappingDialog", _Dialog)

    before = _graph_count(win)
    win.plot_from_gallery({"key": "mapped", "title": "Mapped", "func": draw})

    assert seen["columns"] == ["x", "y"]
    assert _graph_count(win) == before + 1


def test_plot_from_gallery_cancel_mapping_does_not_create_graph(win, monkeypatch):
    import dialogs.plot_data_mapping_dialog as mapping_dialog

    win._suppress_plot_mapping_dialog = False

    class _Dialog:
        Accepted = 1

        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return 0

        def mapped_dataframe(self):
            raise AssertionError("cancelled dialog must not map data")

    monkeypatch.setattr(mapping_dialog, "PlotDataMappingDialog", _Dialog)
    before = _graph_count(win)

    win.plot_from_gallery({"key": "cancelled", "title": "Cancelled", "func": lambda ax, df: ax.plot([1], [1])})

    assert _graph_count(win) == before


def test_gallery_dialog_constructs(qapp):
    """The Origin-style gallery dialog builds its category grid from real data."""
    from dialogs.plot_gallery_dialog import PlotGalleryDialog
    df = pd.DataFrame({"x": np.arange(50.0), "y": np.random.default_rng(3).normal(size=50)})
    picked = {}
    dlg = PlotGalleryDialog(get_dataframe=lambda: df, on_pick=lambda e: picked.update(e))
    assert dlg.catList.count() >= 3  # several categories
    dlg.close()


def test_gallery_empty_data_reports_status_without_crashing(qapp):
    import main as app_main

    window = app_main.MainWindow()
    window._df = None
    window.workbook.source_df = None

    window.open_plot_gallery()
    window.plot_from_gallery({"func": lambda ax, df: None, "title": "Test"})

    assert "No data" in window.statusBar().currentMessage() or "Open or type" in window.statusBar().currentMessage()
    window.close()
