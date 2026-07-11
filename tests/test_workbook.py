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

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange, QToolBar

from widgets.workbook import (
    META_ROW_COUNT,
    META_ROWS,
    WorkbookWidget,
    column_header_text,
    column_label,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_column_label_and_header_text():
    assert column_label(0) == "A"
    assert column_label(1) == "B"
    assert column_label(25) == "Z"
    assert column_label(26) == "AA"
    # first column is X, rest are Y
    assert column_header_text(0) == "A(X)"
    assert column_header_text(1) == "B(Y)"
    assert column_header_text(2) == "C(Y)"


def test_empty_defaults(qapp):
    wb = WorkbookWidget()
    # default empty: 2 columns, 32 data rows + 4 meta rows
    assert wb.table.columnCount() == 2
    assert wb.table.rowCount() == META_ROW_COUNT + 32
    assert wb.data_row_count == 32

    # column headers A(X) / B(Y)
    assert wb.table.horizontalHeaderItem(0).text() == "A(X)"
    assert wb.table.horizontalHeaderItem(1).text() == "B(Y)"

    # meta rows present at the top of the vertical header
    for i, name in enumerate(META_ROWS):
        assert wb.table.verticalHeaderItem(i).text() == name
    # first data row labelled "1"
    assert wb.table.verticalHeaderItem(META_ROW_COUNT).text() == "1"


def test_action_bar_buttons_exist(qapp):
    wb = WorkbookWidget()
    for name in ("btn_add_row", "btn_add_col", "btn_use_data",
                 "btn_plot_line", "btn_plot_scatter"):
        assert getattr(wb, name) is not None
    assert wb.btn_add_row.text() == "+R"
    assert wb.btn_add_col.text() == "+C"
    assert wb.btn_use_data.text() == "Use"
    assert wb.btn_add_row.isHidden()
    assert wb.btn_add_col.isHidden()
    assert wb.btn_use_data.isHidden()
    assert wb.btn_plot_line.isHidden()
    assert wb.btn_plot_scatter.isHidden()
    assert wb.findChild(QToolBar, "WorkbookBottomBar") is wb.workbook_toolbar
    assert wb.layout().indexOf(wb.workbook_toolbar) > wb.layout().indexOf(wb.table)
    assert wb.workbook_toolbar.iconSize().width() == 16
    assert wb.workbook_toolbar.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert "workbook_plot_line" in [
        action.property("toolbarIconKey")
        for action in wb.workbook_toolbar.actions()
        if not action.isSeparator()
    ]


def test_add_data_row_and_column_grow_the_sheet(qapp):
    wb = WorkbookWidget()
    rows0, cols0 = wb.table.rowCount(), wb.table.columnCount()
    wb.add_data_row()
    wb.add_data_column()
    assert wb.table.rowCount() == rows0 + 1
    assert wb.table.columnCount() == cols0 + 1
    # new column gets the next spreadsheet letter header
    assert wb.table.horizontalHeaderItem(cols0).text() == column_header_text(cols0)
    # new cells are real items (styling stays consistent)
    assert wb.table.item(rows0, 0) is not None
    assert wb.table.item(0, cols0) is not None


def test_action_bar_emits_workflow_signals(qapp):
    wb = WorkbookWidget()
    got = []
    wb.use_data_requested.connect(lambda: got.append("use"))
    wb.plot_requested.connect(lambda style: got.append(style))

    wb.btn_use_data.click()
    wb.btn_plot_line.click()
    wb.btn_plot_scatter.click()

    assert got == ["use", "line", "scatter"]


def test_cell_context_menu_groups_real_workflow_actions(qapp):
    wb = WorkbookWidget()
    menu = wb._build_cell_context_menu()
    titles = [
        action.menu().title()
        for action in menu.actions()
        if action.menu() is not None
    ]
    assert titles == [
        "Plot New Graph",
        "Add To Current Graph",
        "Set Selected Columns As",
        "Edit",
        "Structure",
    ]
    plot_titles = [action.text() for action in menu.actions()[0].menu().actions()]
    structure_titles = [action.text() for action in menu.actions()[-1].menu().actions()]
    assert plot_titles == ["Line", "Scatter", "Line + Symbol", "Column / Bar", "Histogram"]
    assert "Insert Row Below" in structure_titles
    assert "Delete Selected Columns" in structure_titles


def test_bottom_workbook_toolbar_triggers_origin_flow_actions(qapp):
    wb = WorkbookWidget()
    got = []
    wb.use_data_requested.connect(lambda: got.append("use"))
    wb.plot_requested.connect(lambda style: got.append(f"plot:{style}"))
    wb.overlay_requested.connect(lambda style: got.append(f"overlay:{style}"))

    wb.workbook_actions["use_data"].trigger()
    wb.workbook_actions["plot_line"].trigger()
    wb.workbook_actions["overlay_scatter"].trigger()

    rows0, cols0 = wb.table.rowCount(), wb.table.columnCount()
    wb.workbook_actions["add_row"].trigger()
    wb.workbook_actions["add_column"].trigger()

    assert got == ["use", "plot:line", "overlay:scatter"]
    assert wb.table.rowCount() == rows0 + 1
    assert wb.table.columnCount() == cols0 + 1


def test_header_context_menu_targets_clicked_column(qapp):
    wb = WorkbookWidget()
    menu = wb._build_header_context_menu(1)
    titles = [
        action.menu().title()
        for action in menu.actions()
        if action.menu() is not None
    ]
    assert titles == [
        "Set Column B As",
        "Plot Column",
        "Add Column To Current Graph",
    ]

    set_as_menu = menu.actions()[0].menu()
    set_as_menu.actions()[0].trigger()
    assert wb.x_column_index() == 1
    assert wb.table.horizontalHeaderItem(1).text() == "B(X)"


def test_context_edit_clear_and_structure_operations(qapp):
    from PySide6.QtCore import QItemSelectionModel

    wb = WorkbookWidget()
    wb.clear_to_empty(rows=3, cols=3)
    wb.table.item(META_ROW_COUNT + 0, 0).setText("1")
    wb.table.item(META_ROW_COUNT + 0, 1).setText("10")
    wb.table.item(META_ROW_COUNT + 1, 0).setText("2")
    wb.table.item(META_ROW_COUNT + 1, 1).setText("20")

    wb.table.setCurrentCell(META_ROW_COUNT, 1)
    wb.clear_selected_cells()
    assert wb.table.item(META_ROW_COUNT, 1).text() == ""
    assert wb.is_dirty is True

    wb.mark_clean()
    wb.table.clearSelection()
    wb.table.setCurrentCell(META_ROW_COUNT, 0)
    wb.insert_data_row_after_selection()
    assert wb.data_row_count == 4
    assert wb.table.verticalHeaderItem(META_ROW_COUNT + 1).text() == "2"
    assert wb.is_dirty is True

    wb.table.clearSelection()
    wb.table.selectColumn(1)
    wb.delete_selected_columns()
    assert wb.table.columnCount() == 2
    assert wb.table.horizontalHeaderItem(0).text() == "A(X)"

    wb.table.clearSelection()
    first_data_row = wb.table.model().index(META_ROW_COUNT, 0)
    wb.table.selectionModel().select(first_data_row, QItemSelectionModel.Select)
    wb.delete_selected_data_rows()
    assert wb.data_row_count == 3
    assert wb.table.verticalHeaderItem(META_ROW_COUNT).text() == "1"


def test_context_copy_paste_expands_sheet(qapp):
    wb = WorkbookWidget()
    wb.clear_to_empty(rows=1, cols=1)
    QApplication.clipboard().setText("1\t2\n3\t4")

    wb.table.setCurrentCell(META_ROW_COUNT, 0)
    wb.paste_from_clipboard()

    assert wb.table.columnCount() == 2
    assert wb.data_row_count == 2
    assert wb.table.item(META_ROW_COUNT + 1, 1).text() == "4"

    wb.table.clearSelection()
    wb.table.setRangeSelected(
        QTableWidgetSelectionRange(META_ROW_COUNT, 0, META_ROW_COUNT + 1, 1),
        True,
    )
    wb.copy_selection_to_clipboard()
    assert QApplication.clipboard().text().splitlines()[-1] == "3\t4"


def test_selected_column_indexes_and_names(qapp):
    wb = WorkbookWidget()
    wb.set_meta(0, long_name="time")
    wb.set_meta(1, long_name="volt")
    # select one cell in column 1 and one in column 0
    wb.table.setCurrentCell(META_ROW_COUNT, 1)
    from PySide6.QtCore import QItemSelectionModel
    index0 = wb.table.model().index(META_ROW_COUNT + 2, 0)
    wb.table.selectionModel().select(index0, QItemSelectionModel.Select)
    assert wb.selected_column_indexes() == [0, 1]
    assert wb.selected_column_names() == ["time", "volt"]


def test_dataframe_trims_all_empty_rows(qapp):
    wb = WorkbookWidget()  # 32 empty rows
    wb.set_meta(0, long_name="x")
    wb.set_meta(1, long_name="y")
    for r, (xv, yv) in enumerate([("1", "10"), ("2", "20"), ("3", "30")]):
        wb.table.item(META_ROW_COUNT + r, 0).setText(xv)
        wb.table.item(META_ROW_COUNT + r, 1).setText(yv)
    df = wb.dataframe()
    assert len(df) == 3  # 29 empty rows dropped
    assert df["x"].tolist() == [1, 2, 3]
    assert df["y"].tolist() == [10, 20, 30]


def test_default_designations_first_column_is_x(qapp):
    wb = WorkbookWidget()
    assert wb.column_designation(0) == "X"
    assert wb.column_designation(1) == "Y"
    assert wb.x_column_index() == 0
    assert wb.y_column_indexes() == [1]
    assert wb.table.horizontalHeaderItem(0).text() == "A(X)"
    assert wb.table.horizontalHeaderItem(1).text() == "B(Y)"


def test_set_designation_single_x_model_and_header_refresh(qapp):
    wb = WorkbookWidget()
    wb.add_data_column()  # A, B, C
    wb.set_designation(2, "X")
    # promoting C to X demotes A back to Y
    assert wb.x_column_index() == 2
    assert wb.column_designation(0) == "Y"
    assert wb.table.horizontalHeaderItem(2).text() == "C(X)"
    assert wb.table.horizontalHeaderItem(0).text() == "A(Y)"

    wb.set_designation(1, "ignore")
    assert wb.table.horizontalHeaderItem(1).text() == "B"  # no designation suffix
    assert wb.y_column_indexes() == [0]

    import pytest as _pytest
    with _pytest.raises(ValueError):
        wb.set_designation(0, "Z")


def test_auto_x_designation_prefers_time_like_column(qapp):
    wb = WorkbookWidget()
    df = pd.DataFrame({"value": [1.0, 2.0], "timestamp": [10, 20]})
    wb.set_dataframe(df)
    assert wb.x_column_index() == 1  # "timestamp" wins over column 0
    assert wb.table.horizontalHeaderItem(1).text() == "B(X)"
    assert wb.table.horizontalHeaderItem(0).text() == "A(Y)"


def test_dirty_flag_tracks_user_edits_only(qapp):
    wb = WorkbookWidget()
    df = pd.DataFrame({"x": [1.0], "y": [2.0]})
    wb.set_dataframe(df)
    assert wb.is_dirty is False  # programmatic fill stays clean
    wb.table.item(META_ROW_COUNT, 0).setText("9")
    assert wb.is_dirty is True
    wb.mark_clean()
    assert wb.is_dirty is False


def test_header_strip_background_is_styled(qapp):
    # The bare QHeaderView area beyond the last column must carry the dark
    # surface color, otherwise it paints near-black against the themed table.
    wb = WorkbookWidget()
    assert "#WorkbookTable QHeaderView {" in wb.styleSheet()


def test_set_dataframe_fills_grid_and_meta(qapp):
    wb = WorkbookWidget()
    df = pd.DataFrame({"time": [1, 2, 3], "value": [10, 20, 30]})
    wb.set_dataframe(df)

    assert wb.table.columnCount() == 2
    assert wb.data_row_count == 3

    # Long Name meta row carries the df column names
    assert wb.table.item(0, 0).text() == "time"
    assert wb.table.item(0, 1).text() == "value"

    # data values land in the numbered rows (offset by the meta rows)
    assert wb.table.item(META_ROW_COUNT + 0, 0).text() == "1"
    assert wb.table.item(META_ROW_COUNT + 2, 0).text() == "3"
    assert wb.table.item(META_ROW_COUNT + 0, 1).text() == "10"
    assert wb.table.item(META_ROW_COUNT + 2, 1).text() == "30"

    # headers still show Origin-style designations
    assert wb.table.horizontalHeaderItem(0).text() == "A(X)"
    assert wb.table.horizontalHeaderItem(1).text() == "B(Y)"


def test_dataframe_round_trips_values(qapp):
    wb = WorkbookWidget()
    df = pd.DataFrame({"time": [1, 2, 3], "value": [10, 20, 30]})
    wb.set_dataframe(df)

    out = wb.dataframe()
    assert list(out.columns) == ["time", "value"]
    assert out["time"].tolist() == [1, 2, 3]
    assert out["value"].tolist() == [10, 20, 30]


def test_dataframe_uses_letters_without_long_name(qapp):
    wb = WorkbookWidget()
    # type values directly into the data rows of the empty sheet
    wb.table.item(META_ROW_COUNT + 0, 0).setText("5")
    wb.table.item(META_ROW_COUNT + 1, 0).setText("6")

    out = wb.dataframe()
    assert out.columns[0] == "A"
    assert out["A"].iloc[0] == 5
    assert out["A"].iloc[1] == 6


def test_set_meta(qapp):
    wb = WorkbookWidget()
    wb.set_meta(0, long_name="Voltage", units="V", comments="probe 1")
    assert wb.table.item(0, 0).text() == "Voltage"   # Long Name
    assert wb.table.item(1, 0).text() == "V"          # Units
    assert wb.table.item(2, 0).text() == "probe 1"    # Comments


def test_clear_to_empty_resets(qapp):
    wb = WorkbookWidget()
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [5, 6, 7, 8], "c": [9, 10, 11, 12]})
    wb.set_dataframe(df)
    assert wb.table.columnCount() == 3

    wb.clear_to_empty()
    assert wb.table.columnCount() == 2
    assert wb.data_row_count == 32
    assert wb.table.horizontalHeaderItem(0).text() == "A(X)"
    # meta + data cells are blank again
    assert wb.table.item(0, 0).text() == ""
    assert wb.table.item(META_ROW_COUNT, 0).text() == ""


def test_clear_to_empty_custom_size(qapp):
    wb = WorkbookWidget()
    wb.clear_to_empty(rows=5, cols=4)
    assert wb.table.columnCount() == 4
    assert wb.data_row_count == 5
    assert wb.table.horizontalHeaderItem(3).text() == "D(Y)"


def test_existing_workbook_item_brushes_follow_application_theme(qapp):
    from styles.theme import apply_font, apply_qss

    wb = WorkbookWidget()
    wb.show()
    qapp.processEvents()
    family = qapp.font().family()

    try:
        apply_font(qapp, family, 12)
        apply_qss(
            qapp,
            theme_mode="light",
            accent_color="#20B8A6",
            font_family=family,
            font_size=12,
        )
        qapp.processEvents()

        meta_item = wb.table.item(0, 0)
        assert meta_item.background().color() == qapp.palette().color(QPalette.AlternateBase)
        assert meta_item.foreground().color() == qapp.palette().color(QPalette.PlaceholderText)
        assert meta_item.font().family() == qapp.font().family()
        assert meta_item.font().pointSize() == 12
    finally:
        apply_font(qapp, family, 10)
        apply_qss(qapp, theme_mode="dark", font_family=family, font_size=10)
        wb.close()
