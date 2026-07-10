from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("PySide6")

import main_window_export_mixin as export_mixin_module
from main_window_export_mixin import MainWindowExportMixin


class _ComboBoxStub:
    def __init__(self, text: str = "", count: int = 1):
        self._text = text
        self._count = count

    def currentText(self):
        return self._text

    def count(self):
        return self._count


class _StatusBarStub:
    def __init__(self):
        self.messages = []

    def showMessage(self, message):
        self.messages.append(message)


class _MessageBoxRecorder:
    def __init__(self):
        self.calls = []

    def critical(self, parent, title, message):
        self.calls.append(("critical", title, message))

    def information(self, parent, title, message):
        self.calls.append(("information", title, message))


class _LineStub:
    def __init__(self, xdata, ydata, label):
        self._xdata = xdata
        self._ydata = ydata
        self._label = label

    def get_xdata(self, orig=False):
        return self._xdata

    def get_ydata(self, orig=False):
        return self._ydata

    def get_label(self):
        return self._label


class _AxesStub:
    def __init__(self, xlim=(0.0, 1.0), lines=None):
        self._xlim = xlim
        self._lines = list(lines or [])

    def get_xlim(self):
        return self._xlim

    def get_lines(self):
        return list(self._lines)


class _FigureStub:
    def __init__(self):
        self.saved = []

    def savefig(self, path, **kwargs):
        self.saved.append((path, kwargs))


class _CanvasStub:
    def __init__(self, ax):
        self.ax = ax
        self.fig = _FigureStub()


class _WindowStub(MainWindowExportMixin):
    def __init__(self):
        self.current_aggregated_df = None
        self._fft_df = None
        self._fft_meta = {}
        self._df = None
        self.cbX = _ComboBoxStub()
        self.canvas = _CanvasStub(_AxesStub())
        self._status_bar = _StatusBarStub()

    def statusBar(self):
        return self._status_bar

    def get_current_dataframe(self):
        return self._df if isinstance(self._df, pd.DataFrame) else pd.DataFrame()

    def selected_x_column(self):
        return self.cbX.currentText()

    def active_axes(self):
        return self.canvas.ax


def test_mixin_exposes_export_methods():
    expected = {
        "export_aggregated_csv",
        "export_fft_dialog",
        "_line_to_numeric_for_export",
        "export_visible_range_csv",
        "export_png",
        "export_figures_batch",
    }

    assert expected.issubset(set(dir(MainWindowExportMixin)))


def test_export_aggregated_csv_writes_current_dataframe(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(export_mixin_module, "QMessageBox", recorder)

    out_path = tmp_path / "aggregate.csv"
    monkeypatch.setattr(
        export_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "CSV (*.csv)"),
    )

    window = _WindowStub()
    window.current_aggregated_df = pd.DataFrame({"group": ["a", "b"], "total": [1, 2]})

    window.export_aggregated_csv()

    saved = pd.read_csv(out_path)
    assert saved.to_dict(orient="list") == {"group": ["a", "b"], "total": [1, 2]}
    assert window.statusBar().messages[-1] == f"Aggregate CSV saved: {out_path}"
    assert recorder.calls == []


def test_export_fft_dialog_csv_branch_writes_fft_dataframe(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(export_mixin_module, "QMessageBox", recorder)
    monkeypatch.setattr(
        export_mixin_module.QInputDialog,
        "getItem",
        lambda *args, **kwargs: ("CSV (.csv)", True),
    )

    out_path = tmp_path / "fft_result.csv"
    monkeypatch.setattr(
        export_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "CSV (*.csv)"),
    )

    window = _WindowStub()
    window._fft_df = pd.DataFrame(
        {
            "freq_Hz": [0.5, 1.0],
            "amplitude": [10.0, 4.0],
            "power": [100.0, 16.0],
        }
    )
    window._fft_meta = {"fs": 2.0, "x_col": "time", "y_col": "value"}

    window.export_fft_dialog()

    saved = pd.read_csv(out_path)
    assert saved.equals(window._fft_df)
    assert window.statusBar().messages[-1] == f"CSV saved: {out_path}"
    assert recorder.calls == []


def test_export_visible_range_csv_filters_dataframe_by_current_xlim(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(export_mixin_module, "QMessageBox", recorder)

    out_path = tmp_path / "visible.csv"
    monkeypatch.setattr(
        export_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "CSV (*.csv)"),
    )

    window = _WindowStub()
    window._df = pd.DataFrame({"time": [0, 1, 2, 3], "value": [10, 20, 30, 40]})
    window.cbX = _ComboBoxStub("time", count=2)
    window.canvas = _CanvasStub(_AxesStub(xlim=(0.5, 2.5)))

    window.export_visible_range_csv()

    saved = pd.read_csv(out_path)
    assert saved.to_dict(orient="list") == {"time": [1, 2], "value": [20, 30]}
    assert window.statusBar().messages[-1] == f"Visible range CSV saved: {out_path}"
    assert recorder.calls == []


def test_export_visible_range_csv_falls_back_to_plot_lines(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(export_mixin_module, "QMessageBox", recorder)

    out_path = tmp_path / "visible_fallback.csv"
    monkeypatch.setattr(
        export_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "CSV (*.csv)"),
    )

    window = _WindowStub()
    window._df = pd.DataFrame({"time": [10.0, 11.0], "value": [0, 1]})
    window.cbX = _ComboBoxStub("time", count=1)
    line = _LineStub([0.0, 1.0, 2.0], [5.0, 6.0, 7.0], "signal")
    window.canvas = _CanvasStub(_AxesStub(xlim=(0.5, 1.5), lines=[line]))

    window.export_visible_range_csv()

    saved = pd.read_csv(out_path)
    assert saved.to_dict(orient="list") == {"time": [1.0], "signal": [6.0]}
    assert window.statusBar().messages[-1] == f"Visible range CSV saved: {out_path}"
    assert recorder.calls == []


def test_export_png_uses_canvas_figure_savefig(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(export_mixin_module, "QMessageBox", recorder)

    out_path = tmp_path / "plot.png"
    monkeypatch.setattr(
        export_mixin_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(out_path), "PNG Image (*.png)"),
    )

    window = _WindowStub()

    window.export_png()

    assert window.canvas.fig.saved == [
        (str(out_path), {"dpi": 300, "bbox_inches": "tight"})
    ]
    assert window.statusBar().messages[-1] == f"Image saved: {out_path}"
    assert recorder.calls == []
