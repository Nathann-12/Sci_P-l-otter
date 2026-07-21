"""Compact, selection-aware formatting controls for the Plot Inspector."""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.plot_style import list_palettes


class QuickFormatWidget(QGroupBox):
    """Apply a small set of common properties to selected logical layers."""

    applyRequested = Signal(dict)
    formatGraphRequested = Signal()
    copyFormatRequested = Signal()
    pasteFormatRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Appearance", parent)
        self._color: str | None = None
        self._marker_dirty = False
        self._palette_dirty = False
        self._selection_count = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 14, 8, 8)
        root.setSpacing(6)

        self.selectionLabel = QLabel("Select one or more layers above", self)
        self.selectionLabel.setWordWrap(True)
        root.addWidget(self.selectionLabel)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(5)

        self.chkColor = QCheckBox("Color", self)
        self.btnColor = QPushButton("Choose…", self)
        self.btnColor.clicked.connect(self._choose_color)
        grid.addWidget(self.chkColor, 0, 0)
        grid.addWidget(self.btnColor, 0, 1)

        grid.addWidget(QLabel("Palette", self), 1, 0)
        self.cboPalette = QComboBox(self)
        self.cboPalette.addItem("Keep palette", None)
        for palette_name in list_palettes():
            self.cboPalette.addItem(palette_name, palette_name)
        self.cboPalette.activated.connect(self._mark_palette_dirty)
        grid.addWidget(self.cboPalette, 1, 1)

        self.chkAlpha = QCheckBox("Opacity", self)
        self.spAlpha = QDoubleSpinBox(self)
        self.spAlpha.setRange(0.0, 1.0)
        self.spAlpha.setDecimals(2)
        self.spAlpha.setSingleStep(0.05)
        self.spAlpha.setValue(1.0)
        self.spAlpha.valueChanged.connect(lambda _value: self.chkAlpha.setChecked(True))
        grid.addWidget(self.chkAlpha, 2, 0)
        grid.addWidget(self.spAlpha, 2, 1)

        self.chkWidth = QCheckBox("Line / edge", self)
        self.spWidth = QDoubleSpinBox(self)
        self.spWidth.setRange(0.0, 50.0)
        self.spWidth.setDecimals(2)
        self.spWidth.setSingleStep(0.25)
        self.spWidth.setValue(1.5)
        self.spWidth.valueChanged.connect(lambda _value: self.chkWidth.setChecked(True))
        grid.addWidget(self.chkWidth, 3, 0)
        grid.addWidget(self.spWidth, 3, 1)

        grid.addWidget(QLabel("Marker", self), 4, 0)
        self.cboMarker = QComboBox(self)
        self.cboMarker.addItem("Keep marker", None)
        for label, value in (
            ("None", "None"), ("Circle", "o"), ("Square", "s"),
            ("Triangle up", "^"), ("Triangle down", "v"),
            ("Diamond", "D"), ("Cross", "x"), ("Plus", "+"),
            ("Star", "*"),
        ):
            self.cboMarker.addItem(label, value)
        self.cboMarker.activated.connect(self._mark_marker_dirty)
        grid.addWidget(self.cboMarker, 4, 1)
        root.addLayout(grid)

        self.btnApply = QPushButton("Apply to Selected Layers", self)
        self.btnApply.setEnabled(False)
        self.btnApply.clicked.connect(self._emit_apply)
        root.addWidget(self.btnApply)

        graph_row = QHBoxLayout()
        self.btnMore = QPushButton("More…", self)
        self.btnCopy = QPushButton("Copy", self)
        self.btnPaste = QPushButton("Paste", self)
        self.btnMore.setToolTip("Open all Plot Details controls")
        self.btnCopy.setToolTip("Copy this graph's appearance without its data or names")
        self.btnPaste.setToolTip("Paste the copied appearance onto this graph")
        self.btnMore.clicked.connect(self.formatGraphRequested)
        self.btnCopy.clicked.connect(self.copyFormatRequested)
        self.btnPaste.clicked.connect(self.pasteFormatRequested)
        graph_row.addWidget(self.btnMore)
        graph_row.addWidget(self.btnCopy)
        graph_row.addWidget(self.btnPaste)
        root.addLayout(graph_row)

        hint = QLabel("Tip: double-click a title, axis label, or legend text to edit it.", self)
        hint.setWordWrap(True)
        root.addWidget(hint)

    def set_selection(self, labels: Iterable[str], values: dict | None = None) -> None:
        labels_list = [str(label) for label in labels if str(label)]
        self._selection_count = len(labels_list)
        if not labels_list:
            self.selectionLabel.setText("Select one or more layers above")
        elif len(labels_list) == 1:
            self.selectionLabel.setText(f"Selected: {labels_list[0]}")
        else:
            preview = ", ".join(labels_list[:2])
            if len(labels_list) > 2:
                preview += f" +{len(labels_list) - 2} more"
            self.selectionLabel.setText(f"{len(labels_list)} layers selected: {preview}")
        self.btnApply.setEnabled(bool(labels_list))
        self._show_current_values(dict(values or {}))

    def style_values(self) -> dict:
        result = {}
        if self.chkColor.isChecked() and self._color:
            result["color"] = self._color
        if self.chkAlpha.isChecked():
            result["alpha"] = float(self.spAlpha.value())
        if self.chkWidth.isChecked():
            result["linewidth"] = float(self.spWidth.value())
        marker = self.cboMarker.currentData()
        if self._marker_dirty and marker is not None:
            result["marker"] = str(marker)
        palette = self.cboPalette.currentData()
        if self._palette_dirty and palette:
            result["palette"] = str(palette)
        return result

    def reset_choices(self) -> None:
        self._color = None
        self._marker_dirty = False
        self._palette_dirty = False
        self.chkColor.setChecked(False)
        self.chkAlpha.setChecked(False)
        self.chkWidth.setChecked(False)
        self.cboMarker.setCurrentIndex(0)
        self.cboPalette.setCurrentIndex(0)
        self.btnColor.setText("Choose…")
        self.btnColor.setStyleSheet("")

    def _show_current_values(self, values: dict) -> None:
        """Show common/mixed values without marking them for application."""
        mixed = set(values.get("mixed_fields", ()))
        unavailable = set(values.get("unavailable_fields", ()))
        color = values.get("color")
        self._color = str(color) if color else None
        self.chkColor.setChecked(False)
        self.chkColor.setText("Color (mixed)" if "color" in mixed else "Color")
        if color:
            qcolor = QColor(str(color))
            self.btnColor.setText(str(color))
            self.btnColor.setStyleSheet(
                f"QPushButton {{ background: {color}; color: "
                f"{'#000000' if qcolor.lightnessF() > 0.6 else '#ffffff'}; }}"
            )
        else:
            self.btnColor.setText("Mapped" if "color" in unavailable else
                                  ("Mixed" if "color" in mixed else "Choose…"))
            self.btnColor.setStyleSheet("")

        for checkbox, spin, key, base in (
            (self.chkAlpha, self.spAlpha, "alpha", "Opacity"),
            (self.chkWidth, self.spWidth, "linewidth", "Line / edge"),
        ):
            spin.blockSignals(True)
            try:
                if values.get(key) is not None:
                    spin.setValue(float(values[key]))
            finally:
                spin.blockSignals(False)
            checkbox.setChecked(False)
            checkbox.setText(f"{base} (mixed)" if key in mixed else base)

        self.cboMarker.blockSignals(True)
        try:
            marker = values.get("marker")
            index = self.cboMarker.findData(marker) if marker is not None else 0
            self.cboMarker.setCurrentIndex(max(0, index))
            self.cboMarker.setToolTip(
                "Mixed markers — choose one to apply to all selected layers"
                if "marker" in mixed else ""
            )
        finally:
            self.cboMarker.blockSignals(False)
        self._marker_dirty = False
        self.cboPalette.blockSignals(True)
        self.cboPalette.setCurrentIndex(0)
        self.cboPalette.blockSignals(False)
        self._palette_dirty = False

    def _mark_marker_dirty(self, _index: int) -> None:
        self._marker_dirty = True

    def _mark_palette_dirty(self, _index: int) -> None:
        self._palette_dirty = True

    def _choose_color(self) -> None:
        initial = QColor(self._color or "#4f9cf9")
        chosen = QColorDialog.getColor(initial, self, "Layer Color")
        if not chosen.isValid():
            return
        self._color = chosen.name()
        self.chkColor.setChecked(True)
        self.btnColor.setText(self._color)
        self.btnColor.setStyleSheet(
            f"QPushButton {{ background: {self._color}; color: "
            f"{'#000000' if chosen.lightnessF() > 0.6 else '#ffffff'}; }}"
        )

    def _emit_apply(self) -> None:
        if self._selection_count:
            self.applyRequested.emit(self.style_values())


__all__ = ["QuickFormatWidget"]
