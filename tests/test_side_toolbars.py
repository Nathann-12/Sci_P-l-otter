"""The Origin-style left / right / bottom tool docks: they exist in the right
areas, every action is wired to a live handler (no dead icons), reused checkable
actions share state with the top bar, and the core tools actually do their job.
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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    df = pd.DataFrame({"Row": np.arange(200, dtype=float),
                       "Sn": np.linspace(2.3e6, 4.9e6, 200)})
    w._stage_insert("s.csv", df, None)
    w._df = df
    w.cbX.clear(); w.cbX.addItems(["Row", "Sn"]); w.cbX.setCurrentText("Row")
    w.cbY.clear(); w.cbY.addItems(["Row", "Sn"]); w.cbY.setCurrentText("Sn")
    yield w
    w.close()


def test_side_toolbars_exist_in_their_areas(win):
    assert set(win.side_toolbars) == {"left", "right", "bottom"}
    assert win.toolBarArea(win.left_toolbar) == Qt.LeftToolBarArea
    assert win.toolBarArea(win.right_toolbar) == Qt.RightToolBarArea
    assert win.toolBarArea(win.bottom_toolbar) == Qt.BottomToolBarArea


def test_every_dock_action_has_an_icon_key_and_no_dead_buttons(win):
    for side, toolbar in win.side_toolbars.items():
        acts = [a for a in toolbar.actions() if not a.isSeparator()]
        assert acts, f"{side} dock has no actions"
        for a in acts:
            assert a.property("toolbarIconKey"), (side, a.text())
            assert not a.icon().isNull(), (side, a.text())

    # the dialog-opening dock buttons resolve to real callables
    for method in ("open_plot_details_dialog", "open_plot_gallery",
                   "on_plot_from_equation", "open_nonlinear_fit_dialog",
                   "run_fft_dialog", "open_spectrogram_dialog",
                   "open_derived_column_dialog", "export_figure_advanced",
                   "export_figures_batch"):
        assert callable(getattr(win, method, None)), method


def test_docks_are_categorized(win):
    """Each dock hosts its own coherent category of tools."""
    left = set(win.left_toolbar.actions())
    right = set(win.right_toolbar.actions())
    bottom = set(win.bottom_toolbar.actions())
    # left = graph interaction + annotation (reuses the top-bar checkables)
    for k in ("crosshair", "boxzoom", "reset_view", "format_graph",
              "ann_enable", "ann_text", "undo", "redo"):
        assert win.toolbar_actions[k] in left, k
    # right = windows + export + Book operations
    for k in ("addtab", "window_tile", "window_cascade", "inspector",
              "export_figure", "export_data", "batch_export", "copy_graph",
              "dataset_group", "dataset_merge"):
        assert win.toolbar_actions[k] in right, k
    # bottom = process / clean / signal / analysis / peak / workflow
    for k in ("moving_average", "fill_missing", "butterworth", "hilbert",
              "stats", "peak_detect", "workflow_history"):
        assert win.toolbar_actions[k] in bottom, k


def test_left_dock_zoom_and_reset_operate_on_the_active_graph(win):
    win.toolbar_actions["plot_line"].trigger()  # plot from the top bar
    ax = win.tabs.currentWidget().get_axes()
    span0 = ax.get_xlim()[1] - ax.get_xlim()[0]

    win.toolbar_actions["left_zoom_in"].trigger()
    assert (ax.get_xlim()[1] - ax.get_xlim()[0]) < span0  # zoomed in

    # zoom into an off-data region, then Reset View must bring the data back
    ax.set_xlim(10, 20); ax.set_ylim(3.0e6, 3.05e6)
    win.toolbar_actions["reset_view"].trigger()
    ylo, yhi = ax.get_ylim()
    assert ylo <= 2.3e6 + 1 and yhi >= 4.8e6 - 1


def test_right_dock_new_graph_tile_cascade(win):
    before = win.tabs.count()
    win.toolbar_actions["addtab"].trigger()
    assert win.tabs.count() == before + 1
    # tiling/cascading several windows must not raise
    win.toolbar_actions["plot_scatter"].trigger()
    win.toolbar_actions["window_tile"].trigger()
    win.toolbar_actions["window_cascade"].trigger()


def test_top_bar_icon_key_uniqueness_still_holds(win):
    # regression guard: the side docks must not pollute the top-bar contract
    icon_keys = [
        a.property("toolbarIconKey")
        for tb in (win.tb, win.function_toolbar)
        for a in tb.actions()
        if not a.isSeparator()
    ]
    assert all(icon_keys)
    assert len(icon_keys) == len(set(icon_keys))
