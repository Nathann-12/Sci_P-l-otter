from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main_window_data_mixin as data_mixin_module
from core.plot_request import PlotOptions
from main_window_actions_mixin import MainWindowActionsMixin
from main_window_data_mixin import MainWindowDataMixin
from main_window_view_access_mixin import MainWindowViewAccessMixin


class _ComboBoxStub:
    def __init__(self):
        self.items = []
        self.current_index = 0

    def clear(self):
        self.items = []
        self.current_index = 0

    def addItems(self, items):
        self.items.extend(items)

    def count(self):
        return len(self.items)

    def currentText(self):
        if not self.items:
            return ""
        return self.items[self.current_index]

    def setCurrentText(self, text):
        self.current_index = self.items.index(text)


class _LabelStub:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _StatusBarStub:
    def __init__(self):
        self.messages = []

    def showMessage(self, message):
        self.messages.append(message)


class _ListItemStub:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _ListWidgetStub:
    def __init__(self):
        self.items = []
        self.current_row = -1

    def addItem(self, text):
        self.items.append(_ListItemStub(text))

    def count(self):
        return len(self.items)

    def setCurrentRow(self, row):
        self.current_row = row

    def currentItem(self):
        if self.current_row < 0 or self.current_row >= len(self.items):
            return None
        return self.items[self.current_row]


class _MessageBoxRecorder:
    def __init__(self):
        self.calls = []

    def critical(self, parent, title, message):
        self.calls.append(("critical", title, message))

    def warning(self, parent, title, message):
        self.calls.append(("warning", title, message))

    def information(self, parent, title, message):
        self.calls.append(("information", title, message))


class _WindowStub(MainWindowDataMixin, MainWindowActionsMixin, MainWindowViewAccessMixin):
    def __init__(self):
        self._df = None
        self._current_path = None
        self._datasets = {}
        self._status_bar = _StatusBarStub()
        self.lblFile = _LabelStub()
        self._sb_rows = _LabelStub()
        self.cbX = _ComboBoxStub()
        self.cbY = _ComboBoxStub()
        self.lstFiles = _ListWidgetStub()
        self.staged = []

    def statusBar(self):
        return self._status_bar

    def selected_y_column(self):
        return self.cbY.currentText()

    def current_plot_options(self):
        return PlotOptions()

    def _stage_insert(self, name, df, path):
        self.staged.append((name, df.copy(), path))
        self._datasets[name] = {"df": df.copy(), "path": path}
        self.lstFiles.addItem(name)


def test_mixin_exposes_target_methods_for_later_mainwindow_integration():
    expected = {
        "open_file",
        "load_data",
        "load_columns_from_df",
        "_convert_to_datetime_if_possible",
        "_check_column_numeric",
        "_get_xy",
        "_is_datetime_column",
    }

    assert expected.issubset(set(dir(MainWindowDataMixin)))


def test_load_columns_from_df_can_pull_from_staged_dataset(monkeypatch):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(data_mixin_module, "QMessageBox", recorder)

    window = _WindowStub()
    df = pd.DataFrame({"time": [1, 2], "value": [10, 20]})
    window._datasets["sample.csv [ตาราง]"] = {"df": df, "path": "sample.csv"}
    window.lstFiles.addItem("sample.csv [ตาราง]")
    window.lstFiles.setCurrentRow(0)

    window.load_columns_from_df()

    assert window._df.equals(df)
    assert window._current_path == "sample.csv"
    assert window.cbX.items == ["time", "value"]
    assert window.cbY.items == ["time", "value"]
    assert window._sb_rows.text == "rows: 2"
    assert recorder.calls == []


def test_convert_to_datetime_if_possible_requires_majority_parseable_values():
    window = _WindowStub()
    window._df = pd.DataFrame(
        {
            "mostly_dates": ["2024-01-01", "2024-01-02", "bad"],
            "mostly_text": ["bad", "still bad", "2024-01-03"],
        }
    )

    ok_dates, parsed_dates = window._convert_to_datetime_if_possible("mostly_dates")
    ok_text, parsed_text = window._convert_to_datetime_if_possible("mostly_text")

    assert ok_dates is True
    assert parsed_dates.notna().sum() == 2
    assert ok_text is False
    assert parsed_text is None


def test_build_plot_request_supports_explicit_columns():
    window = _WindowStub()
    window._df = pd.DataFrame(
        {
            "time": [0, 1, 2],
            "signal_a": [10, 20, 30],
            "signal_b": [3, 4, 5],
        }
    )

    request = window.build_plot_request("time", "signal_b")

    assert request is not None
    assert request.x.tolist() == [0, 1, 2]
    assert request.y.tolist() == [3, 4, 5]
    assert request.x_column == "time"
    assert request.y_column == "signal_b"
    assert request.label == "signal_b vs time"


def test_build_histogram_and_categorical_bar_requests():
    window = _WindowStub()
    window._df = pd.DataFrame(
        {
            "group": ["A", "B", "C"],
            "value": [3, 1, 2],
        }
    )
    options = PlotOptions(histogram_bins=7, fit_normal=True, bar_width=0.5)

    histogram = window.build_histogram_request("value", options)
    bar = window.build_bar_request(
        "group", "value", title="Counts", options=options
    )

    assert histogram is not None
    assert histogram.values.tolist() == [3, 1, 2]
    assert histogram.options is options
    assert bar is not None
    assert bar.x.tolist() == ["A", "B", "C"]
    assert bar.y.tolist() == [3, 1, 2]
    assert bar.options is options


def test_is_datetime_column_rejects_large_numeric_epoch_lookalikes():
    """Regression: a big numeric column (e.g. 5.5e7) must NOT be treated as
    datetime. pd.to_datetime would read it as an epoch offset and succeed, which
    put a DATE locator on a numeric axis -> num2date(5.5e7) overflows the year
    range on draw and blanks/hangs the graph."""
    window = _WindowStub()
    window._df = pd.DataFrame(
        {
            "big": [5.498e7, 5.499e7, 5.500e7, 5.501e7],
            "small_int": [1, 2, 3, 4],
            "real_dates": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        }
    )

    assert window._is_datetime_column("big") is False
    assert window._is_datetime_column("small_int") is False
    # genuine string dates are still detected
    assert window._is_datetime_column("real_dates") is True


def test_check_column_numeric_accepts_datetime_and_rejects_sparse_numeric():
    window = _WindowStub()
    window._df = pd.DataFrame(
        {
            "dt": pd.date_range("2024-01-01", periods=4, freq="h"),
            "mixed": ["1", "bad", "also bad", "still bad"],
        }
    )

    dt_ok, dt_message = window._check_column_numeric("dt")
    mixed_ok, mixed_message = window._check_column_numeric("mixed")

    assert dt_ok is True
    assert "datetime" in dt_message
    assert mixed_ok is False
    assert "25.0%" in mixed_message


def test_get_xy_converts_datetime_strings_to_relative_seconds(monkeypatch):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(data_mixin_module, "QMessageBox", recorder)

    window = _WindowStub()
    window._df = pd.DataFrame(
            {
                "time": [
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:01:00",
                    "2024-01-01 00:02:00",
                ],
                "value": [1.5, 2.5, 3.5],
            }
        )
    window.cbX.addItems(["time", "value"])
    window.cbY.addItems(["time", "value"])
    window.cbX.setCurrentText("time")
    window.cbY.setCurrentText("value")

    x, y = window._get_xy()

    assert recorder.calls == []
    np.testing.assert_allclose(x, np.array([0.0, 60.0, 120.0]))
    np.testing.assert_allclose(y, np.array([1.5, 2.5, 3.5]))


def test_load_data_updates_state_for_tabular_files(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(data_mixin_module, "QMessageBox", recorder)

    window = _WindowStub()
    path = tmp_path / "sample.csv"
    path.write_text("ignored", encoding="utf-8")
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})

    monkeypatch.setattr(data_mixin_module, "load_tabular", lambda path_arg, ext: (df, "csv-note"))

    window.load_data(str(path))

    # Origin multi-book: drag & drop opens a new Book via the staging funnel
    assert len(window.staged) == 1
    staged_name, staged_df, staged_path = window.staged[0]
    assert staged_name == "sample.csv [table]"
    assert staged_path == str(path)
    assert staged_df.equals(df)
    assert "Opened as Book" in window.statusBar().messages[-1]
    assert recorder.calls == []


def test_open_file_stages_loaded_dataframe(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(data_mixin_module, "QMessageBox", recorder)

    path = tmp_path / "picked.csv"
    path.write_text("ignored", encoding="utf-8")
    df = pd.DataFrame({"x": [1], "y": [2]})

    monkeypatch.setattr(
        data_mixin_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(path), "Data Files"),
    )
    monkeypatch.setattr(data_mixin_module, "load_tabular", lambda path_arg, ext: (df, "csv-note"))

    window = _WindowStub()
    window.open_file()

    assert len(window.staged) == 1
    staged_name, staged_df, staged_path = window.staged[0]
    assert staged_name == "picked.csv [table]"
    assert staged_path == str(path)
    assert staged_df.equals(df)
    # Origin multi-book: the file opens as a Book (no staging-list selection)
    assert "Opened as Book" in window.statusBar().messages[-1]
    assert recorder.calls == []


def test_is_datetime_column_detects_existing_datetime_dtype():
    window = _WindowStub()
    window._df = pd.DataFrame({"time": pd.date_range("2024-01-01", periods=2, freq="D")})

    assert window._is_datetime_column("time") is True
    assert window._is_datetime_column("missing") is False
