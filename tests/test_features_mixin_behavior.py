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
    assert any("Moving average" in m for m in win.messages)


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

    win.undo_last_dataframe_change()

    assert len(win._df) == 11
    assert 999.0 in win._df["y"].tolist()
    assert any("Undid data change" in message for message in win.messages)


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


def test_feature_clean_remove_missing_rows_swaps_dataframe():
    df = pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [1.0, np.nan, 3.0]})
    win = DummyFeatures(
        df,
        x_sel="x",
        y_sel="y",
        forms=[{"scope": "Selected column", "col": "y"}],
    )

    win.feature_clean_remove_nan()

    assert not win.errors
    assert win._df["y"].tolist() == [1.0, 3.0]
    assert "columns-reloaded" in win.messages


def test_feature_clean_crop_range_keeps_selected_interval():
    df = pd.DataFrame({"x": np.arange(6, dtype=float), "y": np.arange(6, dtype=float) * 10})
    win = DummyFeatures(
        df,
        x_sel="x",
        y_sel="y",
        forms=[{"col": "x", "min_value": 2.0, "max_value": 4.0}],
    )

    win.feature_clean_crop_range()

    assert not win.errors
    assert win._df["x"].tolist() == [2.0, 3.0, 4.0]


def test_feature_dataset_filter_opens_result_frame():
    df = pd.DataFrame({"group": ["a", "b", "a"], "y": [1.0, 2.0, 3.0]})
    win = DummyFeatures(
        df,
        y_sel="y",
        forms=[{"col": "group", "operator": "equals", "value": "a"}],
    )

    win.feature_dataset_filter()

    assert not win.errors
    assert win._df["group"].tolist() == ["a", "a"]


def test_feature_dataset_group_summarizes_to_result_frame():
    df = pd.DataFrame({"group": ["a", "a", "b"], "y": [1.0, 3.0, 10.0]})
    win = DummyFeatures(
        df,
        y_sel="y",
        forms=[{"group_col": "group", "value_col": "y", "agg": "mean"}],
    )

    win.feature_dataset_group()

    assert not win.errors
    assert dict(zip(win._df["group"], win._df["y_mean"])) == {"a": 2.0, "b": 10.0}
    assert dict(zip(win._df["group"], win._df["row_count"])) == {"a": 2, "b": 1}


def test_feature_dataset_merge_uses_second_book_registry():
    left = pd.DataFrame({"t": [0, 1, 2], "a": [1.0, 2.0, 3.0]})
    right = pd.DataFrame({"t": [1, 2], "b": [20.0, 30.0]})
    win = DummyFeatures(
        left,
        x_sel="t",
        y_sel="a",
        forms=[{"right_book": "Other", "left_key": "t", "right_key": "t", "how": "inner"}],
    )
    win._datasets = {"Other": {"df": right, "path": None}}

    win.feature_dataset_merge()

    assert not win.errors
    assert win._df["t"].tolist() == [1, 2]
    assert win._df["b"].tolist() == [20.0, 30.0]


def test_feature_clean_merge_by_timestamp_nearest():
    left = pd.DataFrame({"t": [0.0, 1.1, 2.2], "a": [1.0, 2.0, 3.0]})
    right = pd.DataFrame({"t2": [0.0, 1.0, 2.0], "b": [10.0, 20.0, 30.0]})
    win = DummyFeatures(
        left,
        x_sel="t",
        y_sel="a",
        forms=[{"right_book": "Other", "left_time": "t", "right_time": "t2", "mode": "nearest"}],
    )
    win._datasets = {"Other": {"df": right, "path": None}}

    win.feature_clean_merge_by_timestamp()

    assert not win.errors
    assert win._df["b"].tolist() == [10.0, 20.0, 30.0]


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


# --- param-taking cores (decoupled from the dialog; also drive the AI tools) ---
def test_smooth_column_core_callable_without_dialog():
    y = np.ones(50)
    y[25] = 100.0
    win = DummyFeatures(pd.DataFrame({"y": y}))  # no y_sel, no forms
    new_col = win.smooth_column("y", "median", kernel=5)
    assert new_col == "y_median"
    assert new_col in win._df.columns
    assert win.added_y == ["y_median"]
    assert win._df["y_median"].iloc[25] == 1.0


def test_smooth_column_rejects_unknown_method_and_missing_column():
    win = DummyFeatures(pd.DataFrame({"y": [1, 2, 3, 4, 5]}))
    with pytest.raises(ValueError):
        win.smooth_column("y", "bogus")
    with pytest.raises(ValueError):
        win.smooth_column("missing", "median")


def test_filter_column_butterworth_core_callable_without_dialog():
    fs = 200.0
    t = np.arange(0, 2, 1 / fs)
    sig = np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 40 * t)
    win = DummyFeatures(pd.DataFrame({"y": sig}))
    new_col = win.filter_column_butterworth("y", fs=fs, kind="lowpass", cutoff=8.0)
    assert new_col == "y_lowpass"
    assert new_col in win._df.columns
    assert np.std(win._df["y_lowpass"].to_numpy() - np.sin(2 * np.pi * 2 * t)) < 0.25


def test_filter_column_butterworth_core_validates_bandpass_cutoff():
    win = DummyFeatures(pd.DataFrame({"y": np.arange(100.0)}))
    with pytest.raises(ValueError):
        win.filter_column_butterworth("y", fs=100.0, kind="bandpass", cutoff=5.0)


def test_feature_signal_hilbert_adds_real_and_imag_columns():
    x = np.linspace(0, 2 * np.pi, 128, endpoint=False)
    y = np.cos(x)
    df = pd.DataFrame({"x": x, "y": y})
    win = DummyFeatures(df, x_sel="x", y_sel="y", forms=[{"y_col": "y"}])

    win.feature_signal_hilbert()

    assert not win.errors
    assert win.added_y == ["y_hilbert_real", "y_hilbert_imag"]
    assert np.allclose(win._df["y_hilbert_real"].to_numpy(), y, atol=1e-10)
    assert np.allclose(win._df["y_hilbert_imag"].to_numpy(), np.sin(x), atol=1e-10)


def test_feature_signal_envelope_adds_amplitude_column():
    fs = 200.0
    t = np.arange(0, 4, 1 / fs)
    amp = 1.0 + 0.25 * np.sin(2 * np.pi * 1.0 * t)
    y = amp * np.cos(2 * np.pi * 20.0 * t)
    df = pd.DataFrame({"t": t, "y": y})
    win = DummyFeatures(df, x_sel="t", y_sel="y", forms=[{"y_col": "y"}])

    win.feature_signal_envelope()

    assert not win.errors
    assert win.added_y == ["y_envelope"]
    assert np.allclose(win._df["y_envelope"].to_numpy(), amp, atol=0.05)


def test_feature_signal_autocorrelation_adds_lag_and_corr_columns():
    df = pd.DataFrame({"y": [1.0, -1.0, 1.0, -1.0]})
    win = DummyFeatures(
        df,
        y_sel="y",
        forms=[{"y_col": "y", "max_lag": 3, "normalize": True, "demean": True}],
    )

    win.feature_signal_autocorrelation()

    assert not win.errors
    assert win.added_x == ["y_autocorr_lag"]
    assert win.added_y == ["y_autocorr"]
    assert win._df["y_autocorr_lag"].tolist() == [0.0, 1.0, 2.0, 3.0]
    assert win._df["y_autocorr"].tolist() == pytest.approx([1.0, -0.75, 0.5, -0.25])


def test_feature_signal_convolution_same_adds_column():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1.0, 1.0, np.nan]})
    win = DummyFeatures(
        df,
        y_sel="a",
        forms=[{"a_col": "a", "b_col": "b", "mode": "same"}],
    )

    win.feature_signal_convolution()

    assert not win.errors
    assert win.added_y == ["a_conv_b"]
    assert win._df["a_conv_b"].tolist() == [1.0, 3.0, 5.0]


def test_feature_signal_deconvolution_outputs_quotient_and_remainder_frame():
    original = np.array([1.0, 2.0, -1.0, 0.5])
    kernel = np.array([1.0, 0.25])
    observed = np.convolve(original, kernel, mode="full")
    df = pd.DataFrame({
        "observed": observed,
        "kernel": [1.0, 0.25, np.nan, np.nan, np.nan],
    })
    win = DummyFeatures(
        df,
        y_sel="observed",
        forms=[{"observed_col": "observed", "kernel_col": "kernel"}],
    )

    win.feature_signal_deconvolution()

    assert not win.errors
    quotient_col = "observed_deconv_kernel"
    remainder_col = "observed_deconv_remainder"
    assert quotient_col in win._df.columns
    assert remainder_col in win._df.columns
    assert win._df[quotient_col].dropna().to_numpy().tolist() == pytest.approx(original.tolist())
    assert np.nanmax(np.abs(win._df[remainder_col].to_numpy(dtype=float))) < 1e-10


def test_feature_signal_instantaneous_frequency_adds_tracking_column():
    fs = 100.0
    t = np.arange(0, 4, 1 / fs)
    df = pd.DataFrame({"t": t, "y": np.sin(2 * np.pi * 5.0 * t)})
    win = DummyFeatures(df, x_sel="t", y_sel="y", forms=[{"y_col": "y", "fs": fs}])

    win.feature_signal_instantaneous_frequency()

    assert not win.errors
    assert win.added_y == ["y_instfreq_Hz"]
    assert np.nanmedian(win._df["y_instfreq_Hz"].to_numpy(dtype=float)) == pytest.approx(5.0, abs=0.05)


def test_feature_signal_ifft_outputs_time_domain_frame():
    signal = np.array([1.0, 0.0, -1.0, 0.0, 0.5, 0.0, -0.5, 0.0])
    spectrum = np.fft.fft(signal)
    df = pd.DataFrame({"real": spectrum.real, "imag": spectrum.imag})
    win = DummyFeatures(
        df,
        y_sel="real",
        forms=[{"real_col": "real", "imag_col": "imag"}],
    )

    win.feature_signal_ifft()

    assert not win.errors
    assert "real_ifft" in win._df.columns
    assert win._df["real_ifft"].to_numpy().tolist() == pytest.approx(signal.tolist())


def test_feature_signal_stft_outputs_long_format_frame():
    fs = 100.0
    t = np.arange(0, 2, 1 / fs)
    df = pd.DataFrame({"t": t, "y": np.sin(2 * np.pi * 20.0 * t)})
    win = DummyFeatures(
        df,
        x_sel="t",
        y_sel="y",
        forms=[{"y_col": "y", "fs": fs, "window": "hann", "nperseg": 64, "noverlap": 32}],
    )

    win.feature_signal_stft()

    assert not win.errors
    assert {"time", "frequency_Hz", "magnitude", "power", "phase_rad"}.issubset(win._df.columns)
    by_freq = win._df.groupby("frequency_Hz")["magnitude"].mean()
    assert float(by_freq.idxmax()) == pytest.approx(20.0, abs=2.0)


def test_feature_signal_zero_pad_outputs_padded_frame():
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0]})
    win = DummyFeatures(df, y_sel="y", forms=[{"y_col": "y", "target_length": 8}])

    win.feature_signal_zero_pad()

    assert not win.errors
    assert "y_zeropad" in win._df.columns
    assert win._df["y_zeropad"].to_numpy().tolist() == [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_feature_signal_harmonic_analysis_outputs_ranked_components():
    fs = 100.0
    t = np.arange(0, 2, 1 / fs)
    y = np.sin(2 * np.pi * 5.0 * t) + 0.4 * np.sin(2 * np.pi * 15.0 * t)
    df = pd.DataFrame({"t": t, "y": y})
    win = DummyFeatures(
        df,
        x_sel="t",
        y_sel="y",
        forms=[{"y_col": "y", "fs": fs, "top_n": 3, "window": "none"}],
    )

    win.feature_signal_harmonic_analysis()

    assert not win.errors
    assert {"source_column", "rank", "frequency_Hz", "amplitude", "power", "harmonic_order"}.issubset(win._df.columns)
    freqs = win._df["frequency_Hz"].round(6).tolist()
    assert 5.0 in freqs
    assert 15.0 in freqs


# ---------- peak & signal-quality metrics (ROADMAP E leftovers) ----------

class _ReportDummy(DummyFeatures):
    """Capture full inform() text for content assertions."""

    def inform(self, title, text):
        self.messages.append(f"{title}||{text}")


def test_feature_peak_metrics_gaussian_fwhm_and_area():
    """New UX: one form (column choice) → result Book table with area/FWHM/peak."""
    sigma = 2.0
    x = np.linspace(-15, 15, 3001)
    y = np.exp(-x**2 / (2 * sigma**2))
    df = pd.DataFrame({"x": x, "y": y})
    win = _ReportDummy(df, x_sel="x", y_sel="y", forms=[{"columns": "y"}])

    win.feature_peak_metrics()

    assert not win.errors
    table = win._df  # stub fallback: result Book lands via _swap_dataframe
    assert list(table["column"]) == ["y"]
    row = table.iloc[0]
    expected_fwhm = 2 * np.sqrt(2 * np.log(2)) * sigma  # ≈ 4.71
    assert row["fwhm"] == pytest.approx(expected_fwhm, rel=0.01)
    assert row["area"] == pytest.approx(sigma * np.sqrt(2 * np.pi), rel=0.01)
    assert row["peak_x"] == pytest.approx(0.0, abs=0.02)
    assert row["peak_height"] == pytest.approx(1.0, rel=0.01)


def test_feature_peak_metrics_all_columns_excludes_x():
    x = np.linspace(0, 10, 500)
    df = pd.DataFrame({"t": x,
                       "a": np.exp(-((x - 3) ** 2)),
                       "b": np.exp(-((x - 7) ** 2))})
    win = _ReportDummy(df, x_sel="t", y_sel="a",
                       forms=[{"columns": "All numeric columns"}])

    win.feature_peak_metrics()

    assert not win.errors
    table = win._df
    # the designated X column is not analyzed against itself
    assert list(table["column"]) == ["a", "b"]
    assert table.iloc[0]["peak_x"] == pytest.approx(3.0, abs=0.05)
    assert table.iloc[1]["peak_x"] == pytest.approx(7.0, abs=0.05)


def test_feature_signal_quality_reports_snr():
    """New UX: column + fs in one form → result Book with snr_db/noise_floor."""
    fs = 100.0
    t = np.arange(0, 10, 1 / fs)
    df = pd.DataFrame({"t": t, "y": np.sin(2 * np.pi * 5 * t)})
    win = _ReportDummy(df, x_sel="t", y_sel="y",
                       forms=[{"columns": "y", "fs": fs}])

    win.feature_signal_quality()

    assert not win.errors
    table = win._df
    assert list(table.columns) == ["column", "fs_hz", "snr_db", "noise_floor"]
    row = table.iloc[0]
    assert row["column"] == "y"
    assert row["fs_hz"] == fs
    assert row["snr_db"] > 20  # clean sine has a strong peak over the floor
    assert np.isfinite(row["noise_floor"])


def test_feature_signal_quality_cancel_leaves_data_untouched():
    df = pd.DataFrame({"y": np.sin(np.linspace(0, 20, 200))})
    win = _ReportDummy(df, y_sel="y", forms=[None])

    win.feature_signal_quality()

    assert not win.errors
    assert win._df is df  # cancelled form = no result Book, no swap


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

def test_feature_show_covariance_opens_matrix_book():
    """New UX: kind form (Covariance/Correlation) → result Book with a named
    'column' first column so the matrix reads correctly on a worksheet."""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})
    win = _ReportDummy(df, y_sel="a", forms=[{"kind": "Covariance"}])

    win.feature_show_covariance()

    assert not win.errors
    table = win._df
    assert list(table["column"]) == ["a", "b"]
    # cov(a, b) = 2 * var(a) = 2.0 for b = 2a
    assert table.iloc[0]["b"] == pytest.approx(2.0)


def test_feature_show_covariance_correlation_kind():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})
    win = _ReportDummy(df, y_sel="a", forms=[{"kind": "Correlation"}])

    win.feature_show_covariance()

    assert not win.errors
    # perfectly correlated: off-diagonal = 1.0
    assert win._df.iloc[0]["b"] == pytest.approx(1.0)


def test_feature_show_statistics_opens_result_book():
    """New UX: column form → result Book (statistic rows × data columns)."""
    df = pd.DataFrame({"y": [1.0, 2.0, 3.0, 4.0]})
    win = _ReportDummy(df, y_sel="y",
                       forms=[{"columns": "All numeric columns"}])

    win.feature_show_statistics()

    assert not win.errors
    table = win._df
    assert "statistic" in table.columns and "y" in table.columns
    mean_row = table[table["statistic"] == "mean"]
    assert mean_row["y"].iloc[0] == pytest.approx(2.5)
    assert "skewness" in list(table["statistic"])
