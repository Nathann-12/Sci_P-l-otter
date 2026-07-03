"""Behavioral safety net for core flows, locked in before the UI redesign.

These exercise real behavior (numeric results / real Qt widgets + matplotlib
artists), not just structure, so a UI redesign that moves widgets around will
fail loudly if it regresses what the app actually does.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("PySide6")
pytest.importorskip("numexpr")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- FFT (signal core)
def test_compute_fft_recovers_known_frequency():
    from processors import compute_fft

    fs = 100.0          # Hz
    f0 = 10.0           # Hz tone we expect to recover
    n = 1024
    t = np.arange(n) / fs
    y = np.sin(2 * np.pi * f0 * t)
    df = pd.DataFrame({"t": t, "y": y})

    df_fft, inferred_fs = compute_fft(df, x_col="t", y_col="y", detrend=True, window="hanning")

    assert abs(inferred_fs - fs) < 1e-6
    peak_freq = float(df_fft.loc[df_fft["amplitude"].idxmax(), "freq_Hz"])
    # frequency resolution is fs/n ~ 0.1 Hz; allow a couple of bins of slack
    assert abs(peak_freq - f0) < 0.5


# ------------------------------------------------- end-to-end: load CSV -> columns -> plot
def test_load_csv_columns_and_plot_line_integration(qapp):
    csv_path = PROJECT_ROOT / "small_test.csv"
    if not csv_path.exists():
        pytest.skip("small_test.csv fixture not present")

    from main import MainWindow

    win = MainWindow()
    try:
        win.load_data(str(csv_path))
        assert win._df is not None and not win._df.empty

        # mimics pressing "โหลดคอลัมน์"
        win.load_columns_from_df()
        assert win.cbX.count() > 0
        assert win.cbY.count() > 0

        # pick two numeric columns and plot a line on the current tab
        win.cbX.setCurrentText("value2")
        win.cbY.setCurrentText("value1")

        tab_id = win.tabs.get_current_tab_id()
        graph_tab = win.tabs.tabs[tab_id]
        win.plot_line()

        assert len(graph_tab.layers) >= 1
        assert len(graph_tab.get_axes().lines) >= 1
    finally:
        win.close()


# ------------------------------------------- Origin-style worksheet fills from loaded data
def test_workbook_fills_from_loaded_data(qapp):
    csv_path = PROJECT_ROOT / "small_test.csv"
    if not csv_path.exists():
        pytest.skip("small_test.csv fixture not present")

    from main import MainWindow

    win = MainWindow()
    try:
        # MDI workspace: the TabManager adapter is the MDI, with an initial graph
        assert win.tabs is win.mdi
        assert win.mdi.count() >= 1              # Graph1 exists so canvas works

        win.load_data(str(csv_path))
        win.load_columns_from_df()
        win._refresh_workbook()

        # the Origin-style worksheet now mirrors the loaded columns/values
        wb_df = win.workbook.dataframe()
        assert len(wb_df.columns) >= 2
        assert len(wb_df) >= 1
    finally:
        win.close()
