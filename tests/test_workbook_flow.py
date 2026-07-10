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


def test_activating_empty_book_clears_previous_active_dataframe(win):
    win._df = win.get_current_dataframe()
    win._current_path = "previous.csv"
    win.workbook.source_df = None

    win._on_book_activated("Book1")

    assert win._df is None
    assert win._current_path is None
    assert win.get_current_dataframe().empty


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


def test_single_selected_x_column_plots_selected_values_against_row_index(win, tmp_path):
    p = tmp_path / "single_selected_x.csv"
    p.write_text("sn,response\n10,100\n20,200\n30,300\n", encoding="utf-8")
    win.load_data(str(p))

    win.workbook.table.clearSelection()
    win.workbook.table.selectColumn(0)  # A(X), selected as the data to plot.
    graphs_before = win.tabs.count()

    win.plot_from_workbook("line")

    assert win.tabs.count() == graphs_before + 1
    ax = win.tabs.currentWidget().get_axes()
    line = ax.get_lines()[-1]
    assert list(line.get_xdata()) == [1.0, 2.0, 3.0]
    assert list(line.get_ydata()) == [10.0, 20.0, 30.0]
    assert ax.get_xlabel() == "Row"
    assert ax.get_ylabel() == "sn"
    assert win.cbY.currentText() == "sn"


def test_single_selected_y_column_plots_selected_values_against_row_index(win, tmp_path):
    p = tmp_path / "single_selected_y.csv"
    p.write_text("sn,response\n10,100\n20,200\n30,300\n", encoding="utf-8")
    win.load_data(str(p))

    win.workbook.table.clearSelection()
    win.workbook.table.selectColumn(1)  # One selected column should behave like Excel.

    win.plot_from_workbook("line")

    ax = win.tabs.currentWidget().get_axes()
    line = ax.get_lines()[-1]
    assert list(line.get_xdata()) == [1.0, 2.0, 3.0]
    assert list(line.get_ydata()) == [100.0, 200.0, 300.0]
    assert ax.get_xlabel() == "Row"
    assert ax.get_ylabel() == "response"


def test_overlay_plots_into_current_graph_without_new_window(win):
    from core.plot_mode import PlotMode
    # overlay must ADD a series → force OVERLAY mode (don't depend on ambient
    # plot_mode left over from other tests; REPLACE mode would clear first)
    win.plot_mode = PlotMode.OVERLAY

    _type_into_book1(win, [(0, 4.0), (1, 5.0)])
    win.plot_from_workbook("line")  # creates a graph first
    graphs_before = win.tabs.count()

    win.workbook.overlay_requested.emit("line")

    assert win.tabs.count() == graphs_before  # no new window
    ax = win.tabs.currentWidget().get_axes()
    assert len(ax.get_lines()) >= 2  # overlay added a second series


def test_multiseries_workbook_plot_uses_explicit_requests(win):
    from PySide6.QtCore import QItemSelectionModel

    wb = win.workbook
    wb.add_data_column()
    wb.set_meta(0, long_name="t")
    wb.set_meta(1, long_name="signal_a")
    wb.set_meta(2, long_name="signal_b")
    for row, values in enumerate([(0, 1, 10), (1, 2, 20), (2, 3, 30)]):
        for column, value in enumerate(values):
            wb.table.item(META_ROW_COUNT + row, column).setText(str(value))

    wb.table.setCurrentCell(META_ROW_COUNT, 1)
    second_y = wb.table.model().index(META_ROW_COUNT, 2)
    wb.table.selectionModel().select(second_y, QItemSelectionModel.Select)

    win.plot_from_workbook("line")

    ax = win.tabs.currentWidget().get_axes()
    assert [line.get_label() for line in ax.get_lines()] == [
        "signal_a vs t",
        "signal_b vs t",
    ]
    assert [list(line.get_ydata()) for line in ax.get_lines()] == [
        [1.0, 2.0, 3.0],
        [10.0, 20.0, 30.0],
    ]
    assert win.cbY.currentText() == "signal_a"


def test_plot_toolbar_origin_bar_exists_and_plots(win):
    from PySide6.QtCore import Qt

    assert hasattr(win, "plot_toolbar")
    assert win.toolBarArea(win.plot_toolbar) == Qt.TopToolBarArea
    assert hasattr(win, "function_toolbar")
    assert win.toolBarArea(win.function_toolbar) == Qt.TopToolBarArea
    assert win.plot_toolbar.iconSize().width() == 16
    assert win.plot_toolbar.iconSize().height() == 16
    assert win.function_toolbar.iconSize().width() == 16
    assert win.function_toolbar.iconSize().height() == 16
    assert set(win.plot_bar_actions) == {"line", "scatter", "linesymbol", "bar", "histogram", "gallery"}
    plot_icon_keys = [
        action.property("toolbarIconKey")
        for toolbar in (win.plot_toolbar, win.function_toolbar)
        for action in toolbar.actions()
        if not action.isSeparator()
    ]
    assert all(plot_icon_keys)
    assert len(plot_icon_keys) == len(set(plot_icon_keys))

    _type_into_book1(win, [(0, 7.0), (1, 8.0)])
    graphs_before = win.tabs.count()
    win.plot_bar_actions["line"].trigger()
    assert win.tabs.count() == graphs_before + 1
    ax = win.tabs.currentWidget().get_axes()
    assert list(ax.get_lines()[-1].get_ydata()) == [7.0, 8.0]


def test_top_chart_menu_matches_origin_workflow(win):
    menu_titles = [
        action.menu().title()
        for action in win.menuBar().actions()
        if action.menu() is not None
    ]
    assert "Charts" in menu_titles
    assert win.chartsMenu.category_list.count() >= 7
    assert win.chartsMenu._host.size().width() >= 900

    _type_into_book1(win, [(0, 2.0), (1, 4.0), (2, 8.0)])
    graphs_before = win.tabs.count()
    basic_row = list(win.chartsMenu._categories).index("Basic 2D")
    win.chartsMenu._show_category(basic_row)
    line_tile = next(
        tile for tile in win.chartsMenu._tiles if tile.text() == "Line"
    )

    line_tile.click()

    assert win.tabs.count() == graphs_before + 1
    ax = win.tabs.currentWidget().get_axes()
    assert list(ax.get_lines()[-1].get_ydata()) == [2.0, 4.0, 8.0]


def test_process_menu_exposes_signal_transforms(win):
    process_menu = next(
        action.menu()
        for action in win.menuBar().actions()
        if action.menu() is not None and action.menu().title().replace("&", "") == "Process"
    )
    submenus = {
        action.menu().title(): action.menu()
        for action in process_menu.actions()
        if action.menu() is not None
    }
    assert "Frequency & Spectrum" in submenus
    assert "Smoothing & Filters" in submenus
    assert "Signal Transforms" in submenus
    assert "Correlation & Convolution" in submenus
    signal_titles = [action.text().replace("…", "...") for action in submenus["Signal Transforms"].actions()]
    spectrum_titles = [action.text().replace("…", "...") for action in submenus["Frequency & Spectrum"].actions()]
    correlation_titles = [
        action.text().replace("…", "...")
        for action in submenus["Correlation & Convolution"].actions()
    ]
    assert "Hilbert Transform..." in signal_titles
    assert "Envelope Detection..." in signal_titles
    assert "Instantaneous Frequency..." in signal_titles
    assert "Zero Padding..." in signal_titles
    assert "IFFT..." in spectrum_titles
    assert "STFT..." in spectrum_titles
    assert "Auto-correlation..." in correlation_titles
    assert "Convolution..." in correlation_titles
    assert "Deconvolution..." in correlation_titles


def test_invalid_workbook_plot_does_not_leave_blank_graph(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    wb = win.workbook
    wb.set_meta(0, long_name="x")
    wb.set_meta(1, long_name="label")
    for row, values in enumerate([(0, "A"), (1, "B"), (2, "C")]):
        for column, value in enumerate(values):
            wb.table.item(META_ROW_COUNT + row, column).setText(str(value))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: None))
    graphs_before = win.tabs.count()

    win.plot_from_workbook("line")

    assert win.tabs.count() == graphs_before


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
    """P4: the Data panel is gone (Origin-pure shell) — the rail now only
    hosts specialty modules (Gas Sensor), and every widget alias mixins rely
    on lives on as a hidden state-holder."""
    assert win.shell.context_widget("data") is None
    assert win.shell.context_widget("modules") is win.modules_panel
    assert win.modules_panel.module_widget("gas_sensor") is win.gas_sensor_panel
    assert win.modules_panel.module_widget("electrochemistry") is win.electrochemistry_panel
    assert win.modules_panel.module_widget("spectroscopy") is win.spectroscopy_panel
    assert win.modules_panel.module_widget("materials") is win.materials_panel
    assert win.modules_panel.module_widget("physics_lab") is win.physics_panel
    assert win.shell.context_widget("gas_sensor") is None
    assert win.shell.rail.isHidden()
    assert win.shell.context_stack.isHidden()
    assert win.shell.side_panel_widget("Project Explorer (1)") is win.project_explorer
    assert win.shell.side_panel_widget("Messages Log") is win.op_log_dock
    assert win.shell.side_panel_widget("Smart Hint Log") is win.ai_dock
    assert win.shell.side_tabs.is_collapsed()
    assert win.shell.dock_tabs.isHidden()
    assert win._panel_left.isHidden()
    assert win.panel_plot.isHidden()
    for alias in ("cbX", "cbY",
                  "btnLine", "btnScatter", "btnClear", "btnCurveFit",
                  "lblFile", "chkCross", "btnBoxZoom", "btnOpenData"):
        assert getattr(win, alias) is not None
    assert not hasattr(win, "spLineWidth")
    assert not hasattr(win, "chkMarker")
    assert win.current_plot_options().line_width == 2


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


def test_main_function_toolbar_uses_small_unique_semantic_icons(win):
    assert win.tb.iconSize().width() == 16
    assert win.tb.iconSize().height() == 16
    assert win.function_toolbar.iconSize().width() == 16
    assert win.function_toolbar.iconSize().height() == 16

    icon_keys = [
        action.property("toolbarIconKey")
        for toolbar in (win.tb, win.function_toolbar)
        for action in toolbar.actions()
        if not action.isSeparator()
    ]

    assert all(icon_keys)
    assert len(icon_keys) == len(set(icon_keys))
    assert len(icon_keys) >= 70
    for key in (
        "open",
        "use_active_book",
        "plot_line",
        "plot_scatter",
        "plot_gallery",
        "moving_average",
        "fill_missing",
        "butterworth",
        "hilbert",
        "stats",
        "peak_detect",
        "ann_text",
        "workflow_history",
    ):
        assert key in win.toolbar_actions
    for specialty_key in ("gas_response", "gas_cycles", "gas_calibration", "gas_dilution"):
        assert specialty_key not in win.toolbar_actions


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
    assert win._activate_book_by_name("alpha.csv [table]") is True
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
