from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from matplotlib.figure import Figure
import numpy as np
import pandas as pd
import pytest

from plots import basic_extra_plots


@pytest.fixture()
def sample_df() -> pd.DataFrame:
    rng = np.random.default_rng(401)
    x = np.linspace(0.0, 10.0, 90)
    return pd.DataFrame(
        {
            "X": x,
            "Y": 2.0 + 0.7 * x + rng.normal(0.0, 0.6, x.size),
            "Uncertainty": rng.uniform(0.15, 0.5, x.size),
            "Bubble color": rng.normal(5.0, 1.0, x.size),
        }
    )


@pytest.mark.parametrize("spec", basic_extra_plots.PLOTS, ids=lambda spec: spec["key"])
def test_extra_2d_plot_draws_visible_artists(spec, sample_df):
    figure = Figure()
    axes = figure.add_subplot(111)

    spec["func"](axes, sample_df)

    assert axes.lines or axes.collections or axes.patches or axes.containers
    assert axes.get_title()


def test_extra_2d_registry_contract_is_unique():
    keys = [entry["key"] for entry in basic_extra_plots.PLOTS]
    assert len(keys) == len(set(keys))
    assert {"step_plot", "stem_plot", "error_bar_plot", "bubble_plot", "hexbin_plot"} == set(keys)
    assert all(entry["category"] == "Basic 2D" for entry in basic_extra_plots.PLOTS)


@pytest.mark.parametrize("spec", basic_extra_plots.PLOTS, ids=lambda spec: spec["key"])
def test_extra_2d_plot_handles_missing_columns(spec):
    figure = Figure()
    axes = figure.add_subplot(111)

    spec["func"](axes, pd.DataFrame({"label": ["A", "B"]}))

    assert axes.texts
