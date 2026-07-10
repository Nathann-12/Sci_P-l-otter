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
from plots import rel_plots


REQUIRED_KEYS = {"key", "title", "category", "func", "desc", "min_cols", "multi"}


def _synthetic_df(rows: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    a = rng.normal(0.0, 1.0, rows)
    b = a * 0.8 + rng.normal(0.0, 0.4, rows)      # correlated with a
    c = a * -0.5 + b * 0.3 + rng.normal(0.0, 0.5, rows)
    return pd.DataFrame({"colA": a, "colB": b, "colC": c})


def _has_content(fig, ax, multi: bool) -> bool:
    if multi:
        return len(fig.axes) > 1
    if ax.lines or ax.collections or ax.images:
        return True
    return len(ax.get_children()) > 8


@pytest.mark.parametrize("spec", rel_plots.PLOTS, ids=[s["key"] for s in rel_plots.PLOTS])
def test_plot_produces_content(spec):
    df = _synthetic_df()
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise
        assert _has_content(fig, ax, spec["multi"]), f"{spec['key']} produced no content"
    finally:
        plt.close(fig)


@pytest.mark.parametrize("spec", rel_plots.PLOTS, ids=[s["key"] for s in rel_plots.PLOTS])
def test_plot_handles_empty_df(spec):
    df = pd.DataFrame()
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise on empty input
    finally:
        plt.close(fig)


@pytest.mark.parametrize("spec", rel_plots.PLOTS, ids=[s["key"] for s in rel_plots.PLOTS])
def test_plot_handles_single_column(spec):
    df = pd.DataFrame({"only": np.linspace(0, 1, 50)})
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise even when below min_cols
    finally:
        plt.close(fig)


def test_plots_catalog_valid():
    keys = [s["key"] for s in rel_plots.PLOTS]
    assert len(keys) == len(set(keys)), "PLOTS keys must be unique"
    for spec in rel_plots.PLOTS:
        assert REQUIRED_KEYS.issubset(spec.keys()), f"{spec} missing keys"
        assert callable(spec["func"]), f"{spec['key']} func not callable"
        assert isinstance(spec["min_cols"], int)
        assert isinstance(spec["multi"], bool)


def test_expected_keys_present():
    keys = {s["key"] for s in rel_plots.PLOTS}
    expected = {
        "corr_heatmap", "scatter_matrix", "qq_plot", "probability_plot",
        "cdf_plot", "pp_plot", "bland_altman", "paired_comparison", "residual_plot",
    }
    assert expected == keys
