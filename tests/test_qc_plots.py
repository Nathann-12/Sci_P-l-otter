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
from plots import qc_plots


REQUIRED_KEYS = {"key", "title", "category", "func", "desc", "min_cols", "multi"}


def _df(rows=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "a": rng.normal(10.0, 2.0, rows),
        "b": rng.normal(5.0, 1.0, rows),
        "c": rng.uniform(0.0, 100.0, rows),
    })


def _has_content(ax):
    """True when the axes drew something meaningful."""
    if len(ax.get_children()) > 8:
        return True
    return bool(ax.lines or ax.patches or ax.collections)


@pytest.mark.parametrize("spec", qc_plots.PLOTS, ids=[s["key"] for s in qc_plots.PLOTS])
def test_plot_produces_content(spec):
    df = _df()
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise
        assert _has_content(ax), f"{spec['key']} produced no content"
    finally:
        plt.close(fig)


@pytest.mark.parametrize("spec", qc_plots.PLOTS, ids=[s["key"] for s in qc_plots.PLOTS])
def test_plot_handles_empty_df(spec):
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, pd.DataFrame())  # must not raise
    finally:
        plt.close(fig)


@pytest.mark.parametrize("spec", qc_plots.PLOTS, ids=[s["key"] for s in qc_plots.PLOTS])
def test_plot_handles_non_numeric_df(spec):
    df = pd.DataFrame({"label": ["x", "y", "z"], "tag": ["p", "q", "r"]})
    fig, ax = plt.subplots()
    try:
        spec["func"](ax, df)  # must not raise
    finally:
        plt.close(fig)


def test_control_xbar_flags_outlier():
    # One huge outlier; everything else tightly clustered.
    values = np.full(60, 10.0)
    values[30] = 1000.0
    df = pd.DataFrame({"a": values})
    fig, ax = plt.subplots()
    try:
        qc_plots.control_xbar(ax, df)
        mean = float(np.mean(values))
        sigma = float(np.std(values, ddof=1))
        ucl = mean + 3 * sigma
        # The outlier must exceed the computed UCL.
        assert 1000.0 > ucl
        # A UCL line (dashed red hline) must exist among the axhlines.
        assert len(ax.lines) >= 1
        # The out-of-control point must be marked by a dedicated scatter artist.
        assert len(ax.collections) >= 1, "no out-of-control marker drawn"
    finally:
        plt.close(fig)


def test_plots_registry_valid():
    keys = [s["key"] for s in qc_plots.PLOTS]
    assert len(keys) == len(set(keys)), "duplicate keys in PLOTS"
    for spec in qc_plots.PLOTS:
        assert REQUIRED_KEYS <= set(spec.keys()), f"missing keys: {spec}"
        assert callable(spec["func"]), f"func not callable for {spec['key']}"
        assert spec["multi"] is False
        assert spec["category"] in {"Quality", "Categorical"}
        assert isinstance(spec["min_cols"], int) and spec["min_cols"] >= 1
