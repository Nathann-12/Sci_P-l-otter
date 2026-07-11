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
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QMenu,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
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

/* Bottom icon strip, following Origin's worksheet flow: edit data in the grid,
   then use/plot/structure from a dense tool row below it. */
QToolBar#WorkbookBottomBar {{
    background-color: #17191c;
    border: none;
    border-top: 1px solid {_BORDER};
    padding: 1px 4px;
    spacing: 1px;
}}

QToolBar#WorkbookBottomBar::separator {{
    background-color: #3c424a;
    width: 1px;
    margin: 3px 4px;
}}

QToolBar#WorkbookBottomBar QToolButton {{
    background: transparent;
    color: {_TEXT};
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px;
    margin: 0px;
    min-width: 20px;
    min-height: 20px;
    max-width: 24px;
    max-height: 24px;
}}

QToolBar#WorkbookBottomBar QToolButton:hover {{
    background: rgba(79, 156, 249, 0.14);
    border-color: rgba(79, 156, 249, 0.35);
}}

QToolBar#WorkbookBottomBar QToolButton:pressed {{
    background: rgba(79, 156, 249, 0.22);
}}

QToolBar#WorkbookBottomBar QToolButton:disabled {{
    color: #666666;
    background: transparent;
}}
"""


# Column designations (Origin's "Set As"): X / Y / ignore (Disregard).
DESIGNATIONS = ("X", "Y", "ignore")

# Column names that look like a time axis get the X designation automatically.
_TIME_LIKE_KEYS = ("time", "timestamp", "datetime", "date", "epoch", "t")


def _format_column(series) -> List[str]:
    """Column values → list of display strings ('' for NaN), fast single pass."""
    try:
        is_na = pd.isna(series).to_numpy()
        values = series.to_numpy()
        return ["" if is_na[i] else str(values[i]) for i in range(len(values))]
    except Exception:
        return ["" if pd.isna(v) else str(v) for v in series.tolist()]


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

        # Shared brushes/fonts — reused for every cell so filling a big sheet
        # doesn't allocate thousands of QBrush/QColor/QFont objects.
        self._brush_meta = QBrush(QColor(_META_BG))
        self._brush_data = QBrush(QColor(_SURFACE))
        self._brush_muted = QBrush(QColor(_MUTED))
        self._font_meta = QFont()
        self._font_meta.setItalic(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Hidden compatibility buttons: older tests/callers can still trigger
        # the same signals, while the visible UI is the Origin-like toolbar.
        self.btn_add_row = QPushButton("+R", self)
        self.btn_add_row.setToolTip("Append one data row")
        self.btn_add_col = QPushButton("+C", self)
        self.btn_add_col.setToolTip("Append one worksheet column")
        self.btn_use_data = QPushButton("Use", self)
        self.btn_use_data.setToolTip("Use this sheet as the active data (ready to plot / analyze)")
        self.btn_plot_line = QPushButton("Plot Line", self)
        self.btn_plot_line.setObjectName("WorkbookPlotButton")
        self.btn_plot_line.setToolTip(
            "Plot selected columns as a new graph. One selected column plots against row number."
        )
        self.btn_plot_scatter = QPushButton("Plot Scatter", self)
        self.btn_plot_scatter.setToolTip(
            "Scatter-plot selected columns as a new graph. One selected column plots against row number."
        )
        self.btn_add_row.hide()
        self.btn_add_col.hide()
        self.btn_use_data.hide()
        self.btn_plot_line.hide()
        self.btn_plot_scatter.hide()

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

        self.workbook_toolbar = self._create_workbook_toolbar()
        layout.addWidget(self.workbook_toolbar)

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

    def _toolbar_icon(self, fallback_sp) -> object:
        try:
            return self.style().standardIcon(fallback_sp)
        except Exception:
            from PySide6.QtGui import QIcon

            return QIcon()

    def _add_workbook_action(
        self,
        toolbar: QToolBar,
        key: str,
        text: str,
        slot,
        fallback_sp,
        *,
        tooltip: str | None = None,
    ) -> QAction:
        action = QAction(self._toolbar_icon(fallback_sp), text, self)
        action.setProperty("toolbarIconKey", f"workbook_{key}")
        action.setToolTip(tooltip or text)
        action.setStatusTip(tooltip or text)
        action.triggered.connect(slot)
        toolbar.addAction(action)
        self.workbook_actions[key] = action
        return action

    def _create_workbook_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Workbook Flow", self)
        toolbar.setObjectName("WorkbookBottomBar")
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setAllowedAreas(Qt.NoToolBarArea)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        toolbar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.workbook_actions = {}

        self._add_workbook_action(
            toolbar,
            "use_data",
            "Use Data",
            self.use_data_requested.emit,
            QStyle.StandardPixmap.SP_DialogApplyButton,
            tooltip="Use this worksheet as active data",
        )
        toolbar.addSeparator()
        for key, text, style, fallback in (
            ("plot_line", "Line", "line", QStyle.StandardPixmap.SP_ArrowRight),
            ("plot_scatter", "Scatter", "scatter", QStyle.StandardPixmap.SP_FileDialogContentsView),
            ("plot_linesymbol", "Line + Symbol", "linesymbol", QStyle.StandardPixmap.SP_FileDialogDetailedView),
            ("plot_bar", "Column / Bar", "bar", QStyle.StandardPixmap.SP_TitleBarShadeButton),
            ("plot_histogram", "Histogram", "histogram", QStyle.StandardPixmap.SP_FileDialogListView),
        ):
            self._add_workbook_action(
                toolbar,
                key,
                text,
                lambda _checked=False, s=style: self.plot_requested.emit(s),
                fallback,
                tooltip=f"Plot selected columns as {text}",
            )
        toolbar.addSeparator()
        for key, text, style, fallback in (
            ("overlay_line", "Add Line", "line", QStyle.StandardPixmap.SP_ArrowUp),
            ("overlay_scatter", "Add Scatter", "scatter", QStyle.StandardPixmap.SP_ArrowForward),
            ("overlay_bar", "Add Column / Bar", "bar", QStyle.StandardPixmap.SP_ArrowRight),
        ):
            self._add_workbook_action(
                toolbar,
                key,
                text,
                lambda _checked=False, s=style: self.overlay_requested.emit(s),
                fallback,
                tooltip=f"Add {text.replace('Add ', '').lower()} to current graph",
            )
        toolbar.addSeparator()
        self._add_workbook_action(
            toolbar,
            "set_x",
            "Set X",
            lambda _checked=False: self.set_selected_columns_designation("X"),
            QStyle.StandardPixmap.SP_ArrowLeft,
            tooltip="Set selected/current column as X",
        )
        self._add_workbook_action(
            toolbar,
            "set_y",
            "Set Y",
            lambda _checked=False: self.set_selected_columns_designation("Y"),
            QStyle.StandardPixmap.SP_ArrowRight,
            tooltip="Set selected/current columns as Y",
        )
        self._add_workbook_action(
            toolbar,
            "set_ignore",
            "Ignore",
            lambda _checked=False: self.set_selected_columns_designation("ignore"),
            QStyle.StandardPixmap.SP_DialogCancelButton,
            tooltip="Ignore selected/current columns",
        )
        toolbar.addSeparator()
        for key, text, slot, fallback in (
            ("copy", "Copy", self.copy_selection_to_clipboard, QStyle.StandardPixmap.SP_FileIcon),
            ("paste", "Paste", self.paste_from_clipboard, QStyle.StandardPixmap.SP_DialogOpenButton),
            ("clear", "Clear", self.clear_selected_cells, QStyle.StandardPixmap.SP_DialogResetButton),
            ("add_row", "Append Row", self.add_data_row, QStyle.StandardPixmap.SP_ArrowDown),
            ("add_column", "Append Column", self.add_data_column, QStyle.StandardPixmap.SP_ArrowRight),
            ("insert_row", "Insert Row Below", self.insert_data_row_after_selection, QStyle.StandardPixmap.SP_ArrowDown),
            ("insert_column", "Insert Column Right", self.insert_data_column_after_selection, QStyle.StandardPixmap.SP_ArrowRight),
            ("delete_rows", "Delete Rows", self.delete_selected_data_rows, QStyle.StandardPixmap.SP_TrashIcon),
            ("delete_columns", "Delete Columns", self.delete_selected_columns, QStyle.StandardPixmap.SP_TrashIcon),
        ):
            self._add_workbook_action(toolbar, key, text, slot, fallback)
        return toolbar

    def _show_context_menu(self, pos) -> None:
        menu = self._build_cell_context_menu()
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _build_cell_context_menu(self) -> QMenu:
        """Create the production worksheet menu without opening a popup."""
        menu = QMenu(self.table)
        plot_menu = QMenu("Plot New Graph", menu)
        menu.addMenu(plot_menu)
        self._add_plot_actions(plot_menu, self.plot_requested)

        overlay_menu = QMenu("Add To Current Graph", menu)
        menu.addMenu(overlay_menu)
        self._add_plot_actions(overlay_menu, self.overlay_requested, include_histogram=False)

        set_as_menu = QMenu("Set Selected Columns As", menu)
        menu.addMenu(set_as_menu)
        set_as_menu.addAction("X").triggered.connect(
            lambda: self.set_selected_columns_designation("X"))
        set_as_menu.addAction("Y").triggered.connect(
            lambda: self.set_selected_columns_designation("Y"))
        set_as_menu.addAction("Ignore").triggered.connect(
            lambda: self.set_selected_columns_designation("ignore"))

        menu.addSeparator()
        menu.addAction("Use This Data").triggered.connect(self.use_data_requested.emit)

        edit_menu = QMenu("Edit", menu)
        menu.addMenu(edit_menu)
        edit_menu.addAction("Copy Selection").triggered.connect(self.copy_selection_to_clipboard)
        edit_menu.addAction("Paste").triggered.connect(self.paste_from_clipboard)
        edit_menu.addAction("Clear Selection").triggered.connect(self.clear_selected_cells)

        structure_menu = QMenu("Structure", menu)
        menu.addMenu(structure_menu)
        structure_menu.addAction("Insert Row Below").triggered.connect(
            self.insert_data_row_after_selection)
        structure_menu.addAction("Delete Selected Rows").triggered.connect(
            self.delete_selected_data_rows)
        structure_menu.addAction("Insert Column Right").triggered.connect(
            self.insert_data_column_after_selection)
        structure_menu.addAction("Delete Selected Columns").triggered.connect(
            self.delete_selected_columns)
        structure_menu.addSeparator()
        structure_menu.addAction("Append Row").triggered.connect(self.add_data_row)
        structure_menu.addAction("Append Column").triggered.connect(self.add_data_column)
        menu._owned_submenus = [plot_menu, overlay_menu, set_as_menu, edit_menu, structure_menu]
        return menu

    def _add_plot_actions(self, menu: QMenu, signal: Signal, include_histogram: bool = True) -> None:
        actions = [
            ("Line", "line"),
            ("Scatter", "scatter"),
            ("Line + Symbol", "linesymbol"),
            ("Column / Bar", "bar"),
        ]
        if include_histogram:
            actions.append(("Histogram", "histogram"))
        for label, style in actions:
            menu.addAction(label).triggered.connect(
                lambda _checked=False, s=style: signal.emit(s))

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

    def apply_application_theme(self) -> None:
        """Refresh item-level brushes/fonts that cannot be changed by QSS."""
        app = QApplication.instance()
        if app is None or not hasattr(self, "table"):
            return
        palette = app.palette()
        self._brush_meta = QBrush(palette.color(QPalette.AlternateBase))
        self._brush_data = QBrush(palette.color(QPalette.Base))
        self._brush_muted = QBrush(palette.color(QPalette.PlaceholderText))
        self._font_meta = QFont(app.font())
        self._font_meta.setItalic(True)

        with self._loading_guard():
            for row in range(min(META_ROW_COUNT, self.table.rowCount())):
                for column in range(self.table.columnCount()):
                    item = self.table.item(row, column)
                    if item is None:
                        continue
                    item.setBackground(self._brush_meta)
                    item.setForeground(self._brush_muted)
                    item.setFont(self._font_meta)

    def _meta_brush(self) -> QBrush:
        return self._brush_meta

    def _data_brush(self) -> QBrush:
        return self._brush_data

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
        menu = self._build_header_context_menu(col)
        menu.exec(header.mapToGlobal(pos))

    def _build_header_context_menu(self, col: int) -> QMenu:
        header = self.table.horizontalHeader()
        menu = QMenu(header)
        label = column_label(col)

        set_as_menu = QMenu(f"Set Column {label} As", menu)
        menu.addMenu(set_as_menu)
        set_as_menu.addAction("X").triggered.connect(lambda: self.set_designation(col, "X"))
        set_as_menu.addAction("Y").triggered.connect(lambda: self.set_designation(col, "Y"))
        set_as_menu.addAction("Ignore").triggered.connect(
            lambda: self.set_designation(col, "ignore"))

        plot_menu = QMenu("Plot Column", menu)
        menu.addMenu(plot_menu)
        self._add_plot_actions(plot_menu, self.plot_requested)

        overlay_menu = QMenu("Add Column To Current Graph", menu)
        menu.addMenu(overlay_menu)
        self._add_plot_actions(overlay_menu, self.overlay_requested, include_histogram=False)

        menu.addSeparator()
        menu.addAction("Use This Data").triggered.connect(self.use_data_requested.emit)
        menu.addAction("Insert Column Right").triggered.connect(
            lambda: self._insert_column_after_index(col))
        menu.addAction("Delete Column").triggered.connect(
            lambda: self._delete_column_by_index(col))
        menu._owned_submenus = [set_as_menu, plot_menu, overlay_menu]
        return menu

    def _make_item(self, text: str, is_meta: bool) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if is_meta:
            item.setBackground(self._brush_meta)
            item.setFont(self._font_meta)
            item.setForeground(self._brush_muted)
        # data cells: no per-cell brush — the #WorkbookTable stylesheet already
        # paints the surface colour, so skipping it saves work on big sheets
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

    def _selected_or_current_column_indexes(self) -> List[int]:
        cols = self.selected_column_indexes()
        if cols:
            return cols
        current_col = self.table.currentColumn()
        if current_col >= 0:
            return [current_col]
        return []

    def _selected_or_current_data_rows(self) -> List[int]:
        rows = sorted({
            index.row()
            for index in self.table.selectedIndexes()
            if index.row() >= META_ROW_COUNT
        })
        if rows:
            return rows
        current_row = self.table.currentRow()
        if current_row >= META_ROW_COUNT:
            return [current_row]
        return []

    def set_selected_columns_designation(self, kind: str) -> None:
        """Apply an Origin-style X/Y/ignore designation to selected columns."""
        cols = self._selected_or_current_column_indexes()
        if not cols:
            return
        if kind == "X":
            self.set_designation(cols[0], "X")
            return
        for col in cols:
            self.set_designation(col, kind)

    def insert_data_row_after_selection(self) -> None:
        rows = self._selected_or_current_data_rows()
        if rows:
            insert_at = max(rows) + 1
        elif self.table.currentRow() >= META_ROW_COUNT:
            insert_at = self.table.currentRow() + 1
        else:
            insert_at = META_ROW_COUNT
        insert_at = max(META_ROW_COUNT, min(insert_at, self.table.rowCount()))
        with self._loading_guard():
            self.table.insertRow(insert_at)
            for col in range(self.table.columnCount()):
                self.table.setItem(insert_at, col, self._make_item("", False))
            self._apply_row_headers(self.data_row_count)
        self._dirty = True

    def insert_data_column_after_selection(self) -> None:
        cols = self._selected_or_current_column_indexes()
        insert_at = (max(cols) + 1) if cols else self.table.columnCount()
        self._insert_column_at(insert_at)

    def _insert_column_after_index(self, col: int) -> None:
        self._insert_column_at(col + 1)

    def _insert_column_at(self, insert_at: int) -> None:
        insert_at = max(0, min(insert_at, self.table.columnCount()))
        with self._loading_guard():
            self.table.insertColumn(insert_at)
            self._designations.insert(insert_at, "Y")
            for row in range(self.table.rowCount()):
                self.table.setItem(row, insert_at, self._make_item("", row < META_ROW_COUNT))
            self._apply_column_headers(self.table.columnCount())
        self._dirty = True

    def _delete_column_by_index(self, col: int) -> None:
        if not (0 <= col < self.table.columnCount()):
            return
        self._delete_columns({col})

    def delete_selected_data_rows(self) -> None:
        rows = self._selected_or_current_data_rows()
        if not rows:
            return
        with self._loading_guard():
            for row in sorted(rows, reverse=True):
                if META_ROW_COUNT <= row < self.table.rowCount():
                    self.table.removeRow(row)
            self._apply_row_headers(self.data_row_count)
        self._dirty = True

    def delete_selected_columns(self) -> None:
        cols = self._selected_or_current_column_indexes()
        if not cols:
            return
        self._delete_columns(set(cols))

    def _delete_columns(self, selected: set[int]) -> None:
        col_count = self.table.columnCount()
        remaining = [col for col in range(col_count) if col not in selected]
        if not remaining:
            selected.discard(min(selected))
        if not selected:
            return

        with self._loading_guard():
            self._ensure_designations(col_count)
            for col in sorted(selected, reverse=True):
                if 0 <= col < self.table.columnCount():
                    self.table.removeColumn(col)
                    if col < len(self._designations):
                        self._designations.pop(col)
            if self._designations and "X" not in self._designations:
                self._designations[0] = "X"
            self._apply_column_headers(self.table.columnCount())
        self._dirty = True

    def clear_selected_cells(self) -> None:
        indexes = self.table.selectedIndexes()
        if not indexes and self.table.currentRow() >= 0 and self.table.currentColumn() >= 0:
            indexes = [self.table.currentIndex()]
        if not indexes:
            return
        with self._loading_guard():
            for index in indexes:
                row, col = index.row(), index.column()
                item = self.table.item(row, col)
                if item is None:
                    item = self._make_item("", row < META_ROW_COUNT)
                    self.table.setItem(row, col, item)
                item.setText("")
        self._dirty = True

    def copy_selection_to_clipboard(self) -> None:
        indexes = self.table.selectedIndexes()
        if not indexes and self.table.currentRow() >= 0 and self.table.currentColumn() >= 0:
            indexes = [self.table.currentIndex()]
        if not indexes:
            return
        rows = [index.row() for index in indexes]
        cols = [index.column() for index in indexes]
        min_row, max_row = min(rows), max(rows)
        min_col, max_col = min(cols), max(cols)
        lines = []
        for row in range(min_row, max_row + 1):
            values = []
            for col in range(min_col, max_col + 1):
                item = self.table.item(row, col)
                values.append(item.text() if item is not None else "")
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))

    def paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            return
        start_row = self.table.currentRow()
        start_col = self.table.currentColumn()
        if start_row < 0:
            start_row = META_ROW_COUNT
        if start_col < 0:
            start_col = 0
        rows = [line.split("\t") for line in text.splitlines()]
        if not rows:
            return
        needed_rows = start_row + len(rows)
        needed_cols = start_col + max(len(row) for row in rows)

        with self._loading_guard():
            if needed_cols > self.table.columnCount():
                old_cols = self.table.columnCount()
                self.table.setColumnCount(needed_cols)
                for col in range(old_cols, needed_cols):
                    for row in range(self.table.rowCount()):
                        self.table.setItem(row, col, self._make_item("", row < META_ROW_COUNT))
                self._apply_column_headers(needed_cols)
            if needed_rows > self.table.rowCount():
                old_rows = self.table.rowCount()
                self.table.setRowCount(needed_rows)
                for row in range(old_rows, needed_rows):
                    for col in range(self.table.columnCount()):
                        self.table.setItem(row, col, self._make_item("", row < META_ROW_COUNT))
                self._apply_row_headers(self.data_row_count)
            for r_offset, values in enumerate(rows):
                row = start_row + r_offset
                for c_offset, value in enumerate(values):
                    col = start_col + c_offset
                    item = self.table.item(row, col)
                    if item is None:
                        item = self._make_item("", row < META_ROW_COUNT)
                        self.table.setItem(row, col, item)
                    item.setText(value)
        self._dirty = True

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
        n_cols = max(1, int(df.shape[1]))
        n_rows = int(df.shape[0])

        # Bulk fill: block per-cell signals + repaints and reuse shared brushes.
        # Each data cell is set exactly once (no populate-then-overwrite), and
        # column values are pre-formatted to strings in one pass.
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        prev_loading = self._loading
        self._loading = True
        try:
            self.table.clear()
            self.table.setColumnCount(n_cols)
            self.table.setRowCount(META_ROW_COUNT + n_rows)
            self._apply_column_headers(n_cols)
            self._apply_row_headers(n_rows)

            make = self._make_item
            set_item = self.table.setItem
            for c, col_name in enumerate(df.columns):
                # meta rows: Long Name holds the source column name, the rest blank
                set_item(0, c, make(str(col_name), True))
                for mr in range(1, META_ROW_COUNT):
                    set_item(mr, c, make("", True))
                # data rows: format the whole column once, then place cells
                texts = _format_column(df.iloc[:, c])
                for r in range(n_rows):
                    set_item(r + META_ROW_COUNT, c, make(texts[r], False))
        finally:
            self._loading = prev_loading
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)
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
