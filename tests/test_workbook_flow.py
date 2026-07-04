"""End-to-end behavioral test of the core UX flow:

    พิมพ์ข้อมูลลง Book1 → "ใช้ข้อมูลนี้" → เลือกคอลัมน์ → พล็อต

Runs through the real MainWindow (offscreen) so it exercises the actual
wiring: WorkbookWidget signals → adopt_workbook_data → cbX/cbY → plot_line.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from widgets.workbook import META_ROW_COUNT


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main
    w = app_main.MainWindow()
    yield w
    w.close()


def _type_into_book1(win, rows):
    wb = win.workbook
    wb.set_meta(0, long_name="t")
    wb.set_meta(1, long_name="signal")
    for r, (xv, yv) in enumerate(rows):
        wb.table.item(META_ROW_COUNT + r, 0).setText(str(xv))
        wb.table.item(META_ROW_COUNT + r, 1).setText(str(yv))


def test_typed_data_becomes_active_dataframe(win):
    _type_into_book1(win, [(0, 1.0), (1, 4.0), (2, 9.0), (3, 16.0)])

    assert win.adopt_workbook_data() is True

    assert list(win._df.columns) == ["t", "signal"]
    assert len(win._df) == 4
    assert win._df["signal"].tolist() == [1.0, 4.0, 9.0, 16.0]
    # column pickers are ready for step ②
    x_items = [win.cbX.itemText(i) for i in range(win.cbX.count())]
    assert x_items == ["t", "signal"]


def test_workbook_use_data_signal_reaches_mainwindow(win):
    _type_into_book1(win, [(0, 5.0), (1, 6.0)])

    win.workbook.use_data_requested.emit()

    assert win._df is not None
    assert win._df["signal"].tolist() == [5.0, 6.0]


def test_plot_from_workbook_draws_typed_data(win):
    _type_into_book1(win, [(0, 1.0), (1, 2.0), (2, 3.0)])

    win.plot_from_workbook("line")

    ax = win.tabs.currentWidget().get_axes()
    lines = ax.get_lines()
    assert lines, "plot_from_workbook must draw at least one line"
    ydata = list(lines[-1].get_ydata())
    assert ydata == [1.0, 2.0, 3.0]
    assert win.cbX.currentText() == "t"
    assert win.cbY.currentText() == "signal"


def test_empty_sheet_is_rejected_politely(win, monkeypatch):
    # fresh window has an empty Book1 → adopting must fail without crashing
    infos = []
    monkeypatch.setattr(
        type(win), "inform", lambda self, t, x: infos.append(t), raising=False)
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: infos.append("info")))

    assert win.adopt_workbook_data() is False
    assert win._df is None or getattr(win._df, "empty", False) or infos
