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

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main

    w = app_main.MainWindow()
    yield w
    w.close()


def _clean_text(text: str) -> str:
    return (text or "").replace("&", "").replace("…", "...").replace("â€¦", "...").strip()


def _top_menu(win, title: str):
    for action in win.menuBar().actions():
        menu = action.menu()
        if menu is not None and _clean_text(menu.title()) == title:
            return menu
    raise AssertionError(f"top menu not found: {title}")


def _menu_action(menu, text: str):
    target = _clean_text(text)
    for action in menu.actions():
        if action.isSeparator():
            continue
        if _clean_text(action.text()) == target:
            return action
    raise AssertionError(f"action not found: {text}")


def _submenu(menu, title: str):
    target = _clean_text(title)
    for action in menu.actions():
        sub = action.menu()
        if sub is not None and _clean_text(sub.title()) == target:
            return sub
    raise AssertionError(f"submenu not found: {title}")


def _clean_text(text: str) -> str:
    return (
        (text or "")
        .replace("&", "")
        .replace("â€¦", "...")
        .replace("Ã¢â‚¬Â¦", "...")
        .replace("…", "...")
        .replace("â†’", "->")
        .replace("→", "->")
        .strip()
    )


def _menu_action_contains(menu, *needles: str):
    targets = [_clean_text(needle) for needle in needles]
    for action in menu.actions():
        if action.isSeparator():
            continue
        action_text = _clean_text(action.text())
        if all(needle in action_text for needle in targets):
            return action
    raise AssertionError(f"action containing not found: {needles}")


def _seed_science_book(win, rows: int = 32):
    t = np.arange(rows, dtype=float)
    signal = np.sin(2.0 * np.pi * t / max(rows, 1)) + 0.05 * t
    other = np.cos(2.0 * np.pi * t / max(rows, 1)) + 2.0
    err = np.full(rows, 0.1, dtype=float)
    kernel = np.full(rows, np.nan, dtype=float)
    kernel[:3] = [1.0, 0.5, 0.25]
    df = pd.DataFrame(
        {
            "t": t,
            "signal": signal,
            "other": other,
            "err": err,
            "kernel": kernel,
        }
    )
    win._df = df.copy()
    win.workbook.set_dataframe(win._df)
    win.workbook.dataset_name = "Book1"
    win.workbook.source_df = win._df
    if hasattr(win.workbook, "mark_clean"):
        win.workbook.mark_clean()
    win.load_columns_from_df()
    win.cbX.setCurrentText("t")
    win.cbY.setCurrentText("signal")
    return win._df


def _install_nonblocking_ui(win, monkeypatch):
    calls = {"inform": [], "notify": [], "errors": []}

    def fake_ask_form(self, _title, fields, description=None):
        result = {}
        for field in fields:
            name = field["name"]
            if name == "kernel_col":
                result[name] = "kernel"
            elif name == "b_col":
                result[name] = "kernel"
            elif name == "imag_col":
                result[name] = "<none>"
            elif name == "xerr":
                result[name] = "(none)"
            else:
                result[name] = field.get("default")
        return result

    monkeypatch.setattr(type(win), "ask_form", fake_ask_form, raising=False)
    monkeypatch.setattr(
        type(win),
        "ask_number",
        lambda self, *_args, **_kwargs: (1.0, True),
        raising=False,
    )
    monkeypatch.setattr(
        type(win),
        "inform",
        lambda self, title, text: calls["inform"].append((title, text)),
        raising=False,
    )
    monkeypatch.setattr(
        type(win),
        "notify",
        lambda self, msg, *args, **kwargs: calls["notify"].append(msg),
        raising=False,
    )
    monkeypatch.setattr(
        type(win),
        "error_box",
        lambda self, title, text: calls["errors"].append((title, text)),
        raising=False,
    )
    return calls


def test_function_menus_expose_expected_actions(win):
    data = _top_menu(win, "Data")
    process = _top_menu(win, "Process")
    analysis = _top_menu(win, "Analysis")
    plot = _top_menu(win, "Plot")
    export = _top_menu(win, "Export")
    tools = _top_menu(win, "Tools")

    for title in (
        "Quick Actions",
        "Frequency & Spectrum",
        "Smoothing & Filters",
        "Signal Transforms",
        "Correlation & Convolution",
        "Clean & Prepare Data",
        "Summarize & Aggregate",
    ):
        assert _submenu(process, title) is not None
    top_level_commands = [
        _clean_text(action.text())
        for action in process.actions()
        if not action.isSeparator() and action.menu() is None
    ]
    assert top_level_commands == []
    quick = _submenu(process, "Quick Actions")
    spectrum = _submenu(process, "Frequency & Spectrum")
    for text in ("Moving Average", "Add |B|", "Add Bangkok Time", "Aggregate..."):
        assert _menu_action(quick, text) is not None
    for text in ("FFT", "PSD (Welch)...", "STFT...", "IFFT...", "Harmonic Analysis..."):
        assert _menu_action(spectrum, text) is not None
    for title in ("Active Book", "Columns", "Units + Metadata", "Quick Transforms", "Books + Query", "Clean Data"):
        assert _submenu(data, title) is not None

    # deduplicated Analysis menu: every command has exactly ONE home in the
    # categorized submenus (no top-level duplicates, no Peak Detection dup menu)
    analysis_top_commands = [
        a.text() for a in analysis.actions()
        if not a.isSeparator() and a.menu() is None
    ]
    assert analysis_top_commands == []
    for title in (
        "Statistics",
        "Mathematics",
        "Data Manipulation",
        "Fitting",
        "Signal Processing",
        "Peaks and Baseline",
    ):
        assert _submenu(analysis, title) is not None
    assert _submenu(analysis, "Cross-Correlation") is not None
    assert _menu_action(_submenu(analysis, "Statistics"), "Descriptive Statistics...") is not None
    assert _menu_action(_submenu(analysis, "Statistics"), "Covariance Matrix...") is not None
    assert _menu_action(_submenu(analysis, "Fitting"), "Nonlinear Curve Fit...") is not None
    peaks_menu = _submenu(analysis, "Peaks and Baseline")
    assert _menu_action(peaks_menu, "Peak Metrics (FWHM / Area)...") is not None
    assert _menu_action(peaks_menu, "Signal Quality (SNR / Noise floor)...") is not None
    assert _menu_action(peaks_menu, "Enable Peak Detection") is not None

    for text in ("Error Bar Plot...", "Fill Between (band)...", "Add Secondary Y Axis...", "Broken Axis..."):
        assert _menu_action(plot, text) is not None
    for text in ("Export Visible CSV", "Export PNG", "Batch Export Graphs...", "Export Report (PDF)..."):
        assert _menu_action(export, text) is not None
    assert _submenu(tools, "Plotting Mode") is not None


def test_data_menu_workflow_sections_and_shortcuts(win):
    data = _top_menu(win, "Data")
    active = _submenu(data, "Active Book")
    columns = _submenu(data, "Columns")
    units = _submenu(data, "Units + Metadata")
    quick = _submenu(data, "Quick Transforms")
    clean = _submenu(data, "Clean Data")

    assert _menu_action(active, "Open Data File...").shortcut().toString() == "Ctrl+O"
    assert _menu_action(active, "Use Active Worksheet Data").shortcut().toString() == "Ctrl+Shift+U"
    assert _menu_action(columns, "Create Derived Column...").shortcut().toString() == "Ctrl+Shift+D"
    assert _menu_action(columns, "Set Column Types...") is not None
    assert _menu_action(units, "Units + Calibration...") is not None
    assert _menu_action(quick, "Moving Average") is not None
    query = _submenu(data, "Books + Query")
    assert _menu_action(active, "Duplicate Active Book...") is not None
    assert _menu_action(active, "Rename Active Book...") is not None
    assert _menu_action(query, "Merge Books...") is not None
    assert _menu_action(query, "Search Book...") is not None
    assert _menu_action(clean, "Normalize / Standardize...") is not None
    assert _menu_action(clean, "Remove Missing Rows...") is not None
    assert _menu_action(clean, "Merge by Timestamp...") is not None


def test_data_menu_quick_transform_executes_from_menu(win, monkeypatch):
    _seed_science_book(win, rows=40)
    calls = _install_nonblocking_ui(win, monkeypatch)
    quick = _submenu(_top_menu(win, "Data"), "Quick Transforms")

    before_columns = set(win._df.columns)
    _menu_action(quick, "Moving Average").trigger()

    assert calls["errors"] == []
    assert set(win._df.columns) != before_columns
    assert any(str(column).endswith("_MA25") for column in win._df.columns)


def test_two_row_toolbar_processing_and_analysis_actions_execute(win, monkeypatch):
    _seed_science_book(win, rows=48)
    calls = _install_nonblocking_ui(win, monkeypatch)

    win.toolbar_actions["moving_average"].trigger()
    assert any(str(column).endswith("_MA25") for column in win._df.columns)
    win.toolbar_actions["fill_missing"].trigger()
    win.toolbar_actions["hilbert"].trigger()
    assert any("hilbert" in str(column).lower() for column in win._df.columns)
    win.toolbar_actions["stats"].trigger()

    assert calls["errors"] == []
    assert "Descriptive Stats" in win._datasets


def test_view_tools_arm_the_graph_cursor(win):
    """Box zoom / crosshair / annotation tools must give visible cursor feedback.

    A user complaint: clicking these did nothing visible — the pointer stayed a
    plain arrow so there was no sign a tool was armed.
    """
    from PySide6.QtCore import Qt

    _seed_science_book(win, rows=32)
    win.plot_from_workbook("line", new_graph=True)
    tab = win._get_current_tab()

    def shape():
        return tab.canvas.cursor().shape()

    win.start_box_zoom()
    assert shape() == Qt.CrossCursor

    win.toggle_crosshair(True)
    assert shape() == Qt.CrossCursor
    win.toggle_crosshair(False)
    assert shape() == Qt.ArrowCursor  # restored when the tool is switched off

    # Annotation tools: text = I-beam, shapes = crosshair; disabling restores arrow.
    win.toolbar_actions["ann_text"].trigger()
    assert shape() == Qt.IBeamCursor
    win.toolbar_actions["ann_rect"].trigger()
    assert shape() == Qt.CrossCursor
    win.actAnnEnable.setChecked(False)
    assert shape() == Qt.ArrowCursor


def test_units_and_calibrate_dialogs_are_english_and_themed(win):
    """The Units/Calibrate dialogs used to hardcode a light theme + Thai labels
    that rendered as tofu; they should now be English and inherit the theme."""
    from dialogs_units import UnitsDialog
    from dialogs_calibrate import CalibrateDialog

    _seed_science_book(win, rows=16)
    dlg = UnitsDialog(win._df, win)
    assert dlg.windowTitle() == "Units & Calibration"
    # numeric columns land in the table (t, signal, other, err, kernel)
    assert dlg.table.rowCount() >= 3
    # no hardcoded light-theme stylesheet fighting the app theme
    assert dlg.styleSheet() == ""
    # sensible size, not the old 1600x800 monster
    assert dlg.width() <= 1100

    cal = CalibrateDialog(win)
    assert "Calibration" in cal.windowTitle() and cal.styleSheet() == ""
    cal.raw1_spin.setValue(0.0); cal.true1_spin.setValue(1.0)
    cal.raw2_spin.setValue(10.0); cal.true2_spin.setValue(21.0)
    cal.compute_calibration()
    a, b = cal.get_calibration()
    assert abs(a - 2.0) < 1e-9 and abs(b - 1.0) < 1e-9


def test_two_row_toolbar_annotation_gas_and_workflow_actions_execute(win, monkeypatch):
    _seed_science_book(win, rows=64)
    calls = _install_nonblocking_ui(win, monkeypatch)
    win.plot_from_workbook("line", new_graph=True)
    manager = win.tabs.currentWidget().annotation_manager

    win.toolbar_actions["ann_text"].trigger()
    # Picking a tool must ARM the manager (enable + mode), not just set the mode —
    # otherwise clicks on the graph silently did nothing until "Annotate" was toggled.
    assert manager.mode == "text" and manager.enabled is True
    assert win.actAnnEnable.isChecked() is True
    win.toolbar_actions["ann_arrow"].trigger()
    assert manager.mode == "arrow" and manager.enabled is True

    _menu_action(_submenu(_top_menu(win, "Modules"), "Gas Sensor"), "Gas Dilution (ppm)...").trigger()
    win.analysis_history.record("fill_missing", col="signal", method="mean")
    win.toolbar_actions["workflow_history"].trigger()
    win.toolbar_actions["workflow_clear"].trigger()

    assert calls["errors"] == []
    assert any("Gas" in title or "แก๊ส" in title for title, _text in calls["inform"])
    assert len(win.analysis_history) == 0


@pytest.mark.parametrize(
    "path",
    [
        ("Process", "Quick Actions", "Moving Average"),
        ("Process", "Quick Actions", "Add |B|"),
        ("Process", "Quick Actions", "Add Bangkok Time"),
        ("Process", "Frequency & Spectrum", "FFT"),
        ("Process", "Frequency & Spectrum", "PSD (Welch)..."),
        ("Process", "Frequency & Spectrum", "STFT..."),
        ("Process", "Frequency & Spectrum", "IFFT..."),
        ("Process", "Frequency & Spectrum", "Harmonic Analysis..."),
        ("Process", "Clean & Prepare Data", "Fill Missing..."),
        ("Process", "Clean & Prepare Data", "Interpolate Missing"),
        ("Process", "Clean & Prepare Data", "Remove Missing Rows..."),
        ("Process", "Clean & Prepare Data", "Remove Duplicates"),
        ("Process", "Clean & Prepare Data", "Remove Outliers..."),
        ("Process", "Clean & Prepare Data", "Crop Range..."),
        ("Process", "Clean & Prepare Data", "Normalize / Standardize..."),
        ("Process", "Clean & Prepare Data", "Detrend / Baseline..."),
        ("Process", "Clean & Prepare Data", "Sort..."),
        ("Process", "Clean & Prepare Data", "Resample (uniform grid)..."),
        ("Process", "Clean & Prepare Data", "Merge by Timestamp..."),
        ("Process", "Smoothing & Filters", "Moving Average"),
        ("Process", "Smoothing & Filters", "Butterworth (Low/High/Band)..."),
        ("Process", "Smoothing & Filters", "Smooth (Savitzky-Golay/Median/Gaussian)..."),
        ("Process", "Smoothing & Filters", "Apply Window (Hann/Hamming/Blackman/Kaiser)..."),
        ("Process", "Smoothing & Filters", "Decimation..."),
        ("Process", "Signal Transforms", "Hilbert Transform..."),
        ("Process", "Signal Transforms", "Envelope Detection..."),
        ("Process", "Signal Transforms", "Instantaneous Frequency..."),
        ("Process", "Signal Transforms", "Zero Padding..."),
        ("Process", "Correlation & Convolution", "Auto-correlation..."),
        ("Process", "Correlation & Convolution", "Convolution..."),
        ("Process", "Correlation & Convolution", "Deconvolution..."),
        ("Process", "Summarize & Aggregate", "Descriptive Statistics..."),
        ("Process", "Summarize & Aggregate", "Signal Quality (SNR / Noise floor)..."),
    ],
)
def test_process_menu_actions_execute_from_menu(win, monkeypatch, path):
    _seed_science_book(win)
    calls = _install_nonblocking_ui(win, monkeypatch)

    menu = _top_menu(win, path[0])
    for sub_title in path[1:-1]:
        menu = _submenu(menu, sub_title)
    action = _menu_action(menu, path[-1])

    before_columns = set(win._df.columns)
    action.trigger()

    assert calls["errors"] == []
    assert calls["notify"] or calls["inform"] or set(win._df.columns) != before_columns


def test_analysis_menu_origin_sections_expose_working_signal_actions(win, monkeypatch):
    source_df = _seed_science_book(win, rows=32).copy()
    calls = _install_nonblocking_ui(win, monkeypatch)
    analysis = _top_menu(win, "Analysis")

    statistics = _submenu(analysis, "Statistics")
    signal = _submenu(analysis, "Signal Processing")
    peaks = _submenu(analysis, "Peaks and Baseline")

    for text in (
        "Descriptive Statistics...",
        "Covariance Matrix...",
        "Correlation Matrix...",
    ):
        assert _menu_action(statistics, text) is not None
    # Signal Quality lives in exactly one place: Peaks and Baseline
    assert _menu_action(peaks, "Signal Quality (SNR / Noise floor)...") is not None
    for title in ("Smooth", "FFT", "Wavelet", "Correlation"):
        assert _submenu(signal, title) is not None
    for text in (
        "FFT Filters...",
        "IIR Filter...",
        "STFT...",
        "Convolution...",
        "Hilbert Transform...",
        "Envelope...",
        "Decimation...",
        "Harmonic Analysis...",
    ):
        assert _menu_action(signal, text) is not None
    for text in (
        "Peak Metrics (FWHM / Area)...",
        "Peak Settings...",
        "Detect in Range",
        "Export Peak Table (CSV/Excel)",
    ):
        assert _menu_action(peaks, text) is not None

    _menu_action(signal, "Decimation...").trigger()
    assert calls["errors"] == []
    assert "Decimation_signal" in win._datasets
    decimated = win._datasets["Decimation_signal"]["df"]
    assert list(decimated["signal_decim2"]) == pytest.approx(
        list(source_df["signal"].iloc[::2])
    )

    _seed_science_book(win, rows=64)
    _menu_action(signal, "Harmonic Analysis...").trigger()
    assert calls["errors"] == []
    assert "Harmonics_signal" in win._datasets


def test_two_row_toolbar_decimation_action_executes(win, monkeypatch):
    _seed_science_book(win, rows=16)
    calls = _install_nonblocking_ui(win, monkeypatch)

    win.toolbar_actions["decimation"].trigger()

    assert calls["errors"] == []
    assert "Decimation_signal" in win._datasets
    assert len(win._datasets["Decimation_signal"]["df"]) == 8


def test_smooth_menu_action_shows_new_column_on_worksheet(win, monkeypatch):
    # Regression: Smooth (and every column-adding transform) updated only the
    # hidden DataFrame/cbY combo — the visible worksheet never changed, so to
    # the user the Smooth function "did nothing at all".
    _seed_science_book(win)
    calls = _install_nonblocking_ui(win, monkeypatch)
    analysis = _top_menu(win, "Analysis")
    smooth_menu = _submenu(_submenu(analysis, "Signal Processing"), "Smooth")

    _menu_action(smooth_menu, "Smooth (Savitzky-Golay/Median/Gaussian)...").trigger()

    assert calls["errors"] == []
    assert "signal_savgol" in win._df.columns
    # the Origin Book (what the user actually sees) must show the new column
    sheet_cols = [str(c) for c in win.workbook.source_df.columns]
    assert "signal_savgol" in sheet_cols
    assert win.workbook.table.columnCount() == len(win._df.columns)

    _seed_science_book(win)
    _menu_action(smooth_menu, "Moving Average").trigger()
    assert calls["errors"] == []
    ma_cols = [c for c in win.workbook.source_df.columns if "signal" in str(c) and c != "signal"]
    assert ma_cols, list(win.workbook.source_df.columns)


def test_merge_by_timestamp_handles_mixed_datetime_resolutions(win, monkeypatch):
    # Regression: pandas 2.x can parse the two Books' time columns at different
    # datetime64 resolutions (ns vs s); merge_asof then failed with
    # "incompatible merge keys" and the action died in an error box.
    calls = _install_nonblocking_ui(win, monkeypatch)
    left = pd.DataFrame(
        {
            "time": ["2026-01-01 00:00:00", "2026-01-01 00:00:10", "2026-01-01 00:00:20"],
            "a": [1.0, 2.0, 3.0],
        }
    )
    win._df = left.copy()
    win.workbook.set_dataframe(win._df)
    win.workbook.dataset_name = "Book1"
    win.load_columns_from_df()
    right = pd.DataFrame(
        {
            "time": np.array(
                ["2026-01-01T00:00:03", "2026-01-01T00:00:12", "2026-01-01T00:00:19"],
                dtype="datetime64[s]",
            ),
            "b": [10.0, 20.0, 30.0],
        }
    )
    win._datasets["Right"] = {"df": right, "path": None}

    analysis = _top_menu(win, "Analysis")
    manipulation = _submenu(analysis, "Data Manipulation")
    _menu_action(manipulation, "Merge by Timestamp...").trigger()

    assert calls["errors"] == [], calls["errors"]
    merged_books = [name for name in win._datasets if name.startswith("TimeMerge_")]
    assert merged_books, list(win._datasets)
    merged = win._datasets[merged_books[0]]["df"]
    assert "b" in merged.columns
    assert len(merged) == 3


def test_two_row_toolbar_new_core_actions_execute(win, monkeypatch, tmp_path):
    _seed_science_book(win, rows=24)
    win._datasets["Other"] = {
        "df": pd.DataFrame({"t": np.arange(24, dtype=float), "aux": np.arange(24, dtype=float) * 2}),
        "path": None,
    }
    calls = _install_nonblocking_ui(win, monkeypatch)
    save_paths = iter([str(tmp_path / "report.html"), str(tmp_path / "snapshot.json")])
    monkeypatch.setattr(type(win), "ask_save_path", lambda self, *_args, **_kwargs: next(save_paths), raising=False)

    win.toolbar_actions["dataset_group"].trigger()
    assert "Group_t" in win._datasets
    _seed_science_book(win, rows=24)
    win.toolbar_actions["dataset_filter"].trigger()
    assert "Filter_signal" in win._datasets
    _seed_science_book(win, rows=24)
    win.toolbar_actions["harmonic"].trigger()
    assert "Harmonics_signal" in win._datasets
    _seed_science_book(win, rows=24)
    win.toolbar_actions["remove_missing_rows"].trigger()
    win.toolbar_actions["crop_range"].trigger()
    win.toolbar_actions["workflow_report"].trigger()
    win.toolbar_actions["workflow_snapshot"].trigger()
    win.toolbar_actions["workflow_compare"].trigger()
    win.toolbar_actions["workflow_audit"].trigger()

    assert calls["errors"] == []
    assert "Audit Trail" in win._datasets


def test_analysis_menu_statistics_and_quality_actions_execute_from_menu(win, monkeypatch):
    _seed_science_book(win)
    calls = _install_nonblocking_ui(win, monkeypatch)
    analysis = _top_menu(win, "Analysis")

    statistics = _submenu(analysis, "Statistics")
    peaks = _submenu(analysis, "Peaks and Baseline")
    for menu, text in (
        (statistics, "Descriptive Statistics..."),
        (statistics, "Covariance Matrix..."),
        (peaks, "Peak Metrics (FWHM / Area)..."),
        (peaks, "Signal Quality (SNR / Noise floor)..."),
    ):
        # a result Book becomes the active Book when it opens (multi-book
        # contract), so re-activate the science data before each analysis —
        # same as a user clicking their data Book first
        _seed_science_book(win)
        _menu_action(menu, text).trigger()

    assert calls["errors"] == []
    # new UX: each analysis opens an Origin-style result Book (not a message box)
    for book in ("Descriptive Stats", "Covariance Matrix",
                 "Peak Metrics", "Signal Quality"):
        assert book in win._datasets, book
    assert any("SNR" in message for message in calls["notify"])
    stats_table = win._datasets["Descriptive Stats"]["df"]
    assert "statistic" in stats_table.columns


def test_analysis_crosscorr_and_peak_menu_actions_smoke(win):
    _seed_science_book(win)
    analysis = _top_menu(win, "Analysis")
    cc_menu = _submenu(analysis, "Cross-Correlation")
    pk_menu = _submenu(analysis, "Peaks and Baseline")

    _menu_action(cc_menu, "Enable Multi-Cursor Mode").trigger()
    _menu_action(cc_menu, "Link Axes by X-Time").trigger()
    _menu_action(cc_menu, "Clear Results").trigger()
    _menu_action(pk_menu, "Enable Peak Detection").trigger()
    _menu_action(pk_menu, "Clear Peaks").trigger()

    assert win.actCCEnable.isChecked()
    assert win.actCCLink.isChecked()
    assert win.actPkEnable.isChecked()


def test_plot_menu_extra_graph_actions_execute_from_menu(win, monkeypatch):
    _seed_science_book(win)
    calls = _install_nonblocking_ui(win, monkeypatch)
    plot = _top_menu(win, "Plot")

    graphs_before = win.tabs.count()
    _menu_action(plot, "Error Bar Plot...").trigger()
    _menu_action(plot, "Fill Between (band)...").trigger()

    assert win.tabs.count() == graphs_before + 2
    assert calls["errors"] == []

    win.plot_from_workbook("line", new_graph=False)

    def plot_extra_form(self, title, fields, description=None):
        if title == "Add Secondary Y Axis":
            return {"x": "t", "y2": "other"}
        if title == "Broken Axis":
            return {"axis": "Y", "lower": 0.4, "upper": 1.2}
        return {field["name"]: field.get("default") for field in fields}

    monkeypatch.setattr(type(win), "ask_form", plot_extra_form, raising=False)
    _menu_action(plot, "Add Secondary Y Axis...").trigger()
    _menu_action(plot, "Broken Axis...").trigger()

    assert calls["errors"] == []
    assert calls["notify"]


def test_tools_plotting_mode_menu_updates_plot_mode(win):
    from core.plot_mode import PlotMode

    mode_menu = _submenu(_top_menu(win, "Tools"), "Plotting Mode")

    _menu_action(mode_menu, "Replace").trigger()
    assert win.plot_mode == PlotMode.REPLACE

    _menu_action(mode_menu, "Overlay (default)").trigger()
    assert win.plot_mode == PlotMode.OVERLAY


def test_process_aggregate_action_executes_from_menu(win, monkeypatch):
    from PySide6.QtWidgets import QDialog

    import main_window_features_mixin as features_mixin

    _seed_science_book(win)
    calls = _install_nonblocking_ui(win, monkeypatch)
    captured = {}

    class FakeAggregateDialog:
        def __init__(self, parent, df, cols):
            captured["parent"] = parent
            captured["cols"] = list(cols)

        def exec(self):
            return QDialog.Accepted

        def get_params(self):
            return {
                "id_col": "t",
                "value_cols": ["signal"],
                "agg": "mean",
                "stacked": False,
            }

    def fake_aggregate_and_plot(self, df, *, id_col, value_cols, agg, stacked=False):
        captured["aggregate"] = {
            "rows": len(df),
            "id_col": id_col,
            "value_cols": list(value_cols),
            "agg": agg,
            "stacked": stacked,
        }

    monkeypatch.setattr(features_mixin, "AggregateDialog", FakeAggregateDialog)
    monkeypatch.setattr(type(win), "_aggregate_and_plot", fake_aggregate_and_plot, raising=False)

    _menu_action(_submenu(_top_menu(win, "Process"), "Summarize & Aggregate"), "Aggregate...").trigger()

    assert calls["errors"] == []
    assert captured["parent"] is win
    assert captured["cols"] == list(win._df.columns)
    assert captured["aggregate"] == {
        "rows": len(win._df),
        "id_col": "t",
        "value_cols": ["signal"],
        "agg": "mean",
        "stacked": False,
    }


def test_analysis_submenu_actions_execute_from_menu(win, monkeypatch, tmp_path):
    _seed_science_book(win, rows=64)
    calls = _install_nonblocking_ui(win, monkeypatch)
    win.plot_from_workbook("line", new_graph=True)

    analysis = _top_menu(win, "Analysis")
    cc_menu = _submenu(analysis, "Cross-Correlation")
    pk_menu = _submenu(analysis, "Peaks and Baseline")

    _menu_action(cc_menu, "Window...").trigger()
    assert not win.ccDock.isHidden()
    win.ccDock.cbX.setCurrentText("t")
    win.ccDock.cbY1.setCurrentText("signal")
    win.ccDock.cbY2.setCurrentText("other")
    win.ccDock.spinMaxLag.setValue(8.0)
    _menu_action(cc_menu, "Compute in Range").trigger()
    assert "best r:" in win.ccDock.txt.toPlainText()

    _menu_action(pk_menu, "Peak Settings...").trigger()
    assert not win.pkDock.isHidden()
    win.pkDock.cbX.setCurrentText("t")
    win.pkDock.cbY.setCurrentText("signal")
    win.pkDock.spinMinDist.setValue(2)
    win.pkDock.chkAnnotate.setChecked(False)
    _menu_action(pk_menu, "Detect in Range").trigger()
    assert win.pkDock.table.columnCount() >= 3

    peak_path = tmp_path / "peaks.csv"
    monkeypatch.setattr(type(win), "ask_save_path", lambda self, *_args, **_kwargs: str(peak_path), raising=False)
    _menu_action(pk_menu, "Export Peak Table (CSV/Excel)").trigger()
    assert peak_path.exists()

    _menu_action(pk_menu, "Annotate Peaks").trigger()
    assert win.actPkAnnotate.isChecked()
    _menu_action(pk_menu, "Clear Peaks").trigger()
    assert win.pkDock.table.rowCount() == 0
    assert calls["errors"] == []


def test_annotation_menu_actions_target_active_graph_manager(win, monkeypatch):
    import main_window_menu_mixin as menu_mixin

    _seed_science_book(win)
    win.plot_from_workbook("line", new_graph=True)
    tab = win.tabs.currentWidget()
    manager = tab.annotation_manager
    executed = {}

    class FakeAnnotationListDialog:
        def __init__(self, mgr, parent=None):
            executed["manager"] = mgr
            executed["parent"] = parent

        def exec(self):
            executed["exec"] = True
            return 0

    monkeypatch.setattr(menu_mixin, "AnnotationListDialog", FakeAnnotationListDialog)
    annotation = _top_menu(win, "Annotation")

    _menu_action(annotation, "Enable Annotation Mode").trigger()
    assert manager.enabled

    for action_text, mode in (
        ("Add Text (T)", "text"),
        ("Add Arrow (W)", "arrow"),
        ("Add Line (L)", "line"),
        ("Add Rectangle (R)", "rect"),
        ("Add Ellipse (E)", "ellipse"),
        ("Add Callout (C)", "callout"),
    ):
        _menu_action(annotation, action_text).trigger()
        assert manager.mode == mode

    _menu_action(annotation, "Style Dock...").trigger()
    assert not win.annStyleDock.isHidden()
    _menu_action(annotation, "Manage Annotations").trigger()
    _menu_action(annotation, "Undo").trigger()
    _menu_action(annotation, "Redo").trigger()

    assert executed == {"manager": manager, "parent": win, "exec": True}


def test_gas_sensor_menu_actions_execute_from_menu(win, monkeypatch):
    t = np.linspace(0.0, 120.0, 121)
    response = np.where((t >= 30.0) & (t <= 80.0), 70.0, 100.0)
    win._df = pd.DataFrame({"time": t, "response": response, "conc": np.linspace(1.0, 10.0, len(t))})
    win.workbook.set_dataframe(win._df)
    win.load_columns_from_df()
    calls = _install_nonblocking_ui(win, monkeypatch)

    def gas_form(self, title, fields, description=None):
        result = {}
        for field in fields:
            name = field["name"]
            if name == "y_col":
                result[name] = "response"
            elif name == "t_on":
                result[name] = 30.0
            elif name == "t_off":
                result[name] = 80.0
            elif name == "conc_col":
                result[name] = "conc"
            elif name == "resp_col":
                result[name] = "response"
            elif name == "noise_std":
                result[name] = 0.0
            else:
                result[name] = field.get("default")
        return result

    monkeypatch.setattr(type(win), "ask_form", gas_form, raising=False)
    gas_menu = _submenu(_top_menu(win, "Modules"), "Gas Sensor")

    for text in (
        "Response Analysis (t90)...",
        "Detect Gas Cycles...",
        "Calibration Curve + LOD...",
        "Gas Dilution (ppm)...",
    ):
        _menu_action(gas_menu, text).trigger()

    assert calls["errors"] == []
    assert len(calls["inform"]) >= 4
    assert any("Response" in title for title, _text in calls["inform"])


def test_workflow_tools_menu_actions_execute_from_menu(win, monkeypatch, tmp_path):
    _seed_science_book(win)
    calls = _install_nonblocking_ui(win, monkeypatch)
    tools = _top_menu(win, "Tools")

    win.analysis_history.record("fill_missing", col="signal", method="mean")
    export_path = tmp_path / "workflow.json"
    script_path = tmp_path / "workflow_script.py"
    report_path = tmp_path / "auto_report.html"
    snapshot_path = tmp_path / "snapshot.json"
    save_paths = iter([str(export_path), str(script_path), str(report_path), str(snapshot_path)])
    monkeypatch.setattr(type(win), "ask_save_path", lambda self, *_args, **_kwargs: next(save_paths), raising=False)

    _menu_action_contains(tools, "Analysis History").trigger()
    _menu_action_contains(tools, "Export Workflow").trigger()
    _menu_action_contains(tools, "Generate Python Script").trigger()
    _menu_action_contains(tools, "Auto Report").trigger()
    _menu_action_contains(tools, "Project Snapshot").trigger()
    _menu_action_contains(tools, "Compare", "Snapshot").trigger()
    _menu_action_contains(tools, "Audit Trail").trigger()

    assert export_path.exists()
    assert script_path.exists()
    assert report_path.exists()
    assert snapshot_path.exists()
    assert "Snapshot Compare" in win._datasets
    assert "Audit Trail" in win._datasets

    _seed_science_book(win)
    win._df.loc[0, "signal"] = np.nan
    monkeypatch.setattr(type(win), "ask_open_path", lambda self, *_args, **_kwargs: str(export_path), raising=False)
    _menu_action_contains(tools, "Import Workflow", "Re-run").trigger()
    assert "signal_filled" in win._df.columns

    _menu_action(tools, "Clear Analysis History").trigger()
    assert len(win.analysis_history) == 0
    assert calls["errors"] == []
