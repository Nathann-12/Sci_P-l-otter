"""Behavioral tests for analysis.cleaning (ROADMAP section B)."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.cleaning import (
    baseline_subtract,
    detect_outliers,
    detrend_polynomial,
    fill_missing,
    interpolate_missing,
    normalize_column,
    remove_duplicates,
    remove_outliers,
    resample_uniform,
    sort_dataframe,
    summarize_anomalies,
)


# ---------- fill_missing ----------

def test_fill_missing_with_value():
    df = pd.DataFrame({"y": [1.0, np.nan, 3.0]})
    col = fill_missing(df, "y", method="value", value=-1.0)
    assert col == "y_filled"
    assert df[col].tolist() == [1.0, -1.0, 3.0]


def test_fill_missing_mean_and_median():
    df = pd.DataFrame({"y": [1.0, np.nan, 5.0, np.nan, 3.0]})
    mean_col = fill_missing(df, "y", method="mean", new_col="m")
    med_col = fill_missing(df, "y", method="median", new_col="md")
    assert df[mean_col].iloc[1] == pytest.approx(3.0)  # mean of 1,5,3
    assert df[med_col].iloc[3] == pytest.approx(3.0)   # median of 1,5,3


def test_fill_missing_ffill_bfill():
    df = pd.DataFrame({"y": [np.nan, 2.0, np.nan, 4.0]})
    f = fill_missing(df, "y", method="ffill", new_col="f")
    b = fill_missing(df, "y", method="bfill", new_col="b")
    assert df[f].tolist()[1:] == [2.0, 2.0, 4.0] and np.isnan(df[f].iloc[0])
    assert df[b].tolist() == [2.0, 2.0, 4.0, 4.0]


def test_fill_missing_rejects_bad_method_and_missing_value():
    df = pd.DataFrame({"y": [1.0]})
    with pytest.raises(ValueError):
        fill_missing(df, "y", method="nope")
    with pytest.raises(ValueError):
        fill_missing(df, "y", method="value")


# ---------- interpolate_missing ----------

def test_interpolate_missing_linear_gap():
    df = pd.DataFrame({"y": [0.0, np.nan, np.nan, 3.0]})
    col = interpolate_missing(df, "y")
    assert df[col].tolist() == pytest.approx([0.0, 1.0, 2.0, 3.0])


# ---------- duplicates ----------

def test_remove_duplicates_counts_and_keeps_first():
    df = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": [9, 9, 8, 7, 6]})
    out, removed = remove_duplicates(df)
    assert removed == 1  # only the (1, 9) pair repeats fully
    assert len(out) == 4
    out2, removed2 = remove_duplicates(df, subset=["a"])
    assert removed2 == 2
    assert out2["a"].tolist() == [1, 2, 3]


# ---------- outliers ----------

def test_detect_outliers_zscore_flags_spike():
    values = [1.0] * 20 + [1000.0]
    mask = detect_outliers(pd.Series(values), method="zscore", threshold=3.0)
    assert bool(mask.iloc[-1]) is True
    assert int(mask.sum()) == 1


def test_detect_outliers_iqr_flags_spike_but_not_normal_points():
    values = list(range(20)) + [500]
    mask = detect_outliers(pd.Series(values), method="iqr")
    assert bool(mask.iloc[-1]) is True
    assert int(mask.sum()) == 1


def test_detect_outliers_constant_series_flags_nothing():
    mask = detect_outliers(pd.Series([5.0] * 10), method="zscore")
    assert int(mask.sum()) == 0


def test_remove_outliers_drops_rows():
    df = pd.DataFrame({"y": [1.0] * 10 + [999.0], "tag": list("abcdefghijk")})
    out, removed = remove_outliers(df, "y", method="zscore")
    assert removed == 1
    assert len(out) == 10
    assert 999.0 not in out["y"].tolist()


# ---------- anomaly report ----------

def test_summarize_anomalies_reports_position_value_and_score():
    values = [1.0] * 20 + [1000.0]
    report = summarize_anomalies(pd.Series(values), method="zscore", threshold=3.0)
    assert report["n_total"] == 21
    assert report["n_anomalies"] == 1
    assert report["points"][0]["index"] == 20
    assert report["points"][0]["value"] == 1000.0
    assert report["points"][0]["zscore"] > 3.0
    assert 0.0 < report["fraction"] < 1.0


def test_summarize_anomalies_orders_points_most_extreme_first():
    values = [1.0] * 30 + [20.0, 40.0]
    report = summarize_anomalies(pd.Series(values), method="zscore", threshold=2.0)
    assert report["n_anomalies"] == 2
    # 40 is more extreme than 20 -> reported first
    assert report["points"][0]["value"] == 40.0
    assert report["points"][0]["zscore"] >= report["points"][1]["zscore"]


def test_summarize_anomalies_constant_series_reports_none():
    report = summarize_anomalies(pd.Series([5.0] * 10), method="zscore")
    assert report["n_anomalies"] == 0
    assert report["points"] == []


def test_summarize_anomalies_rejects_unknown_method():
    with pytest.raises(ValueError):
        summarize_anomalies(pd.Series([1.0, 2.0, 3.0]), method="bogus")


# ---------- normalize ----------

def test_normalize_zscore_gives_zero_mean_unit_std():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0, 5.0]})
    col = normalize_column(df, "y", method="zscore")
    assert df[col].mean() == pytest.approx(0.0, abs=1e-12)
    assert df[col].std() == pytest.approx(1.0)


def test_normalize_minmax_maps_to_unit_interval():
    df = pd.DataFrame({"y": [10.0, 20.0, 30.0]})
    col = normalize_column(df, "y", method="minmax")
    assert df[col].tolist() == pytest.approx([0.0, 0.5, 1.0])


def test_normalize_rejects_constant_column():
    df = pd.DataFrame({"y": [7.0, 7.0]})
    with pytest.raises(ValueError):
        normalize_column(df, "y", method="zscore")
    with pytest.raises(ValueError):
        normalize_column(df, "y", method="minmax")


# ---------- detrend / baseline ----------

def test_detrend_polynomial_zeroes_pure_linear_data():
    x = np.arange(50, dtype=float)
    df = pd.DataFrame({"x": x, "y": 2.0 * x + 5.0})
    col = detrend_polynomial(df, "y", order=1, x_col="x")
    assert np.allclose(df[col].to_numpy(), 0.0, atol=1e-9)


def test_detrend_polynomial_leaves_no_residual_slope():
    x = np.arange(200, dtype=float)
    df = pd.DataFrame({"x": x, "y": np.sin(x / 3.0) + (2.0 * x + 5.0)})
    col = detrend_polynomial(df, "y", order=1, x_col="x")
    resid = df[col].to_numpy()
    # least squares guarantees the residual has no remaining linear component
    slope = np.polyfit(x, resid, 1)[0]
    assert abs(slope) < 1e-9
    # and the huge trend (max ~405) is gone: residual stays sine-sized
    assert np.max(np.abs(resid)) < 1.5


def test_baseline_subtract_alias_removes_quadratic_baseline():
    # narrow peak over a wide window: the quadratic fit tracks the baseline
    x = np.linspace(-20, 20, 400)
    peak = np.exp(-x**2)
    df = pd.DataFrame({"x": x, "y": peak + (0.3 * x**2 - x + 2.0)})
    col = baseline_subtract(df, "y", order=2, x_col="x")
    resid = df[col].to_numpy()
    # baseline swings over ~140 units; after subtraction the residual must be
    # peak-sized and track the peak closely
    assert resid.max() == pytest.approx(1.0, abs=0.15)
    assert np.max(np.abs(resid - peak)) < 0.15


def test_detrend_polynomial_needs_enough_points():
    df = pd.DataFrame({"y": [1.0, np.nan]})
    with pytest.raises(ValueError):
        detrend_polynomial(df, "y", order=2)


# ---------- resample / sort ----------

def test_resample_uniform_produces_even_grid_and_exact_linear_values():
    # y = 2x is preserved exactly by linear interpolation
    df = pd.DataFrame({"x": [0.0, 1.0, 4.0, 9.0], "y": [0.0, 2.0, 8.0, 18.0]})
    out = resample_uniform(df, "x", n_points=10)
    dx = np.diff(out["x"].to_numpy())
    assert np.allclose(dx, dx[0])
    assert np.allclose(out["y"].to_numpy(), 2.0 * out["x"].to_numpy())


def test_resample_uniform_handles_unsorted_x():
    df = pd.DataFrame({"x": [9.0, 0.0, 4.0, 1.0], "y": [18.0, 0.0, 8.0, 2.0]})
    out = resample_uniform(df, "x", n_points=5)
    assert out["x"].iloc[0] == pytest.approx(0.0)
    assert out["x"].iloc[-1] == pytest.approx(9.0)
    assert np.allclose(out["y"].to_numpy(), 2.0 * out["x"].to_numpy())


def test_sort_dataframe_orders_rows():
    df = pd.DataFrame({"x": [3, 1, 2], "y": ["c", "a", "b"]})
    out = sort_dataframe(df, "x")
    assert out["x"].tolist() == [1, 2, 3]
    assert out["y"].tolist() == ["a", "b", "c"]
    desc = sort_dataframe(df, "x", ascending=False)
    assert desc["x"].tolist() == [3, 2, 1]
