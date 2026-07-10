from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from plots import multicolumn_plots


def _multi_y_dataframe(rows: int = 100) -> pd.DataFrame:
    x = np.linspace(0.0, 8.0, rows)
    return pd.DataFrame(
        {
            "time": x,
            "signal_a": np.sin(x),
            "signal_b": np.cos(x) * 2,
            "signal_c": np.sin(x * 0.5) * 0.5,
        }
    )


def test_stacked_lines_draws_every_y_column_with_offsets():
    figure, axes = plt.subplots()
    try:
        multicolumn_plots.stacked_lines_y_offset(axes, _multi_y_dataframe())

        assert len(axes.lines) == 3
        starts = [line.get_ydata()[0] for line in axes.lines]
        assert starts[1] > starts[0]
        assert starts[2] > starts[1]
        assert axes.get_xlabel() == "time"
    finally:
        plt.close(figure)


def test_waterfall_draws_every_y_column_on_3d_planes():
    figure = plt.figure()
    axes = figure.add_subplot(111, projection="3d")
    try:
        multicolumn_plots.waterfall_3d(axes, _multi_y_dataframe())

        assert len(axes.lines) == 3
        assert axes.get_zlabel() == "Value"
        assert [tick.get_text() for tick in axes.get_yticklabels()] == [
            "signal_a",
            "signal_b",
            "signal_c",
        ]
    finally:
        plt.close(figure)


def test_subplot_grid_draws_each_y_column_on_separate_axes():
    figure, axes = plt.subplots()
    try:
        multicolumn_plots.subplot_grid(axes, _multi_y_dataframe())

        visible_axes = [axis for axis in figure.axes if axis.get_visible()]
        assert len(visible_axes) == 3
        assert [axis.get_title() for axis in visible_axes] == [
            "signal_a",
            "signal_b",
            "signal_c",
        ]
        assert all(len(axis.lines) == 1 for axis in visible_axes)
        assert all(axis.get_xlabel() == "time" for axis in visible_axes)
    finally:
        plt.close(figure)


@pytest.mark.parametrize("spec", multicolumn_plots.PLOTS, ids=lambda spec: spec["key"])
def test_multicolumn_plot_handles_empty_dataframe(spec):
    figure = plt.figure()
    axes = figure.add_subplot(
        111,
        projection="3d" if spec.get("is3d") else None,
    )
    try:
        spec["func"](axes, pd.DataFrame())
        assert axes.texts
    finally:
        plt.close(figure)


def test_single_numeric_column_uses_row_number_as_x():
    dataframe = pd.DataFrame({"signal": [1.0, 4.0, 2.0]})
    figure, axes = plt.subplots()
    try:
        multicolumn_plots.stacked_lines_y_offset(axes, dataframe)

        assert axes.lines[0].get_xdata().tolist() == [0.0, 1.0, 2.0]
        assert axes.get_xlabel() == "Row"
    finally:
        plt.close(figure)


def test_multicolumn_catalog_contract():
    assert {entry["key"] for entry in multicolumn_plots.PLOTS} == {
        "stacked_lines_y_offset",
        "waterfall_3d",
        "subplot_grid",
    }
    assert next(
        entry for entry in multicolumn_plots.PLOTS if entry["key"] == "waterfall_3d"
    )["is3d"] is True
    assert next(
        entry for entry in multicolumn_plots.PLOTS if entry["key"] == "subplot_grid"
    )["multi"] is True
