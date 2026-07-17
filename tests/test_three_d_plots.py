from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure
import numpy as np
import pandas as pd
import pytest

from plots import three_d_plots


@pytest.fixture()
def xyz_df() -> pd.DataFrame:
    grid = np.linspace(-2.5, 2.5, 15)
    x, y = np.meshgrid(grid, grid)
    z = np.sin(np.hypot(x, y) * 2.0) * np.exp(-0.16 * (x**2 + y**2))
    return pd.DataFrame({"X": x.ravel(), "Y": y.ravel(), "Z": z.ravel()})


@pytest.mark.parametrize("spec", three_d_plots.PLOTS, ids=lambda spec: spec["key"])
def test_three_d_plot_draws_on_real_3d_axes(spec, xyz_df):
    figure = Figure()
    axes = figure.add_subplot(111, projection="3d")

    spec["func"](axes, xyz_df)

    assert axes.name == "3d"
    assert axes.lines or axes.collections or axes.patches or axes.containers
    assert axes.get_title()
    assert axes.get_xlabel() == "X"
    assert axes.get_ylabel() == "Y"
    assert axes.get_zlabel() == "Z"


def test_three_d_registry_contract_and_variety():
    keys = [entry["key"] for entry in three_d_plots.PLOTS]
    assert len(keys) == len(set(keys))
    assert len(keys) >= 8
    assert {
        "scatter_3d",
        "trajectory_3d",
        "stem_3d",
        "bar_3d",
        "surface_3d",
        "wireframe_3d",
        "contour_3d",
        "trisurface_3d",
    } == set(keys)
    assert all(entry["category"] == "3D" for entry in three_d_plots.PLOTS)
    assert all(entry["projection"] == "3d" for entry in three_d_plots.PLOTS)


@pytest.mark.parametrize("spec", three_d_plots.PLOTS, ids=lambda spec: spec["key"])
def test_three_d_plot_handles_insufficient_data(spec):
    figure = Figure()
    axes = figure.add_subplot(111, projection="3d")

    spec["func"](axes, pd.DataFrame({"X": [1.0, 2.0], "Y": [2.0, 3.0]}))

    assert axes.texts
