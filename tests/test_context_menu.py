"""Regression tests for the right-click plot context menu (context_menu.py),
focused on the 'Reset View makes the graph disappear' bug: the home snapshot
was captured while the axes was still empty (0,1), so resetting pushed the data
off-screen. Reset View must autoscale to the actual data instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pytest

pytest.importorskip("PySide6")

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import QApplication

from context_menu import ContextMenuManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _manager_on_empty_axes(qapp):
    """A manager adopted while the axes is still empty — home = (0,1), (0,1)."""
    fig = Figure()
    ax = fig.add_subplot(111)
    canvas = FigureCanvasQTAgg(fig)
    mgr = ContextMenuManager(canvas, ax)
    # sanity: the home snapshot is the empty-axes default
    assert mgr._zoom_hist[0].ylim[1] <= 1.0
    return mgr, ax, canvas


def test_reset_view_shows_data_even_when_home_was_captured_empty(qapp):
    mgr, ax, _ = _manager_on_empty_axes(qapp)

    # plot large-valued data into the SAME axes (OVERLAY reuse) + autoscale
    x = np.arange(3000, dtype=float)
    y = np.linspace(2.3e6, 4.9e6, 3000)
    ax.plot(x, y)
    ax.relim(); ax.autoscale_view()
    data_lo, data_hi = float(y.min()), float(y.max())

    # user zooms into a tiny sub-region
    ax.set_xlim(1000, 1500)
    ax.set_ylim(3.0e6, 3.5e6)

    # Reset View
    mgr._on_reset_view()

    ylo, yhi = ax.get_ylim()
    xlo, xhi = ax.get_xlim()
    # the full data band is visible again (not the stale (0,1) home)
    assert yhi > ylo and xhi > xlo
    assert ylo <= data_lo + 1e-6 and yhi >= data_hi - 1e-6, (ylo, yhi)
    assert xlo <= 0 and xhi >= 2999
    # and the reported symptom is gone: view is nowhere near (0,1)
    assert yhi > 1.0


def test_reset_view_includes_scatter_collections(qapp):
    """Autoscale must fit scatter points too (collections keep their extent in
    dataLim), otherwise scatter graphs would still vanish on reset."""
    mgr, ax, _ = _manager_on_empty_axes(qapp)

    x = np.linspace(0, 100, 200)
    y = np.linspace(-500.0, 900.0, 200)
    ax.scatter(x, y)
    ax.autoscale_view()

    ax.set_xlim(10, 20)
    ax.set_ylim(0, 5)

    mgr._on_reset_view()

    ylo, yhi = ax.get_ylim()
    assert ylo <= -500.0 + 1.0 and yhi >= 900.0 - 1.0, (ylo, yhi)


def test_reset_view_rebaselines_home_to_data(qapp):
    """After a reset, the stored 'home' is the true data view, so a subsequent
    reset stays correct (no drift back to the empty-axes snapshot)."""
    mgr, ax, _ = _manager_on_empty_axes(qapp)
    ax.plot(np.arange(100.0), np.linspace(1e5, 2e5, 100))
    ax.relim(); ax.autoscale_view()

    mgr._on_reset_view()
    home_after = (mgr._zoom_hist[0].xlim, mgr._zoom_hist[0].ylim)
    assert home_after[1][1] > 1.0  # y-home is the data view, not (0,1)

    # zoom + reset again → same data view
    ax.set_xlim(10, 20); ax.set_ylim(1.2e5, 1.3e5)
    mgr._on_reset_view()
    assert ax.get_ylim()[1] >= 2e5 - 1.0


def test_graph_context_menu_exposes_copy_and_clipboard_aware_paste(qapp):
    mgr, ax, _ = _manager_on_empty_axes(qapp)
    target_tab = object()
    calls = []

    class MainStub:
        ready = False

        def open_plot_details_dialog(self):
            pass

        def _graph_tab_for_figure(self, figure):
            assert figure is ax.figure
            return target_tab

        def copy_graph_format(self, tab):
            calls.append(("copy", tab))

        def paste_graph_format(self, tab):
            calls.append(("paste", tab))

        def has_format_clipboard(self):
            return self.ready

    main = MainStub()
    mgr.main = main
    event = SimpleNamespace(xdata=0.5, ydata=0.5)

    menu = mgr._build_menu(event)
    actions = {action.text(): action for action in menu.actions()}
    assert actions["Copy Graph Format"].isEnabled()
    assert not actions["Paste Graph Format"].isEnabled()
    actions["Copy Graph Format"].trigger()
    assert calls == [("copy", target_tab)]

    main.ready = True
    menu = mgr._build_menu(event)
    actions = {action.text(): action for action in menu.actions()}
    assert actions["Paste Graph Format"].isEnabled()
    actions["Paste Graph Format"].trigger()
    assert calls[-1] == ("paste", target_tab)


def test_graph_context_menu_exposes_text_editor_for_empty_labels(qapp):
    mgr, ax, _ = _manager_on_empty_axes(qapp)
    target_tab = object()
    calls = []

    class MainStub:
        def open_plot_details_dialog(self):
            pass

        def _graph_tab_for_figure(self, figure):
            assert figure is ax.figure
            return target_tab

        def edit_graph_text(self, kind, tab, axes, legend_index=None):
            calls.append((kind, tab, axes, legend_index))

    mgr.main = MainStub()
    menu = mgr._build_menu(SimpleNamespace(xdata=0.5, ydata=0.5))
    edit_action = next(action for action in menu.actions() if action.text() == "Edit Text")
    edit_menu = edit_action.menu()
    actions = {action.text(): action for action in edit_menu.actions()}
    assert {"Graph Title…", "X Axis Label…", "Y Axis Label…"} <= set(actions)

    # This route remains usable when the label is empty and therefore has no
    # rendered bounding box to double-click.
    assert ax.get_xlabel() == ""
    actions["X Axis Label…"].trigger()
    assert calls == [("xlabel", target_tab, ax, None)]


def test_context_format_toggles_join_graph_undo_history(qapp):
    from widgets.plot_tabs import GraphTab

    tab = GraphTab("context-history")
    try:
        ax = tab.get_axes()
        ax.plot([0, 1], [1, 2])
        tab.draw()

        class MainStub:
            def _graph_tab_for_figure(self, figure):
                assert figure is tab.get_figure()
                return tab

        manager = ContextMenuManager(tab.canvas, ax, main=MainStub())
        before = any(line.get_visible() for line in ax.get_xgridlines())
        tab.graph_undo_stack.clear()
        manager._on_toggle_grid()

        assert tab.graph_undo_stack.count() == 1
        assert any(line.get_visible() for line in ax.get_xgridlines()) is not before
        tab.graph_undo_stack.undo()
        assert any(line.get_visible() for line in ax.get_xgridlines()) is before
    finally:
        tab.close()
