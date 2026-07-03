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
from PySide6.QtWidgets import QApplication

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
