"""Analysis Recipe manager used by the desktop scientific workflow."""
from __future__ import annotations

from typing import Iterable, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class RecipeManagerDialog(QDialog):
    run_requested = Signal(str)
    mode_requested = Signal(str, str)
    duplicate_requested = Signal(str)
    export_requested = Signal(str)
    delete_requested = Signal(str)

    HEADERS = ("Name", "Mode", "Status", "Source", "Result", "Last run")

    def __init__(self, recipes: Iterable[Mapping], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Analysis Recipes")
        self.resize(850, 430)
        self._rows: list[dict] = []

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Recipes preserve data mappings, parameters, dependencies, and provenance. "
            "Auto recalculates after source edits; Manual waits for Run; Frozen keeps the saved result."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, len(self.HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._sync_controls)
        self.table.itemDoubleClicked.connect(lambda *_: self._emit_run())
        layout.addWidget(self.table, 1)

        controls = QHBoxLayout()
        self.run_button = QPushButton("Run / Recalculate")
        self.run_button.clicked.connect(self._emit_run)
        controls.addWidget(self.run_button)
        controls.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Auto", "Manual", "Frozen"])
        self.mode_combo.activated.connect(self._emit_mode)
        controls.addWidget(self.mode_combo)
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.clicked.connect(self._emit_duplicate)
        controls.addWidget(self.duplicate_button)
        self.export_button = QPushButton("Export...")
        self.export_button.clicked.connect(self._emit_export)
        controls.addWidget(self.export_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._emit_delete)
        controls.addWidget(self.delete_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.detail)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.set_recipes(recipes)

    def set_recipes(self, recipes: Iterable[Mapping]) -> None:
        selected = self.selected_recipe_id()
        self._rows = [dict(recipe) for recipe in recipes]
        self.table.setRowCount(len(self._rows))
        for row, recipe in enumerate(self._rows):
            values = (
                recipe.get("name", "Untitled Recipe"),
                recipe.get("mode", "Manual"),
                recipe.get("status", "Ready"),
                recipe.get("source", ""),
                recipe.get("result", ""),
                recipe.get("last_run", "Never"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, str(recipe.get("id", "")))
                if recipe.get("error"):
                    item.setToolTip(str(recipe["error"]))
                self.table.setItem(row, column, item)
            if str(recipe.get("id", "")) == selected:
                self.table.selectRow(row)
        self.table.resizeColumnsToContents()
        if self._rows and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self._sync_controls()

    def selected_recipe_id(self) -> str:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return str(item.data(Qt.UserRole)) if item is not None else ""

    def _selected_recipe(self) -> dict:
        recipe_id = self.selected_recipe_id()
        return next((row for row in self._rows if str(row.get("id")) == recipe_id), {})

    def _sync_controls(self) -> None:
        recipe = self._selected_recipe()
        enabled = bool(recipe)
        for button in (
            self.run_button, self.duplicate_button, self.export_button, self.delete_button,
        ):
            button.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        if not enabled:
            self.detail.setText("No analysis recipes in this project yet.")
            return
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(str(recipe.get("mode", "Manual")).title())
        self.mode_combo.blockSignals(False)
        checksum = recipe.get("source_checksum") or "not calculated"
        detail = f"Operation: {recipe.get('operation', '')}   |   Source checksum: {checksum}"
        if recipe.get("error"):
            detail += f"\nLast error: {recipe['error']} (the last good result was kept)"
        self.detail.setText(detail)

    def _emit_run(self) -> None:
        if recipe_id := self.selected_recipe_id():
            self.run_requested.emit(recipe_id)

    def _emit_mode(self) -> None:
        if recipe_id := self.selected_recipe_id():
            self.mode_requested.emit(recipe_id, self.mode_combo.currentText())

    def _emit_duplicate(self) -> None:
        if recipe_id := self.selected_recipe_id():
            self.duplicate_requested.emit(recipe_id)

    def _emit_export(self) -> None:
        if recipe_id := self.selected_recipe_id():
            self.export_requested.emit(recipe_id)

    def _emit_delete(self) -> None:
        if recipe_id := self.selected_recipe_id():
            self.delete_requested.emit(recipe_id)


__all__ = ["RecipeManagerDialog"]
