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


# Column designations (Origin's "Set As"): X / Y / ignore (Disregard).
DESIGNATIONS = ("X", "Y", "ignore")

# Column names that look like a time axis get the X designation automatically.
_TIME_LIKE_KEYS = ("time", "timestamp", "datetime", "date", "epoch", "t")


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
        - ``plot_requested(str)``           — plot selected columns into a NEW
          graph window ("line"/"scatter"/...), Origin-style.
        - ``overlay_requested(str)``        — add selected columns to the
          currently active graph instead.
    """

    use_data_requested = Signal()
    plot_requested = Signal(str)
    overlay_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("WorkbookWidget")

        # Origin multi-book model: each Book carries its own DataFrame so
        # switching Books never re-reads the (slow) QTableWidget. Kept in sync
        # by set_dataframe() and MainWindow.adopt_workbook_data().
        self.source_df: Optional[pd.DataFrame] = None
        # Registry key in MainWindow._datasets (set when the Book is created).
        self.dataset_name: str = ""
        # Dirty = user edited cells since the last set_dataframe/adopt →
        # plotting must re-read the sheet; clean books use source_df (fast).
        self._dirty = False
        self._loading = False
        # Per-column designation ("X"/"Y"/"ignore") — Origin's Set As.
        self._designations: List[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- action bar: makes the sheet self-explanatory (type -> plot) ---
        bar = QWidget(self)
        bar.setObjectName("WorkbookBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(6)

        self.btn_add_row = QPushButton("+ Row", bar)
        self.btn_add_col = QPushButton("+ Column", bar)
        self.btn_use_data = QPushButton("Use This Data", bar)
        self.btn_use_data.setToolTip("Use this sheet as the active data (ready to plot / analyze)")
        self.btn_plot_line = QPushButton("Plot Line", bar)
        self.btn_plot_line.setObjectName("WorkbookPlotButton")
        self.btn_plot_line.setToolTip("Plot the selected columns as a new graph (first selected = X)")
        self.btn_plot_scatter = QPushButton("Plot Scatter", bar)
        self.btn_plot_scatter.setToolTip("Scatter-plot the selected columns as a new graph (first selected = X)")

        hint = QLabel("Type data → select columns → plot", bar)

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

        # Origin's "Set As X/Y" on the column header.
        header = self.table.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_menu)

        self.table.itemChanged.connect(self._on_item_changed)

        self.setStyleSheet(_WORKBOOK_QSS)

        self.clear_to_empty()

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self.table)
        menu.addAction("Line → new graph").triggered.connect(
            lambda: self.plot_requested.emit("line"))
        menu.addAction("Scatter → new graph").triggered.connect(
            lambda: self.plot_requested.emit("scatter"))
        menu.addAction("Line + Symbol → new graph").triggered.connect(
            lambda: self.plot_requested.emit("linesymbol"))
        menu.addAction("Column / Bar → new graph").triggered.connect(
            lambda: self.plot_requested.emit("bar"))
        menu.addAction("Histogram → new graph").triggered.connect(
            lambda: self.plot_requested.emit("histogram"))
        menu.addSeparator()
        menu.addAction("Add line to current graph").triggered.connect(
            lambda: self.overlay_requested.emit("line"))
        menu.addAction("Add scatter to current graph").triggered.connect(
            lambda: self.overlay_requested.emit("scatter"))
        menu.addSeparator()
        menu.addAction("Use this data").triggered.connect(
            self.use_data_requested.emit)
        menu.addSeparator()
        menu.addAction("Add Row").triggered.connect(self.add_data_row)
        menu.addAction("Add Column").triggered.connect(self.add_data_column)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ helpers
    def _on_item_changed(self, _item) -> None:
        if not self._loading:
            self._dirty = True

    def _loading_guard(self):
        """Context manager: suppress dirty-marking during programmatic fills."""
        from contextlib import contextmanager

        @contextmanager
        def _guard():
            prev = self._loading
            self._loading = True
            try:
                yield
            finally:
                self._loading = prev

        return _guard()

    @property
    def is_dirty(self) -> bool:
        """True เมื่อผู้ใช้แก้เซลล์หลังโหลดข้อมูลครั้งล่าสุด (ชีตใหม่กว่า source_df)"""
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False

    def _meta_brush(self) -> QBrush:
        return QBrush(QColor(_META_BG))

    def _data_brush(self) -> QBrush:
        return QBrush(QColor(_SURFACE))

    def _apply_row_headers(self, data_row_count: int) -> None:
        """Set vertical header labels: meta names then 1..N for data rows."""
        labels = list(META_ROWS) + [str(i + 1) for i in range(data_row_count)]
        self.table.setVerticalHeaderLabels(labels)

    def _ensure_designations(self, col_count: int) -> None:
        """Resize the designation list: first column X, new columns Y."""
        if len(self._designations) > col_count:
            self._designations = self._designations[:col_count]
        while len(self._designations) < col_count:
            self._designations.append("X" if not self._designations else "Y")

    def _apply_column_headers(self, col_count: int) -> None:
        self._ensure_designations(col_count)
        labels = []
        for i in range(col_count):
            designation = self._designations[i]
            if designation == "ignore":
                labels.append(column_label(i))
            else:
                labels.append(f"{column_label(i)}({designation})")
        self.table.setHorizontalHeaderLabels(labels)

    # ---------------------------------------------- designations (Set As X/Y)
    def column_designation(self, col_index: int) -> str:
        self._ensure_designations(self.table.columnCount())
        if 0 <= col_index < len(self._designations):
            return self._designations[col_index]
        return "Y"

    def set_designation(self, col_index: int, kind: str) -> None:
        """Origin's Set As: mark a column X / Y / ignore (single-X model —
        promoting a column to X demotes the previous X to Y)."""
        if kind not in DESIGNATIONS:
            raise ValueError(f"unknown designation: {kind!r} (use one of {DESIGNATIONS})")
        self._ensure_designations(self.table.columnCount())
        if not (0 <= col_index < len(self._designations)):
            raise IndexError(f"column index {col_index} out of range")
        if kind == "X":
            for i, d in enumerate(self._designations):
                if d == "X":
                    self._designations[i] = "Y"
        self._designations[col_index] = kind
        self._apply_column_headers(self.table.columnCount())

    def x_column_index(self):
        """Index of the designated X column, or None."""
        self._ensure_designations(self.table.columnCount())
        for i, d in enumerate(self._designations):
            if d == "X":
                return i
        return None

    def y_column_indexes(self) -> List[int]:
        """Indexes of all designated Y columns (order preserved)."""
        self._ensure_designations(self.table.columnCount())
        return [i for i, d in enumerate(self._designations) if d == "Y"]

    def _auto_designations(self, df: pd.DataFrame) -> None:
        """Default X = first time-like column (else column 0), rest Y."""
        n = max(1, int(df.shape[1]))
        self._designations = ["Y"] * n
        x_idx = 0
        for i, name in enumerate(df.columns):
            low = str(name).strip().lower()
            if any(key == low or key in low for key in _TIME_LIKE_KEYS if len(key) > 1) or low == "t":
                x_idx = i
                break
        self._designations[x_idx] = "X"

    def _show_header_menu(self, pos) -> None:
        header = self.table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col < 0:
            return
        menu = QMenu(header)
        menu.addAction(f"Set As X — column {column_label(col)}").triggered.connect(
            lambda: self.set_designation(col, "X"))
        menu.addAction(f"Set As Y — column {column_label(col)}").triggered.connect(
            lambda: self.set_designation(col, "Y"))
        menu.addAction("Disregard this column").triggered.connect(
            lambda: self.set_designation(col, "ignore"))
        menu.exec(header.mapToGlobal(pos))

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
        with self._loading_guard():
            row = self.table.rowCount()
            self.table.setRowCount(row + 1)
            for c in range(self.table.columnCount()):
                self.table.setItem(row, c, self._make_item("", False))
            self._apply_row_headers(self.data_row_count)

    def add_data_column(self) -> None:
        """Append one empty column labelled with the next spreadsheet letter."""
        with self._loading_guard():
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
        with self._loading_guard():
            cols = max(1, int(cols))
            rows = max(0, int(rows))
            self._designations = []  # reset to default: A(X), B(Y), ...
            self.table.clear()
            self.table.setColumnCount(cols)
            self.table.setRowCount(META_ROW_COUNT + rows)
            self._apply_column_headers(cols)
            self._apply_row_headers(rows)
            self._populate_empty_cells()
        self._dirty = False

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
        with self._loading_guard():
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
            self.source_df = None
            self.clear_to_empty()
            return

        self.source_df = df
        self._auto_designations(df)  # X = คอลัมน์เวลา (ถ้ามี) ไม่งั้นคอลัมน์แรก
        with self._loading_guard():
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
        self._dirty = False

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
