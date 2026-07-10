import os, sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np, pandas as pd, pytest
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plots import dist_plots


def _synth_df(n=200):
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "normal": rng.normal(0.0, 1.0, n),
        "skewed": rng.exponential(2.0, n),
        "shifted": rng.normal(5.0, 2.0, n) + rng.gamma(2.0, 1.0, n),
    })


def _axes_has_content(ax):
    if len(ax.get_children()) > 10:
        return True
    return bool(ax.lines) or bool(ax.collections) or bool(ax.patches)


@pytest.mark.parametrize("spec", dist_plots.PLOTS, ids=[s["key"] for s in dist_plots.PLOTS])
def test_plot_draws_content(spec):
    df = _synth_df()
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise
        assert _axes_has_content(ax), f"{spec['key']} drew nothing"
    finally:
        plt.close(fig)


@pytest.mark.parametrize("spec", dist_plots.PLOTS, ids=[s["key"] for s in dist_plots.PLOTS])
def test_plot_empty_df_placeholder(spec):
    df = pd.DataFrame()
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise
        assert ax.texts, f"{spec['key']} did not draw a placeholder message"
    finally:
        plt.close(fig)


def test_plots_registry_valid():
    keys = [s["key"] for s in dist_plots.PLOTS]
    assert len(keys) == len(set(keys)), "duplicate keys in PLOTS"
    required = {"key", "title", "category", "func", "desc", "min_cols", "multi"}
    for spec in dist_plots.PLOTS:
        assert required <= set(spec), f"{spec.get('key')} missing keys"
        assert callable(spec["func"])
        assert spec["multi"] is False
        assert isinstance(spec["min_cols"], int) and spec["min_cols"] >= 1


def test_single_column_df_does_not_crash():
    df = pd.DataFrame({"only": np.random.default_rng(0).normal(size=150)})
    for spec in dist_plots.PLOTS:
        fig, ax = plt.subplots()
        try:
            spec["func"](ax, df)  # must not raise regardless of min_cols
        finally:
            plt.close(fig)
