"""Behavioral tests for feature actions, now possible headless because the
logic talks to the view-accessor seam (which we stub) instead of popping
real Qt dialogs."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main_window_features_mixin import MainWindowFeaturesMixin


class DummyFeatures(MainWindowFeaturesMixin):
    """Feature logic with the view seam stubbed — no real widgets/dialogs."""

    def __init__(self, df: pd.DataFrame, x_sel: str = "", y_sel: str = "",
                 choices=(), forms=()):
        self._df = df
        self._x_sel = x_sel
        self._y_sel = y_sel
        self._choices = iter(choices)
        self._forms = iter(forms)
        self.messages: list[str] = []
        self.errors: list[tuple] = []
        self.added_x: list[str] = []
        self.added_y: list[str] = []

    # --- stubbed view seam ---
    def inform(self, title, text):
        self.messages.append(f"info:{title}")

    def error_box(self, title, text):
        self.errors.append((title, text))

    def notify(self, msg, error=False):
        self.messages.append(msg)

    def x_column_count(self):
        return len(self._df.columns)

    def y_column_count(self):
        return len(self._df.columns)

    def selected_x_column(self):
        return self._x_sel

    def selected_y_column(self):
        return self._y_sel

    def selected_y_index(self):
        return 0

    def add_x_column_option(self, name):
        self.added_x.append(name)

    def add_y_column_option(self, name):
        self.added_y.append(name)

    def ask_choice(self, title, label, options, current=0):
        return next(self._choices)

    def ask_number(self, title, label, value=0.0, minimum=-1e12, maximum=1e12, decimals=4):
        return next(self._choices)

    def ask_int(self, title, label, value=0, minimum=-10**9, maximum=10**9, step=1):
        return next(self._choices)

    def ask_form(self, title, fields, description=None):
        return next(self._forms)

    def load_columns_from_df(self):
        self.messages.append("columns-reloaded")


def test_feature_add_moving_average_creates_column():
    df = pd.DataFrame({"t": range(60), "value": np.sin(np.linspace(0, 6, 60))})
    win = DummyFeatures(df, y_sel="value")

    win.feature_add_moving_average()

    assert not win.errors
    assert len(win.added_y) == 1
    new_col = win.added_y[0]
    assert new_col in win._df.columns
    assert any("Moving Average" in m for m in win.messages)


def test_feature_add_magnitude_creates_b_mag():
    df = pd.DataFrame({"Bx": [3.0, 0.0], "By": [4.0, 0.0], "Bz": [0.0, 5.0]})
    win = DummyFeatures(df, y_sel="Bx",
                        forms=[{"bx": "Bx", "by": "By", "bz": "Bz"}])

    win.feature_add_magnitude()

    assert not win.errors
    assert "B_mag" in win._df.columns
    assert win.added_y == ["B_mag"]
    # |(3,4,0)| == 5
    assert abs(float(win._df["B_mag"].iloc[0]) - 5.0) < 1e-9


def test_feature_add_magnitude_cancel_stops_early():
    df = pd.DataFrame({"Bx": [1.0], "By": [2.0], "Bz": [2.0]})
    win = DummyFeatures(df, y_sel="Bx", forms=[None])  # cancelled form

    win.feature_add_magnitude()

    assert "B_mag" not in win._df.columns
    assert win.added_y == []


# ---------- cleaning actions (ROADMAP B) ----------

def test_feature_clean_fill_missing_with_value():
    df = pd.DataFrame({"y": [1.0, np.nan, 3.0]})
    win = DummyFeatures(df, y_sel="y", forms=[{"method": "value", "value": -9.0}])

    win.feature_clean_fill_missing()

    assert not win.errors
    assert win.added_y == ["y_filled"]
    assert win._df["y_filled"].tolist() == [1.0, -9.0, 3.0]


def test_feature_clean_remove_outliers_swaps_dataframe():
    df = pd.DataFrame({"y": [1.0] * 10 + [999.0]})
    win = DummyFeatures(df, y_sel="y",
                        forms=[{"method": "zscore", "threshold": 3.0}])

    win.feature_clean_remove_outliers()

    assert not win.errors
    assert len(win._df) == 10
    assert 999.0 not in win._df["y"].tolist()
    assert "columns-reloaded" in win.messages  # df swap refreshed the columns


def test_feature_clean_normalize_minmax_adds_column():
    df = pd.DataFrame({"y": [10.0, 20.0, 30.0]})
    win = DummyFeatures(df, y_sel="y", forms=[{"method": "minmax"}])

    win.feature_clean_normalize()

    assert not win.errors
    assert win.added_y == ["y_minmax"]
    assert win._df["y_minmax"].tolist() == [0.0, 0.5, 1.0]


def test_feature_clean_detrend_uses_x_column():
    x = np.arange(30, dtype=float)
    df = pd.DataFrame({"t": x, "y": 3.0 * x + 1.0})
    win = DummyFeatures(df, x_sel="t", y_sel="y", forms=[{"order": 1}])

    win.feature_clean_detrend()

    assert not win.errors
    assert win.added_y == ["y_detrend1"]
    assert np.allclose(win._df["y_detrend1"].to_numpy(), 0.0, atol=1e-9)


# ---------- filter actions (ROADMAP E) ----------

def test_feature_filter_butterworth_lowpass_adds_column():
    fs = 100.0
    t = np.arange(0, 5, 1 / fs)
    df = pd.DataFrame({
        "t": t,
        "y": np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 20 * t),
    })
    # single form: kind + fs (inferred) + cutoff
    win = DummyFeatures(df, x_sel="t", y_sel="y",
                        forms=[{"kind": "lowpass", "fs": fs, "cutoff": 5.0}])

    win.feature_filter_butterworth()

    assert not win.errors
    assert win.added_y == ["y_lowpass"]
    out = win._df["y_lowpass"].to_numpy()
    # the 20 Hz component is heavily attenuated
    assert np.std(out - np.sin(2 * np.pi * 2 * t)) < 0.2


def test_feature_filter_smooth_median_kills_spike():
    y = np.ones(50)
    y[25] = 100.0
    df = pd.DataFrame({"y": y})
    win = DummyFeatures(df, y_sel="y", forms=[{"method": "median", "kernel": 5}])

    win.feature_filter_smooth()

    assert not win.errors
    assert win.added_y == ["y_median"]
    assert win._df["y_median"].iloc[25] == 1.0


# ---------- peak & signal-quality metrics (ROADMAP E leftovers) ----------

class _ReportDummy(DummyFeatures):
    """Capture full inform() text for content assertions."""

    def inform(self, title, text):
        self.messages.append(f"{title}||{text}")


def test_feature_peak_metrics_gaussian_fwhm_and_area():
    sigma = 2.0
    x = np.linspace(-15, 15, 3001)
    y = np.exp(-x**2 / (2 * sigma**2))
    df = pd.DataFrame({"x": x, "y": y})
    win = _ReportDummy(df, x_sel="x", y_sel="y")

    win.feature_peak_metrics()

    assert not win.errors
    joined = "\n".join(win.messages)
    expected_fwhm = 2 * np.sqrt(2 * np.log(2)) * sigma  # ≈ 4.71
    assert "FWHM" in joined
    assert f"{expected_fwhm:.3g}"[:3] in joined  # "4.7..."
    expected_area = sigma * np.sqrt(2 * np.pi)  # ≈ 5.01
    assert "5.01" in joined


def test_feature_signal_quality_reports_snr():
    fs = 100.0
    t = np.arange(0, 10, 1 / fs)
    df = pd.DataFrame({"t": t, "y": np.sin(2 * np.pi * 5 * t)})
    win = _ReportDummy(df, x_sel="t", y_sel="y")

    win.feature_signal_quality()

    assert not win.errors
    joined = "\n".join(win.messages)
    assert "SNR" in joined and "dB" in joined and "Noise floor" in joined


def test_feature_apply_window_blackman_tapers_endpoints():
    df = pd.DataFrame({"y": np.ones(64)})
    win = DummyFeatures(df, y_sel="y", forms=[{"window": "blackman"}])

    win.feature_apply_window()

    assert not win.errors
    assert win.added_y == ["y_blackman"]
    col = win._df["y_blackman"].to_numpy()
    assert abs(col[0]) < 1e-6 and abs(col[-1]) < 1e-6
    assert col.max() == pytest.approx(1.0, abs=0.05)


def test_feature_apply_window_kaiser_asks_beta():
    df = pd.DataFrame({"y": np.ones(32)})
    win = DummyFeatures(df, y_sel="y", forms=[{"window": "kaiser", "beta": 14.0}])

    win.feature_apply_window()

    assert not win.errors
    assert win.added_y == ["y_kaiser"]


# ---------- statistics ----------

def test_feature_show_covariance_reports_matrix():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})

    class CovDummy(DummyFeatures):
        def inform(self, title, text):
            self.messages.append(f"{title}||{text}")

    win = CovDummy(df, y_sel="a")
    win.feature_show_covariance()

    assert not win.errors
    joined = "\n".join(win.messages)
    assert "Covariance" in joined and "a" in joined and "b" in joined


def test_feature_show_statistics_reports_via_inform():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0]})

    class StatsDummy(DummyFeatures):
        def inform(self, title, text):
            self.messages.append(f"{title}||{text}")

    win = StatsDummy(df, y_sel="y")
    win.feature_show_statistics()

    assert not win.errors
    joined = "\n".join(win.messages)
    assert "mean" in joined and "skewness" in joined and "2.5" in joined
