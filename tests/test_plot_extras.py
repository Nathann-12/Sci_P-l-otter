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

from core.plot_extras import (
    add_secondary_y,
    draw_broken_axis,
    draw_error_bars,
    draw_fill_between,
)


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


def test_add_y_axis_layer_stacks_offset_colored_axes():
    from core.plot_extras import add_y_axis_layer, count_extra_y_axes

    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 3])
    assert count_extra_y_axes(ax) == 0

    ax2, l2 = add_y_axis_layer(ax, [0, 1, 2], [10, 20, 30], index=0,
                               color="#d62728", label="B", ylabel="B")
    assert count_extra_y_axes(ax) == 1
    assert ax2.get_shared_x_axes().joined(ax, ax2)

    ax3, l3 = add_y_axis_layer(ax, [0, 1, 2], [100, 400, 900], index=1,
                               color="#2ca02c", label="C", ylabel="C")
    assert count_extra_y_axes(ax) == 2
    # the 3rd axis' spine is pushed outward so scales don't overlap
    assert ax3.spines["right"].get_position() != ax2.spines["right"].get_position()
    # each layer keeps its own data + colour
    assert list(l2.get_ydata()) != list(l3.get_ydata())
    assert l2.get_color() == "#d62728" and l3.get_color() == "#2ca02c"
    plt.close(fig)


def test_add_y_axis_layer_auto_colours_differ_from_base():
    """Without an explicit colour each layer must pick a *distinct* colour — a
    fresh twinx() cycle otherwise restarts at C0 and every layer draws in the
    same blue (regression: live multi-axis was all-blue + all-blue axes)."""
    from core.plot_extras import add_y_axis_layer

    fig, ax = plt.subplots()
    (base_line,) = ax.plot([0, 1, 2], [1, 2, 3])          # base = C0
    ax2, l2 = add_y_axis_layer(ax, [0, 1, 2], [10, 20, 30], index=0, ylabel="B")  # no colour
    ax3, l3 = add_y_axis_layer(ax, [0, 1, 2], [5, 4, 3], index=1, ylabel="C")     # no colour

    colours = {base_line.get_color(), l2.get_color(), l3.get_color()}
    assert len(colours) == 3                               # no all-blue collapse
    # the colour-matched axis/ticks follow the curve colour
    assert ax2.yaxis.get_label().get_color() == l2.get_color()
    assert ax3.yaxis.get_label().get_color() == l3.get_color()
    plt.close(fig)


def test_reserve_layer_margins_shrinks_right_edge():
    from core.plot_extras import add_y_axis_layer, reserve_layer_margins

    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 3])
    add_y_axis_layer(ax, [0, 1, 2], [10, 20, 30], index=0)
    add_y_axis_layer(ax, [0, 1, 2], [100, 400, 900], index=1)
    reserve_layer_margins(fig)
    # room reserved for the pushed-out spine + its colour-matched label
    assert fig.subplotpars.right < 0.85
    plt.close(fig)


def test_draw_broken_y_axis_splits_line_plot():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2, 3], [1, 2, 50, 60], label="signal")
    ax.set_xlabel("time")
    ax.set_ylabel("value")

    top, bottom = draw_broken_axis(ax, "y", 3.0, 40.0)

    assert len(fig.axes) == 2
    assert top in fig.axes and bottom in fig.axes
    assert top.get_ylim()[0] == pytest.approx(40.0)
    assert bottom.get_ylim()[1] == pytest.approx(3.0)
    assert any(line.get_label() == "signal" for line in top.lines)
    assert bottom.get_xlabel() == "time"
    plt.close(fig)


def test_draw_broken_x_axis_splits_line_plot():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 50, 60], [1, 2, 3, 4], label="signal")

    left, right = draw_broken_axis(ax, "x", 3.0, 40.0)

    assert len(fig.axes) == 2
    assert left.get_xlim()[1] == pytest.approx(3.0)
    assert right.get_xlim()[0] == pytest.approx(40.0)
    plt.close(fig)


def test_draw_broken_axis_rejects_out_of_range_break():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 3])
    with pytest.raises(ValueError):
        draw_broken_axis(ax, "y", 10.0, 20.0)
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


def test_plot_y_axis_layer_stacks_on_current_graph(win):
    from core.plot_extras import count_extra_y_axes

    _load(win)
    win.plot_from_workbook("line")  # primary curve first
    n = win.tabs.count()
    base = win.tabs.currentWidget().get_axes()
    seq = [{"x": "t", "y": "y2"}, {"x": "t", "y": "err"}]
    calls = {"i": 0}

    def fake_form(*a, **k):
        r = seq[calls["i"]]
        calls["i"] += 1
        return r

    win.ask_form = fake_form
    win.plot_y_axis_layer()
    win.plot_y_axis_layer()

    fig = win.tabs.currentWidget().get_figure()
    assert win.tabs.count() == n                       # no new graph
    assert count_extra_y_axes(base) == 2               # two stacked layers
    assert len(fig.axes) >= 3
    # right margin reserved so the pushed-out spine/label isn't clipped
    assert fig.subplotpars.right < 0.85
    # each layer draws in a distinct colour (not all C0 blue)
    line_colours = [a.get_lines()[0].get_color() for a in fig.axes if a.get_lines()]
    assert len(set(line_colours)) == len(line_colours)


def test_plot_y_axis_layer_needs_a_primary_curve(win):
    _load(win)
    win.tabs.add_tab()  # empty graph, no curve
    infos = []
    win.inform = lambda t, x: infos.append(t)
    win.plot_y_axis_layer()
    assert infos  # politely refused, no crash


def test_plot_broken_axis_splits_current_graph_without_new_graph(win):
    _load(win)
    win.plot_from_workbook("line")
    n = win.tabs.count()
    messages = []
    win.ask_form = lambda *a, **k: {"axis": "Y", "lower": 2.1, "upper": 3.1}
    win.notify = lambda msg, *a, **k: messages.append(msg)

    win.plot_broken_axis()

    tab = win.tabs.currentWidget()
    assert win.tabs.count() == n
    assert len(tab.get_figure().axes) == 2
    assert tab.canvas.ax in tab.get_figure().axes
    assert messages == ["Broken Y axis applied"]
