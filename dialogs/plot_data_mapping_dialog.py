# dialogs/plot_data_mapping_dialog.py
"""Column-mapping dialog used before gallery plots.

Most registry plots intentionally work from "first numeric column(s)" so they
remain pure and reusable. This dialog gives the user an Origin/Excel-like
chance to reorder or insert data columns before that pure plotting code runs.
"""
from __future__ import annotations

from typing import Iterable, List

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


ROW_INDEX = "Row index (1..N)"
NONE_VALUE = "(None)"


class PlotDataMappingDialog(QDialog):
    """Select and reorder worksheet columns for a gallery plot."""

    def __init__(self, dataframe: pd.DataFrame, plot_title: str = "Plot", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Select Plot Data - {plot_title}")
        self.setModal(True)
        self.resize(540, 560)

        self._df = dataframe if isinstance(dataframe, pd.DataFrame) else pd.DataFrame()
        self._columns = list(self._df.columns)
        self._labels = {str(column): column for column in self._columns}
        self._numeric_labels = [
            str(column)
            for column in self._columns
            if pd.api.types.is_numeric_dtype(self._df[column])
        ]
        self._explicit_y_order: List[str] = []

        outer = QVBoxLayout(self)
        title = QLabel(
            "Choose which worksheet columns this chart should use. "
            "SciPlotter will reorder a temporary copy of the active Book, "
            "then plot into a new Graph."
        )
        title.setWordWrap(True)
        outer.addWidget(title)

        outer.addWidget(self._build_mapping_group())
        outer.addWidget(self._build_series_group(), 1)
        outer.addWidget(self._build_options_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _build_mapping_group(self) -> QWidget:
        group = QGroupBox("Primary / Axes")
        form = QFormLayout(group)

        self.cb_primary = QComboBox()
        self.cb_primary.addItem(ROW_INDEX)
        self.cb_primary.addItem(NONE_VALUE)
        self.cb_primary.addItems([str(column) for column in self._columns])
        default_primary = self._numeric_labels[0] if self._numeric_labels else ROW_INDEX
        _set_combo(self.cb_primary, default_primary)

        self.cb_z = QComboBox()
        self.cb_z.addItem(NONE_VALUE)
        self.cb_z.addItems(self._numeric_labels)
        if len(self._numeric_labels) >= 3:
            _set_combo(self.cb_z, self._numeric_labels[2])

        self.cb_group = QComboBox()
        self.cb_group.addItem(NONE_VALUE)
        self.cb_group.addItems([str(column) for column in self._columns])

        form.addRow("Primary / X column", self.cb_primary)
        form.addRow("Z column (3D/Contour)", self.cb_z)
        form.addRow("Group / category", self.cb_group)
        return group

    def _build_series_group(self) -> QWidget:
        group = QGroupBox("Y Series / Value Columns")
        layout = QVBoxLayout(group)
        hint = QLabel("Checked columns are placed after Primary/X, in this order.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_y = QListWidget()
        for label in self._numeric_labels:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_y.addItem(item)
        self._set_default_y_selection()
        layout.addWidget(self.list_y, 1)

        row = QHBoxLayout()
        btn_all = QLabel("<a href='all'>Select all numeric</a>")
        btn_none = QLabel("<a href='none'>Clear</a>")
        btn_all.linkActivated.connect(lambda _link: self.set_y_columns(self._numeric_labels))
        btn_none.linkActivated.connect(lambda _link: self.set_y_columns([]))
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _build_options_group(self) -> QWidget:
        group = QGroupBox("Options")
        form = QFormLayout(group)
        self.chk_keep_unused = QCheckBox("Append unused columns after mapped data")
        self.chk_keep_unused.setChecked(False)
        form.addRow("", self.chk_keep_unused)
        return group

    def _set_default_y_selection(self) -> None:
        primary = self.cb_primary.currentText() if hasattr(self, "cb_primary") else None
        selected = [label for label in self._numeric_labels if label != primary]
        self.set_y_columns(selected)

    def selected_y_columns(self) -> List[str]:
        checked: List[str] = []
        for row in range(self.list_y.count()):
            item = self.list_y.item(row)
            if item.checkState() == Qt.Checked:
                checked.append(item.text())
        ordered = [label for label in self._explicit_y_order if label in checked]
        ordered.extend(label for label in checked if label not in ordered)
        return ordered

    def set_y_columns(self, labels: Iterable[str]) -> None:
        self._explicit_y_order = [str(label) for label in labels]
        wanted = set(self._explicit_y_order)
        for row in range(self.list_y.count()):
            item = self.list_y.item(row)
            item.setCheckState(Qt.Checked if item.text() in wanted else Qt.Unchecked)

    def set_mapping(
        self,
        *,
        primary: str | None = None,
        y_columns: Iterable[str] | None = None,
        z_column: str | None = None,
        group_column: str | None = None,
        keep_unused: bool | None = None,
    ) -> None:
        """Convenience hook for tests and future scripted workflows."""
        if primary is not None:
            _set_combo(self.cb_primary, primary)
        if y_columns is not None:
            self.set_y_columns(y_columns)
        if z_column is not None:
            _set_combo(self.cb_z, z_column)
        if group_column is not None:
            _set_combo(self.cb_group, group_column)
        if keep_unused is not None:
            self.chk_keep_unused.setChecked(bool(keep_unused))

    def mapped_dataframe(self) -> pd.DataFrame:
        """Return a temporary DataFrame ordered according to the dialog."""
        if self._df is None or getattr(self._df, "empty", True):
            return pd.DataFrame()

        result = pd.DataFrame(index=self._df.index)
        used: set[str] = set()

        primary = self.cb_primary.currentText()
        if primary == ROW_INDEX:
            result["Row"] = np.arange(1, len(self._df) + 1, dtype=float)
        elif primary not in ("", NONE_VALUE):
            self._append_column(result, primary, used)

        for label in self.selected_y_columns():
            self._append_column(result, label, used)

        z_label = self.cb_z.currentText()
        if z_label not in ("", NONE_VALUE):
            self._append_column(result, z_label, used)

        group_label = self.cb_group.currentText()
        if group_label not in ("", NONE_VALUE):
            self._append_column(result, group_label, used)

        if self.chk_keep_unused.isChecked():
            for label in map(str, self._columns):
                self._append_column(result, label, used)

        return result.reset_index(drop=True)

    def _append_column(self, out: pd.DataFrame, label: str, used: set[str]) -> None:
        if label in used:
            return
        column = self._labels.get(label)
        if column is None or column not in self._df.columns:
            return
        out[label] = self._df[column].to_numpy()
        used.add(label)


def _set_combo(combo: QComboBox, value) -> None:
    idx = combo.findText(str(value))
    if idx >= 0:
        combo.setCurrentIndex(idx)
