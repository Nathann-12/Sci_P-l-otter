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


def test_plot_from_workbook_creates_new_graph_with_typed_data(win):
    _type_into_book1(win, [(0, 1.0), (1, 2.0), (2, 3.0)])
    graphs_before = win.tabs.count()

    win.plot_from_workbook("line")  # Origin default: new graph window

    assert win.tabs.count() == graphs_before + 1
    ax = win.tabs.currentWidget().get_axes()
    lines = ax.get_lines()
    assert lines, "plot_from_workbook must draw at least one line"
    ydata = list(lines[-1].get_ydata())
    assert ydata == [1.0, 2.0, 3.0]
    assert win.cbX.currentText() == "t"
    assert win.cbY.currentText() == "signal"


def test_overlay_plots_into_current_graph_without_new_window(win):
    _type_into_book1(win, [(0, 4.0), (1, 5.0)])
    win.plot_from_workbook("line")  # creates a graph first
    graphs_before = win.tabs.count()

    win.workbook.overlay_requested.emit("line")

    assert win.tabs.count() == graphs_before  # no new window
    ax = win.tabs.currentWidget().get_axes()
    assert len(ax.get_lines()) >= 2  # overlay added a second series


def test_plot_toolbar_origin_bar_exists_and_plots(win):
    from PySide6.QtCore import Qt

    assert hasattr(win, "plot_toolbar")
    assert win.toolBarArea(win.plot_toolbar) == Qt.BottomToolBarArea
    assert set(win.plot_bar_actions) == {"line", "scatter", "linesymbol", "bar", "histogram"}

    _type_into_book1(win, [(0, 7.0), (1, 8.0)])
    graphs_before = win.tabs.count()
    win.plot_bar_actions["line"].trigger()
    assert win.tabs.count() == graphs_before + 1
    ax = win.tabs.currentWidget().get_axes()
    assert list(ax.get_lines()[-1].get_ydata()) == [7.0, 8.0]


def test_left_panel_plot_controls_fit_thai_text(win):
    """Regression: the ② card clipped Thai vowels because CompactPlotPanel
    used fixed 28px heights and a side-by-side form layout. Fields must be
    height-flexible (no fixed max) and full-width in the narrow panel."""
    from PySide6.QtWidgets import QSizePolicy
    panel = win.panel_plot
    QWIDGETSIZE_MAX = 16777215
    for widget in (panel.cbo_x, panel.cbo_y, panel.spin_width):
        assert widget.maximumHeight() == QWIDGETSIZE_MAX  # not setFixedHeight
        assert widget.minimumHeight() >= 30
    for cb in (panel.cbo_x, panel.cbo_y):
        assert cb.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding


def test_origin_pure_shell_no_left_panel_but_aliases_survive(win):
    """P4: the Data panel is gone (Origin-pure shell) — no context registered,
    rail hidden, and every widget alias mixins rely on lives on as a hidden
    state-holder."""
    assert win.shell.context_widget("data") is None
    assert win.shell.rail.isHidden()
    assert win.shell.context_stack.isHidden()
    assert win._panel_left.isHidden()
    assert win.panel_plot.isHidden()
    for alias in ("cbX", "cbY", "spLineWidth", "chkMarker",
                  "btnLine", "btnScatter", "btnClear", "btnCurveFit",
                  "lblFile", "chkCross", "btnBoxZoom", "btnOpenData"):
        assert getattr(win, alias) is not None


def test_crosshair_and_boxzoom_live_on_the_toolbar(win):
    """P4: graph tools moved from the left panel to checkable toolbar actions;
    the crosshair action drives the hidden chkCross so old wiring + session
    persistence still work."""
    assert win.actCrosshair.isCheckable()
    win.actCrosshair.setChecked(True)
    assert win.chkCross.isChecked() is True
    win.actCrosshair.setChecked(False)
    assert win.chkCross.isChecked() is False
    assert win.actBoxZoom is not None
    toolbar_actions = win.tb.actions()
    assert win.actCrosshair in toolbar_actions
    assert win.actBoxZoom in toolbar_actions


def test_multibook_one_file_one_book_and_active_switch(win, tmp_path):
    """Origin model: each opened file becomes its own Book; activating a Book
    switches the working DataFrame."""
    import pandas as pd

    a = tmp_path / "alpha.csv"
    a.write_text("t,va\n0,1\n1,2\n", encoding="utf-8")
    b = tmp_path / "beta.csv"
    b.write_text("t,vb\n0,10\n1,20\n", encoding="utf-8")

    books_before = len(win.mdi._books)
    win.load_data(str(a))
    win.load_data(str(b))

    assert len(win.mdi._books) == books_before + 2
    # last opened book is active → its data is the working df
    assert "vb" in win._df.columns
    assert win._df["vb"].tolist() == [10, 20]

    # switch back to the first file's Book → df follows
    assert win._activate_book_by_name("alpha.csv [ตาราง]") is True
    assert "va" in win._df.columns
    assert win._df["va"].tolist() == [1, 2]
    x_items = [win.cbX.itemText(i) for i in range(win.cbX.count())]
    assert x_items == ["t", "va"]


def test_multibook_plot_uses_active_book(win, tmp_path):
    p = tmp_path / "gamma.csv"
    p.write_text("t,g\n0,5\n1,6\n2,7\n", encoding="utf-8")
    win.load_data(str(p))

    graphs_before = win.tabs.count()
    win.plot_from_workbook("line")

    assert win.tabs.count() == graphs_before + 1
    ax = win.tabs.currentWidget().get_axes()
    assert list(ax.get_lines()[-1].get_ydata()) == [5.0, 6.0, 7.0]


def test_plot_respects_set_as_x_designation(win, tmp_path):
    """Origin Set As: after designating column C as X, plots use C for x-data."""
    p = tmp_path / "delta.csv"
    p.write_text("a,b,c\n1,10,100\n2,20,200\n3,30,300\n", encoding="utf-8")
    win.load_data(str(p))

    win.workbook.set_designation(2, "X")  # C(X); A demoted to Y
    win.plot_from_workbook("line")

    ax = win.tabs.currentWidget().get_axes()
    line = ax.get_lines()[-1]
    assert list(line.get_xdata()) == [100.0, 200.0, 300.0]
    assert win.cbX.currentText() == "c"


def test_auto_x_uses_time_column_when_loading_file(win, tmp_path):
    p = tmp_path / "timed.csv"
    p.write_text("volt,time\n5,0\n6,1\n7,2\n", encoding="utf-8")
    win.load_data(str(p))

    win.plot_from_workbook("line")

    ax = win.tabs.currentWidget().get_axes()
    line = ax.get_lines()[-1]
    # X came from the auto-designated "time" column, Y from "volt"
    assert list(line.get_xdata()) == [0.0, 1.0, 2.0]
    assert list(line.get_ydata()) == [5.0, 6.0, 7.0]


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
