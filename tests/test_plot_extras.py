"""Tests for extra plot types (core.plot_extras) + the plotextra mixin
end-to-end through the real MainWindow."""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.plot_extras import add_secondary_y, draw_error_bars, draw_fill_between


# ---------------- pure helpers ----------------

def test_draw_error_bars_creates_container():
    fig, ax = plt.subplots()
    cont = draw_error_bars(ax, [0, 1, 2], [1, 2, 3], [0.1, 0.2, 0.1], label="y")
    assert cont is not None
    # errorbar container has line + error segments
    assert len(ax.containers) == 1
    plt.close(fig)


def test_draw_error_bars_with_xerr_and_nan_filtering():
    fig, ax = plt.subplots()
    draw_error_bars(ax, [0, 1, np.nan, 3], [1, 2, 3, 4],
                    [0.1, 0.1, 0.1, 0.1], xerr=[0.05, 0.05, 0.05, 0.05])
    assert len(ax.containers) == 1
    plt.close(fig)


def test_draw_fill_between():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    poly = draw_fill_between(ax, x, x - 0.1, x + 0.1, label="band", alpha=0.4)
    assert poly is not None
    assert len(ax.collections) == 1
    plt.close(fig)


def test_add_secondary_y_twins_axis_and_colors():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 3])
    ax2, line = add_secondary_y(ax, [0, 1, 2], [10, 20, 30],
                                label="right", ylabel="Right")
    assert ax2 is not ax
    assert ax2.get_ylabel() == "Right"
    # the two share the x axis
    assert ax2.get_shared_x_axes().joined(ax, ax2)
    plt.close(fig)


def test_clean_raises_on_all_nan():
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        draw_fill_between(ax, [np.nan, np.nan], [1, 2], [3, 4])
    plt.close(fig)


# ---------------- mixin through MainWindow ----------------

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def _load(win):
    df = pd.DataFrame({
        "t": [0.0, 1.0, 2.0, 3.0],
        "y": [1.0, 2.0, 3.0, 4.0],
        "err": [0.1, 0.2, 0.1, 0.2],
        "y2": [10.0, 20.0, 30.0, 40.0],
    })
    win._stage_insert("e.csv [ตาราง]", df, None)


def test_plot_error_bars_opens_new_graph(win):
    _load(win)
    win.ask_form = lambda *a, **k: {"x": "t", "y": "y", "yerr": "err", "xerr": "(none)"}
    n = win.tabs.count()
    win.plot_error_bars()
    assert win.tabs.count() == n + 1
    assert len(win.tabs.currentWidget().get_axes().containers) == 1


def test_plot_fill_between_opens_new_graph(win):
    _load(win)
    win.ask_form = lambda *a, **k: {"x": "t", "y1": "y", "y2": "y2", "alpha": 0.3}
    n = win.tabs.count()
    win.plot_fill_between()
    assert win.tabs.count() == n + 1
    assert len(win.tabs.currentWidget().get_axes().collections) >= 1


def test_plot_secondary_axis_adds_to_current(win):
    _load(win)
    win.plot_from_workbook("line")  # primary curve first
    n = win.tabs.count()
    win.ask_form = lambda *a, **k: {"x": "t", "y2": "y2"}
    win.plot_secondary_axis()
    assert win.tabs.count() == n  # no new graph — added to current
    # the figure now has two axes (twinned)
    assert len(win.tabs.currentWidget().get_figure().axes) == 2
