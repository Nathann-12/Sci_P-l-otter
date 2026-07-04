"""OriginLab-style data worksheet ("workbook") widget for SciPlotter.

Replicates OriginPro's central worksheet: an Excel-like grid where the first
four rows are metadata header rows (``Long Name``, ``Units``, ``Comments``,
``F(x)=``) followed by numbered data rows (1, 2, 3, ...). Columns are labelled
``A(X)``, ``B(Y)``, ``C(Y)``, ... — the first column defaults to the X
designation, the rest to Y.

The widget is purely PySide6 + pandas (both existing deps) and styles itself via
an embedded stylesheet (objectName ``WorkbookWidget``) so it stays self-contained
and testable.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# Meta rows shown above the numbered data rows (matches OriginPro layout).
META_ROWS: List[str] = ["Long Name", "Units", "Comments", "F(x)="]
META_ROW_COUNT = len(META_ROWS)

# Palette (matches dark_modern.qss / shell.qss).
_BG = "#1e2126"
_SURFACE = "#23272e"
_SURFACE_2 = "#262b33"
_META_BG = "#2b313a"  # slightly lighter "650" shade for meta rows
_HEADER_BG = "#283446"  # blue-tinted column header row
_BORDER = "#3a3f44"
_GRID = "#2f343b"
_ACCENT = "#4F9CF9"
_TEXT = "#e6e6e6"
_MUTED = "#8b929c"

_WORKBOOK_QSS = f"""
#WorkbookWidget {{
    background-color: {_BG};
}}

#WorkbookTable {{
    background-color: {_SURFACE};
    alternate-background-color: {_SURFACE_2};
    gridline-color: {_GRID};
    border: 1px solid {_BORDER};
    border-radius: 0px;
    padding: 0px;
    color: {_TEXT};
    selection-background-color: {_ACCENT};
    selection-color: #ffffff;
    outline: none;
}}

#WorkbookTable::item {{
    padding: 2px 6px;
    border: none;
}}

#WorkbookTable::item:selected {{
    background-color: {_ACCENT};
    color: #ffffff;
}}

/* Header strip itself (the empty area beyond the last column/row would
   otherwise paint near-black and clash with the dark surface) */
#WorkbookTable QHeaderView {{
    background-color: {_SURFACE};
    border: none;
}}

/* Column headers: blue-tinted, bold */
#WorkbookTable QHeaderView::section:horizontal {{
    background-color: {_HEADER_BG};
    color: {_TEXT};
    border: none;
    border-right: 1px solid {_BORDER};
    border-bottom: 1px solid {_BORDER};
    padding: 4px 6px;
    font-weight: 600;
}}

/* Row headers (Long Name / Units / ... / 1, 2, 3) */
#WorkbookTable QHeaderView::section:vertical {{
    background-color: {_SURFACE_2};
    color: {_MUTED};
    border: none;
    border-right: 1px solid {_BORDER};
    border-bottom: 1px solid {_GRID};
    padding: 2px 8px;
}}

#WorkbookTable QTableCornerButton::section {{
    background-color: {_HEADER_BG};
    border: none;
    border-right: 1px solid {_BORDER};
    border-bottom: 1px solid {_BORDER};
}}

/* Action bar above the sheet (type data -> plot, Origin-style) */
#WorkbookBar {{
    background-color: {_SURFACE_2};
    border-bottom: 1px solid {_BORDER};
}}

#WorkbookBar QLabel {{
    color: {_MUTED};
    font-size: 11px;
}}

#WorkbookBar QPushButton {{
    background: transparent;
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 3px 10px;
    min-height: 22px;
}}

#WorkbookBar QPushButton:hover {{
    background: rgba(255, 255, 255, 0.06);
    border-color: {_ACCENT};
}}

#WorkbookBar QPushButton#WorkbookPlotButton {{
    background: {_ACCENT};
    color: #ffffff;
    border-color: {_ACCENT};
    font-weight: 600;
}}

#WorkbookBar QPushButton#WorkbookPlotButton:hover {{
    background: #5fa8fb;
    border-color: #5fa8fb;
}}
"""


def column_label(index: int) -> str:
    """Spreadsheet-style letter label for a column index (0 -> A, 25 -> Z, 26 -> AA)."""
    if index < 0:
        raise ValueError("column index must be non-negative")
    letters = ""
    n = index
    while True:
        letters = chr(ord("A") + (n % 26)) + letters
        n = n // 26 - 1
        if n < 0:
            break
    return letters


def column_header_text(index: int) -> str:
    """Origin-style column header, e.g. ``A(X)`` for the first column, ``B(Y)`` after."""
    designation = "X" if index == 0 else "Y"
    return f"{column_label(index)}({designation})"


class WorkbookWidget(QWidget):
    """An OriginLab-style worksheet view backed by a :class:`QTableWidget`.

    Public API:
        - ``set_dataframe(df)``        — load a DataFrame into the grid.
        - ``dataframe()``              — read the data rows back into a DataFrame.
        - ``clear_to_empty(rows, cols)`` — reset to the empty ``Book1`` state.
        - ``set_meta(col_index, long_name=, units=, comments=)`` — set column meta.
        - ``add_data_row()`` / ``add_data_column()`` — grow the sheet.
        - ``selected_column_indexes()`` — worksheet columns touched by selection.
        - ``table``                    — the underlying QTableWidget (for tests).

    Signals (the workflow: type data → use it → plot it):
        - ``use_data_requested()``          — adopt the sheet as the active data.
        - ``plot_requested(str)``           — plot selected columns ("line"/"scatter").
    """

    use_data_requested = Signal()
    plot_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("WorkbookWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- action bar: makes the sheet self-explanatory (type -> plot) ---
        bar = QWidget(self)
        bar.setObjectName("WorkbookBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(6)

        self.btn_add_row = QPushButton("+ แถว", bar)
        self.btn_add_col = QPushButton("+ คอลัมน์", bar)
        self.btn_use_data = QPushButton("ใช้ข้อมูลนี้", bar)
        self.btn_use_data.setToolTip("นำข้อมูลในตารางไปเป็นข้อมูลหลัก (พร้อมพล็อต/วิเคราะห์)")
        self.btn_plot_line = QPushButton("พล็อตเส้น", bar)
        self.btn_plot_line.setObjectName("WorkbookPlotButton")
        self.btn_plot_line.setToolTip("พล็อตจากคอลัมน์ที่เลือก (คอลัมน์แรก = X)")
        self.btn_plot_scatter = QPushButton("พล็อตจุด", bar)
        self.btn_plot_scatter.setToolTip("พล็อต scatter จากคอลัมน์ที่เลือก (คอลัมน์แรก = X)")

        hint = QLabel("พิมพ์ข้อมูลลงตาราง → เลือกคอลัมน์ → กดพล็อต", bar)

        bar_layout.addWidget(self.btn_add_row)
        bar_layout.addWidget(self.btn_add_col)
        bar_layout.addSpacing(8)
        bar_layout.addWidget(self.btn_use_data)
        bar_layout.addWidget(self.btn_plot_line)
        bar_layout.addWidget(self.btn_plot_scatter)
        bar_layout.addStretch(1)
        bar_layout.addWidget(hint)
        layout.addWidget(bar)

        self.btn_add_row.clicked.connect(self.add_data_row)
        self.btn_add_col.clicked.connect(self.add_data_column)
        self.btn_use_data.clicked.connect(self.use_data_requested.emit)
        self.btn_plot_line.clicked.connect(lambda: self.plot_requested.emit("line"))
        self.btn_plot_scatter.clicked.connect(lambda: self.plot_requested.emit("scatter"))

        self.table = QTableWidget(self)
        self.table.setObjectName("WorkbookTable")
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(96)
        self.table.verticalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setHighlightSections(False)
        layout.addWidget(self.table)

        # Origin-style right-click: plot straight from the selection.
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        self.setStyleSheet(_WORKBOOK_QSS)

        self.clear_to_empty()

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self.table)
        menu.addAction("พล็อตเส้นจากคอลัมน์ที่เลือก").triggered.connect(
            lambda: self.plot_requested.emit("line"))
        menu.addAction("พล็อตจุดจากคอลัมน์ที่เลือก").triggered.connect(
            lambda: self.plot_requested.emit("scatter"))
        menu.addSeparator()
        menu.addAction("ใช้ข้อมูลนี้เป็นข้อมูลหลัก").triggered.connect(
            self.use_data_requested.emit)
        menu.addSeparator()
        menu.addAction("เพิ่มแถว").triggered.connect(self.add_data_row)
        menu.addAction("เพิ่มคอลัมน์").triggered.connect(self.add_data_column)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ helpers
    def _meta_brush(self) -> QBrush:
        return QBrush(QColor(_META_BG))

    def _data_brush(self) -> QBrush:
        return QBrush(QColor(_SURFACE))

    def _apply_row_headers(self, data_row_count: int) -> None:
        """Set vertical header labels: meta names then 1..N for data rows."""
        labels = list(META_ROWS) + [str(i + 1) for i in range(data_row_count)]
        self.table.setVerticalHeaderLabels(labels)

    def _apply_column_headers(self, col_count: int) -> None:
        labels = [column_header_text(i) for i in range(col_count)]
        self.table.setHorizontalHeaderLabels(labels)

    def _make_item(self, text: str, is_meta: bool) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if is_meta:
            item.setBackground(self._meta_brush())
            font = QFont()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(QBrush(QColor(_MUTED)))
        else:
            item.setBackground(self._data_brush())
        return item

    def _populate_empty_cells(self) -> None:
        """Ensure every cell holds a QTableWidgetItem so styling is consistent."""
        rows = self.table.rowCount()
        cols = self.table.columnCount()
        for r in range(rows):
            is_meta = r < META_ROW_COUNT
            for c in range(cols):
                if self.table.item(r, c) is None:
                    self.table.setItem(r, c, self._make_item("", is_meta))

    @property
    def data_row_count(self) -> int:
        return max(0, self.table.rowCount() - META_ROW_COUNT)

    # -------------------------------------------------------------------- API
    def add_data_row(self) -> None:
        """Append one empty data row (keeps meta rows and styling intact)."""
        row = self.table.rowCount()
        self.table.setRowCount(row + 1)
        for c in range(self.table.columnCount()):
            self.table.setItem(row, c, self._make_item("", False))
        self._apply_row_headers(self.data_row_count)

    def add_data_column(self) -> None:
        """Append one empty column labelled with the next spreadsheet letter."""
        col = self.table.columnCount()
        self.table.setColumnCount(col + 1)
        for r in range(self.table.rowCount()):
            self.table.setItem(r, col, self._make_item("", r < META_ROW_COUNT))
        self._apply_column_headers(col + 1)

    def selected_column_indexes(self) -> List[int]:
        """Worksheet columns touched by the current selection, in order."""
        cols = sorted({index.column() for index in self.table.selectedIndexes()})
        return cols

    def selected_column_names(self) -> List[str]:
        """Names (Long Name meta, else letter) of the selected columns."""
        names = []
        for c in self.selected_column_indexes():
            long_name = self._meta_text(0, c)
            names.append(long_name if long_name else column_label(c))
        return names

    def clear_to_empty(self, rows: int = 32, cols: int = 2) -> None:
        """Reset to an empty ``Book1``-like sheet: ``cols`` columns, ``rows`` data rows."""
        cols = max(1, int(cols))
        rows = max(0, int(rows))
        self.table.clear()
        self.table.setColumnCount(cols)
        self.table.setRowCount(META_ROW_COUNT + rows)
        self._apply_column_headers(cols)
        self._apply_row_headers(rows)
        self._populate_empty_cells()

    def set_meta(
        self,
        col_index: int,
        long_name: Optional[str] = None,
        units: Optional[str] = None,
        comments: Optional[str] = None,
    ) -> None:
        """Set the Long Name / Units / Comments meta rows for a single column."""
        if col_index < 0 or col_index >= self.table.columnCount():
            raise IndexError(f"column index {col_index} out of range")
        mapping = {0: long_name, 1: units, 2: comments}
        for meta_row, value in mapping.items():
            if value is None:
                continue
            self.table.setItem(meta_row, col_index, self._make_item(str(value), True))

    def _meta_text(self, meta_row: int, col_index: int) -> str:
        item = self.table.item(meta_row, col_index)
        return item.text().strip() if item is not None else ""

    def set_dataframe(self, df: pd.DataFrame) -> None:
        """Load a DataFrame: each column becomes a worksheet column.

        The DataFrame column name fills that column's ``Long Name`` meta row;
        the values fill the numbered data rows. The first column keeps the X
        designation, the rest Y (best-effort).
        """
        if df is None:
            self.clear_to_empty()
            return

        n_cols = max(1, int(df.shape[1]))
        n_rows = int(df.shape[0])

        self.table.clear()
        self.table.setColumnCount(n_cols)
        self.table.setRowCount(META_ROW_COUNT + n_rows)
        self._apply_column_headers(n_cols)
        self._apply_row_headers(n_rows)
        self._populate_empty_cells()

        for c, col_name in enumerate(df.columns):
            # Long Name meta row holds the source column name.
            self.set_meta(c, long_name=str(col_name))
            series = df.iloc[:, c]
            for r in range(n_rows):
                value = series.iat[r]
                text = "" if pd.isna(value) else str(value)
                self.table.setItem(
                    r + META_ROW_COUNT, c, self._make_item(text, False)
                )

    def dataframe(self) -> pd.DataFrame:
        """Read the data rows back into a DataFrame.

        Column names use each column's Long Name meta row when present, else the
        spreadsheet letter (A, B, C, ...). Numeric-looking values are coerced to
        numbers; otherwise the raw string is kept.
        """
        cols = self.table.columnCount()
        data_rows = self.data_row_count

        names: List[str] = []
        columns_data: List[list] = []
        for c in range(cols):
            long_name = self._meta_text(0, c)
            names.append(long_name if long_name else column_label(c))
            values: list = []
            for r in range(data_rows):
                item = self.table.item(r + META_ROW_COUNT, c)
                values.append(item.text() if item is not None else "")
            columns_data.append(values)

        # De-duplicate column names so the DataFrame stays well-formed.
        seen: dict = {}
        unique_names: List[str] = []
        for name in names:
            if name in seen:
                seen[name] += 1
                unique_names.append(f"{name}.{seen[name]}")
            else:
                seen[name] = 0
                unique_names.append(name)

        frame = pd.DataFrame(
            {unique_names[c]: columns_data[c] for c in range(cols)}
        )
        # Best-effort numeric coercion per column (keeps strings if it fails).
        for name in frame.columns:
            converted = pd.to_numeric(frame[name], errors="coerce")
            # Only adopt the numeric column if it doesn't introduce new NaNs
            # over genuinely-empty cells (i.e. every non-empty cell parsed).
            non_empty = frame[name].astype(str).str.strip() != ""
            if non_empty.any() and converted[non_empty].notna().all():
                frame[name] = converted
        # Drop rows that are entirely empty, so a half-filled sheet (the
        # type-your-own-data flow) comes back as just the typed rows.
        empty_mask = frame.apply(
            lambda col: col.isna() | (col.astype(str).str.strip() == ""), axis=0
        )
        frame = frame.loc[~empty_mask.all(axis=1)].reset_index(drop=True)
        return frame
