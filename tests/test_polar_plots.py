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

from plots import polar_plots


def _polar_axes():
    figure = plt.figure()
    return figure, figure.add_subplot(111, projection="polar")


def test_polar_line_converts_degree_angles_and_draws_each_radius_column():
    dataframe = pd.DataFrame(
        {
            "angle_deg": [0.0, 90.0, 180.0, 270.0],
            "r1": [1.0, 2.0, 3.0, 4.0],
            "r2": [2.0, 3.0, 4.0, 5.0],
        }
    )
    figure, axes = _polar_axes()
    try:
        polar_plots.polar_line(axes, dataframe)

        assert axes.name == "polar"
        assert len(axes.lines) == 2
        np.testing.assert_allclose(axes.lines[0].get_xdata(), np.deg2rad(dataframe["angle_deg"]))
        np.testing.assert_allclose(axes.lines[0].get_ydata(), dataframe["r1"])
    finally:
        plt.close(figure)


def test_polar_scatter_single_numeric_column_uses_even_angles():
    dataframe = pd.DataFrame({"radius": [1.0, 2.0, 3.0, 4.0]})
    figure, axes = _polar_axes()
    try:
        polar_plots.polar_scatter(axes, dataframe)

        assert len(axes.collections) == 1
        offsets = axes.collections[0].get_offsets()
        np.testing.assert_allclose(offsets[:, 0], np.linspace(0.0, 2.0 * np.pi, 4, endpoint=False))
        np.testing.assert_allclose(offsets[:, 1], dataframe["radius"])
    finally:
        plt.close(figure)


def test_wind_rose_uses_weighted_direction_bins():
    dataframe = pd.DataFrame(
        {
            "angle": [0.0, 0.1, np.pi, np.pi + 0.1],
            "magnitude": [1.0, 3.0, 2.0, 4.0],
        }
    )
    figure, axes = _polar_axes()
    try:
        polar_plots.wind_rose(axes, dataframe)

        assert axes.patches
        heights = [patch.get_height() for patch in axes.patches]
        assert max(heights) >= 4.0
        assert axes.get_title() == "Wind Rose"
    finally:
        plt.close(figure)


@pytest.mark.parametrize("spec", polar_plots.PLOTS, ids=lambda spec: spec["key"])
def test_polar_plot_handles_empty_dataframe(spec):
    figure, axes = _polar_axes()
    try:
        spec["func"](axes, pd.DataFrame())
        assert axes.texts
    finally:
        plt.close(figure)


def test_polar_catalog_contract():
    assert {entry["key"] for entry in polar_plots.PLOTS} == {
        "polar_line",
        "polar_scatter",
        "wind_rose",
    }
    for entry in polar_plots.PLOTS:
        assert entry["category"] == "Polar"
        assert entry["projection"] == "polar"
