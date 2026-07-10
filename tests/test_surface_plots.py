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

from plots import surface_plots


def _xyz_dataframe(rows: int = 160) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    x = rng.uniform(-2.0, 2.0, rows)
    y = rng.uniform(-2.0, 2.0, rows)
    z = np.sin(x * 1.5) * np.cos(y) + rng.normal(0.0, 0.04, rows)
    return pd.DataFrame({"x": x, "y": y, "z": z, "label": "sample"})


@pytest.mark.parametrize(
    "plotter",
    [surface_plots.filled_contour, surface_plots.contour_lines, surface_plots.heatmap],
)
def test_surface_plot_draws_content(plotter):
    figure, axes = plt.subplots()
    try:
        plotter(axes, _xyz_dataframe())
        assert axes.collections or axes.images
    finally:
        plt.close(figure)


@pytest.mark.parametrize("spec", surface_plots.PLOTS, ids=lambda spec: spec["key"])
def test_surface_plot_handles_empty_dataframe(spec):
    figure, axes = plt.subplots()
    try:
        spec["func"](axes, pd.DataFrame())
        assert axes.texts
    finally:
        plt.close(figure)


def test_contour_rejects_collinear_xyz_without_raising():
    dataframe = pd.DataFrame(
        {
            "x": [0.0, 1.0, 2.0, 3.0],
            "y": [0.0, 1.0, 2.0, 3.0],
            "z": [1.0, 2.0, 1.0, 2.0],
        }
    )
    figure, axes = plt.subplots()
    try:
        surface_plots.filled_contour(axes, dataframe)
        assert axes.texts
        assert "cannot form" in axes.texts[0].get_text()
    finally:
        plt.close(figure)


def test_surface_plot_catalog_contract():
    assert {entry["key"] for entry in surface_plots.PLOTS} == {
        "filled_contour",
        "contour_lines",
        "matrix_heatmap",
    }
    for entry in surface_plots.PLOTS:
        assert {
            "key", "title", "category", "func", "desc", "min_cols", "multi"
        } <= set(entry)
