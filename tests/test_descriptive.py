"""Behavioral tests for analysis.descriptive (ROADMAP section D)."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.descriptive import covariance_matrix, describe_series, format_describe


def test_describe_series_known_values():
    s = pd.Series([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    stats = describe_series(s)
    assert stats["count"] == 8
    assert stats["mean"] == pytest.approx(5.0)
    assert stats["median"] == pytest.approx(4.5)
    assert stats["mode"] == pytest.approx(4.0)
    assert stats["variance"] == pytest.approx(s.var())
    assert stats["std"] == pytest.approx(s.std())
    assert stats["skewness"] == pytest.approx(s.skew())
    assert stats["kurtosis"] == pytest.approx(s.kurt())
    assert stats["min"] == 2.0 and stats["max"] == 9.0


def test_describe_series_ignores_nan_and_rejects_empty():
    s = pd.Series([1.0, np.nan, 3.0])
    assert describe_series(s)["count"] == 2
    with pytest.raises(ValueError):
        describe_series(pd.Series([np.nan, np.nan]))
    with pytest.raises(ValueError):
        describe_series(pd.Series(["a", "b"]))


def test_covariance_matrix_matches_pandas_and_is_symmetric():
    rng = np.random.default_rng(11)
    df = pd.DataFrame({
        "a": rng.normal(size=100),
        "b": rng.normal(size=100),
        "label": ["x"] * 100,  # non-numeric must be ignored
    })
    cov = covariance_matrix(df)
    assert list(cov.columns) == ["a", "b"]
    assert cov.loc["a", "b"] == pytest.approx(cov.loc["b", "a"])
    assert cov.loc["a", "a"] == pytest.approx(df["a"].var())


def test_covariance_matrix_needs_two_numeric_columns():
    with pytest.raises(ValueError):
        covariance_matrix(pd.DataFrame({"a": [1.0, 2.0], "s": ["x", "y"]}))


def test_format_describe_renders_all_keys():
    stats = describe_series(pd.Series([1.0, 2.0, 3.0]))
    text = format_describe(stats, title="y")
    assert text.startswith("y")
    for key in ("count", "mean", "median", "mode", "std", "variance",
                "skewness", "kurtosis", "min", "max"):
        assert key in text
