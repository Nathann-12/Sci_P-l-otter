from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("PySide6")

import main_window_session_mixin as session_mixin_module
from main_window_session_mixin import MainWindowSessionMixin


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

    def addItem(self, item):
        text = item.text() if hasattr(item, "text") else str(item)
        self.items.append(_ListItemStub(text))

    def count(self):
        return len(self.items)

    def currentItem(self):
        if self.current_row < 0 or self.current_row >= len(self.items):
            return None
        return self.items[self.current_row]

    def currentRow(self):
        return self.current_row

    def item(self, row):
        return self.items[row]

    def setCurrentRow(self, row):
        self.current_row = row

    def takeItem(self, row):
        return self.items.pop(row)


class _MessageBoxRecorder:
    Yes = object()
    No = object()

    def __init__(self):
        self.calls = []
        self.question_result = self.Yes

    def critical(self, parent, title, message):
        self.calls.append(("critical", title, message))

    def warning(self, parent, title, message):
        self.calls.append(("warning", title, message))

    def information(self, parent, title, message):
        self.calls.append(("information", title, message))

    def question(self, parent, title, message):
        self.calls.append(("question", title, message))
        return self.question_result


class _CloseEventBase:
    def __init__(self):
        self.closed_events = []

    def closeEvent(self, event):
        self.closed_events.append(event)


class _WindowStub(MainWindowSessionMixin, _CloseEventBase):
    def __init__(self):
        _CloseEventBase.__init__(self)
        self._datasets = {}
        self._df = None
        self._current_path = None
        self.lstFiles = _ListWidgetStub()
        self.lblFile = _LabelStub()
        self._status_bar = _StatusBarStub()

    def statusBar(self):
        return self._status_bar


def test_mixin_exposes_session_and_staging_methods():
    expected = {
        "_stage_insert",
        "stage_add_files",
        "stage_use_selected",
        "stage_remove_selected",
        "_load_dataset_from_path",
        "closeEvent",
    }

    assert expected.issubset(set(dir(MainWindowSessionMixin)))


def test_stage_insert_deduplicates_names_and_stores_dataframe_copy():
    window = _WindowStub()
    df = pd.DataFrame({"x": [1, 2]})

    window._stage_insert("sample.csv [ตาราง]", df, "sample.csv")
    window._stage_insert("sample.csv [ตาราง]", df, "sample.csv")

    assert list(window._datasets) == ["sample.csv [ตาราง]", "sample.csv [ตาราง] (2)"]
    assert window.lstFiles.count() == 2
    assert window.statusBar().messages[-1] == "เตรียมข้อมูล: sample.csv [ตาราง] (2)"


def test_load_dataset_from_path_uses_override_name(monkeypatch, tmp_path):
    path = tmp_path / "restored.csv"
    path.write_text("ignored", encoding="utf-8")
    df = pd.DataFrame({"x": [1], "y": [2]})

    monkeypatch.setattr(session_mixin_module, "load_tabular", lambda path_arg, ext: (df, "csv-note"))

    window = _WindowStub()
    restored = window._load_dataset_from_path(str(path), name="Restored Name")

    assert restored == "Restored Name"
    assert "Restored Name" in window._datasets
    assert window._datasets["Restored Name"]["path"] == str(path)


def test_stage_add_files_stages_supported_paths_and_skips_unsupported(monkeypatch, tmp_path):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(session_mixin_module, "QMessageBox", recorder)

    csv_path = tmp_path / "sample.csv"
    txt_path = tmp_path / "notes.unsupported"
    csv_path.write_text("ignored", encoding="utf-8")
    txt_path.write_text("ignored", encoding="utf-8")

    df = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(
        session_mixin_module.QFileDialog,
        "getOpenFileNames",
        lambda *args, **kwargs: ([str(csv_path), str(txt_path)], "Data Files"),
    )
    monkeypatch.setattr(session_mixin_module, "load_tabular", lambda path_arg, ext: (df, "csv-note"))

    window = _WindowStub()
    window.stage_add_files()

    assert list(window._datasets) == ["sample.csv [ตาราง]"]
    assert recorder.calls == [("information", "ข้ามไฟล์", f"นามสกุลไม่รองรับ: {txt_path}")]


def test_stage_use_selected_copies_dataset_and_updates_label(monkeypatch):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(session_mixin_module, "QMessageBox", recorder)

    window = _WindowStub()
    df = pd.DataFrame({"x": [1, 2]})
    window._datasets["sample.csv [ตาราง]"] = {"df": df, "path": "sample.csv"}
    window.lstFiles.addItem("sample.csv [ตาราง]")
    window.lstFiles.setCurrentRow(0)

    window.stage_use_selected()

    assert window._df.equals(df)
    assert window._df is not df
    assert window._current_path == "sample.csv"
    assert window.lblFile.text == "ใช้งานไฟล์: sample.csv [ตาราง]"
    assert recorder.calls == []


def test_stage_remove_selected_confirms_when_removing_active_dataset(monkeypatch):
    recorder = _MessageBoxRecorder()
    monkeypatch.setattr(session_mixin_module, "QMessageBox", recorder)

    window = _WindowStub()
    window._datasets["sample.csv [ตาราง]"] = {"df": pd.DataFrame({"x": [1]}), "path": "sample.csv"}
    window._current_path = "sample.csv"
    window.lstFiles.addItem("sample.csv [ตาราง]")
    window.lstFiles.setCurrentRow(0)

    window.stage_remove_selected()

    assert "sample.csv [ตาราง]" not in window._datasets
    assert window.lstFiles.count() == 0
    assert recorder.calls[0][0] == "question"
    assert window.statusBar().messages[-1] == "นำออกจากรายการแล้ว: sample.csv [ตาราง]"


def test_close_event_saves_session_and_calls_super(monkeypatch):
    saved = []
    monkeypatch.setattr(session_mixin_module.session_store, "save_session", lambda window: saved.append(window))

    window = _WindowStub()
    event = object()

    window.closeEvent(event)

    assert saved == [window]
    assert window.closed_events == [event]
