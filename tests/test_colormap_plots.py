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
from matplotlib.collections import LineCollection
import numpy as np
import pandas as pd
import pytest

from plots import colormap_plots
from plots.registry import all_plots


@pytest.fixture()
def ax():
    fig, axes = plt.subplots()
    yield axes
    plt.close(fig)


def test_registered_in_the_gallery():
    keys = {p["key"] for p in all_plots()}
    assert "color_mapped_line" in keys
    assert "color_mapped_line_markers" in keys


def test_third_column_drives_the_color_and_a_colorbar_appears(ax):
    n = 200
    t = np.linspace(0, 10, n)
    df = pd.DataFrame({"x": t, "y": np.sin(t), "z": t})
    colormap_plots.color_mapped_line(ax, df)

    lcs = [c for c in ax.collections if isinstance(c, LineCollection)]
    assert len(lcs) == 1
    # one colour value per segment, spanning the z range
    arr = lcs[0].get_array()
    assert arr is not None and len(arr) == n - 1
    assert lcs[0].get_clim() == pytest.approx((float(df.z.min()), float(df.z.max())))
    # colourbar axes added to the figure
    assert len(ax.figure.axes) > 1
    assert ax.get_xlabel() == "x" and ax.get_ylabel() == "y"


def test_two_columns_map_color_to_y(ax):
    df = pd.DataFrame({"t": np.linspace(0, 5, 60), "sig": np.cos(np.linspace(0, 5, 60))})
    colormap_plots.color_mapped_line(ax, df)
    lc = next(c for c in ax.collections if isinstance(c, LineCollection))
    assert lc.get_clim() == pytest.approx((float(df.sig.min()), float(df.sig.max())))


def test_markers_variant_adds_a_scatter(ax):
    df = pd.DataFrame({"t": np.linspace(0, 5, 40), "sig": np.linspace(0, 1, 40)})
    colormap_plots.color_mapped_line_markers(ax, df)
    # LineCollection + a PathCollection (scatter)
    assert any(isinstance(c, LineCollection) for c in ax.collections)
    assert len(ax.collections) >= 2


def test_single_column_uses_row_index_as_x(ax):
    df = pd.DataFrame({"v": np.linspace(0, 10, 30)})
    colormap_plots.color_mapped_line(ax, df)
    assert ax.get_xlabel() == "Row"
    assert any(isinstance(c, LineCollection) for c in ax.collections)


def test_degenerate_input_draws_placeholder_without_crashing(ax):
    colormap_plots.color_mapped_line(ax, pd.DataFrame({"a": [1.0]}))       # 1 point
    colormap_plots.color_mapped_line(ax, pd.DataFrame({"s": ["a", "b"]}))  # non-numeric
    assert not [c for c in ax.collections if isinstance(c, LineCollection)]
