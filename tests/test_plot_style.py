"""Behavioral tests for core.plot_style (Origin-style graph customization)."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.plot_style import (
    apply_line_style,
    apply_style,
    read_line_style,
    read_style,
)


@pytest.fixture()
def ax():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9], label="series")
    yield ax
    plt.close(fig)


def test_apply_titles_labels_and_fonts(ax):
    apply_style(ax, {"axes": {
        "title": "My Graph", "title_size": 16,
        "xlabel": "Time (s)", "ylabel": "Signal", "label_size": 13}})
    assert ax.get_title() == "My Graph"
    assert ax.title.get_fontsize() == 16
    assert ax.get_xlabel() == "Time (s)"
    assert ax.get_ylabel() == "Signal"
    assert ax.xaxis.label.get_fontsize() == 13


def test_manual_limits_and_invert(ax):
    apply_style(ax, {"axes": {
        "x_autoscale": False, "xmin": 0, "xmax": 10,
        "y_autoscale": False, "ymin": 0, "ymax": 100, "invert_y": True}})
    assert ax.get_xlim() == (0.0, 10.0)
    # inverted y → hi, lo order
    ylo, yhi = ax.get_ylim()
    assert ylo == 100.0 and yhi == 0.0


def test_log_scale(ax):
    apply_style(ax, {"axes": {"yscale": "log"}})
    assert ax.get_yscale() == "log"
    apply_style(ax, {"axes": {"yscale": "linear"}})
    assert ax.get_yscale() == "linear"


def test_grid_major_toggle_and_color(ax):
    apply_style(ax, {"grid": {"major": True, "color": "#ff0000",
                              "linestyle": "--", "alpha": 0.5}})
    gl = ax.get_xgridlines()
    assert any(g.get_visible() for g in gl)
    apply_style(ax, {"grid": {"major": False}})
    assert not any(g.get_visible() for g in ax.get_xgridlines())


def test_legend_show_hide(ax):
    apply_style(ax, {"legend": {"visible": True, "loc": "upper left",
                                "fontsize": 12, "frame": False}})
    leg = ax.get_legend()
    assert leg is not None and leg.get_visible()
    apply_style(ax, {"legend": {"visible": False}})
    assert ax.get_legend() is None or not ax.get_legend().get_visible()


def test_read_apply_roundtrip(ax):
    apply_style(ax, {"axes": {"title": "T", "xlabel": "X", "ylabel": "Y",
                              "x_autoscale": False, "xmin": -1, "xmax": 5,
                              "yscale": "log"},
                     "grid": {"major": True}})
    captured = read_style(ax, ax.figure)
    # apply the captured style to a fresh axes → same key properties
    fig2, ax2 = plt.subplots()
    ax2.plot([1, 2], [1, 2], label="s")
    apply_style(ax2, captured, fig2)
    assert ax2.get_title() == "T"
    assert ax2.get_xlabel() == "X"
    assert ax2.get_yscale() == "log"
    assert ax2.get_xlim() == (-1.0, 5.0)
    plt.close(fig2)


def test_line_style_read_apply(ax):
    line = ax.get_lines()[0]
    apply_line_style(line, {"color": "#00ff00", "linewidth": 3.5,
                            "linestyle": "--", "marker": "o",
                            "markersize": 8, "alpha": 0.7, "label": "renamed"})
    assert line.get_linewidth() == 3.5
    assert line.get_linestyle() == "--"
    assert line.get_marker() == "o"
    assert line.get_markersize() == 8
    assert line.get_label() == "renamed"
    d = read_line_style(line)
    assert d["color"] == "#00ff00"
    assert d["linewidth"] == 3.5
    assert d["marker"] == "o"
    assert d["alpha"] == pytest.approx(0.7)


def test_apply_ignores_unknown_and_empty(ax):
    # must not raise on partial/empty styles
    apply_style(ax, {})
    apply_style(ax, {"axes": {}, "grid": {}, "legend": {}, "figure": {}})
    apply_style(ax, {"nonsense": {"x": 1}})
