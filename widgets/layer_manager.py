from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QInputDialog,
    QColorDialog,
)


class LayerManagerWidget(QWidget):
    """Simple per-tab layer controller for Matplotlib artists."""

    layerVisibilityChanged = Signal(str, bool)
    layerRenameRequested = Signal(str, str)
    layerRemoveRequested = Signal(str)
    layerStyleRequested = Signal(str)
    layerSelectionChanged = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: Dict[str, QTreeWidgetItem] = {}
        self._suspend_item_changed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Layer", "Type"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._rename_selected)
        root.addWidget(self.tree)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btnRename = QPushButton("Rename", self)
        self.btnDelete = QPushButton("Remove", self)
        self.btnStyle = QPushButton("Style…", self)

        for btn in (self.btnRename, self.btnDelete, self.btnStyle):
            btn.setEnabled(False)
            btn_row.addWidget(btn)

        self.btnRename.clicked.connect(self._rename_selected)
        self.btnDelete.clicked.connect(self._delete_selected)
        self.btnStyle.clicked.connect(self._style_selected)

        root.addLayout(btn_row)

    # --- public API -------------------------------------------------

    def clear_layers(self) -> None:
        self._items.clear()
        self.tree.clear()
        self._update_button_state()

    def add_layer(self, layer_id: str, label: str, layer_type: str, *, visible: bool = True) -> None:
        item = QTreeWidgetItem([label, layer_type])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        item.setData(0, Qt.UserRole, layer_id)
        item.setCheckState(0, Qt.Checked if visible else Qt.Unchecked)
        self.tree.addTopLevelItem(item)
        self._items[layer_id] = item
        self._update_button_state()

    def update_layer_label(self, layer_id: str, label: str) -> None:
        item = self._items.get(layer_id)
        if not item:
            return
        self._suspend_item_changed = True
        item.setText(0, label)
        self._suspend_item_changed = False

    def update_layer_visibility(self, layer_id: str, visible: bool) -> None:
        item = self._items.get(layer_id)
        if not item:
            return
        self._suspend_item_changed = True
        item.setCheckState(0, Qt.Checked if visible else Qt.Unchecked)
        self._suspend_item_changed = False

    def remove_layer(self, layer_id: str) -> None:
        item = self._items.pop(layer_id, None)
        if not item:
            return
        index = self.tree.indexOfTopLevelItem(item)
        if index >= 0:
            self.tree.takeTopLevelItem(index)
        self._update_button_state()

    def selected_layer_ids(self) -> List[str]:
        """Return selected layer IDs in their current visual tree order."""
        selected: List[str] = []
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item is None or not item.isSelected():
                continue
            layer_id = item.data(0, Qt.UserRole)
            if layer_id is not None:
                selected.append(str(layer_id))
        return selected

    def select_layer_ids(self, layer_ids, *, clear: bool = True) -> None:
        """Select logical layers programmatically and emit one coherent change."""
        wanted = {str(layer_id) for layer_id in (layer_ids or ())}
        self.tree.blockSignals(True)
        try:
            if clear:
                self.tree.clearSelection()
            matches = []
            for index in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(index)
                if item is None:
                    continue
                layer_id = str(item.data(0, Qt.UserRole) or "")
                if layer_id not in wanted:
                    continue
                matches.append(item)
            if matches:
                # setCurrentItem() may replace the selection; do it before the
                # explicit multi-select pass, never after it.
                self.tree.setCurrentItem(matches[0])
            for item in matches:
                item.setSelected(True)
        finally:
            self.tree.blockSignals(False)
        self._on_selection_changed()

    # --- helpers ----------------------------------------------------

    def _current_layer_id(self) -> Optional[str]:
        selected_ids = self.selected_layer_ids()
        if not selected_ids:
            return None

        current = self.tree.currentItem()
        if current is not None and current.isSelected():
            layer_id = current.data(0, Qt.UserRole)
            if layer_id is not None:
                return str(layer_id)
        return selected_ids[0]

    def _update_button_state(self) -> None:
        count = len(self.selected_layer_ids())
        self.btnRename.setEnabled(count == 1)
        self.btnDelete.setEnabled(count >= 1)
        self.btnStyle.setEnabled(count >= 1)

    def _on_selection_changed(self) -> None:
        selected_ids = self.selected_layer_ids()
        self._update_button_state()
        self.layerSelectionChanged.emit(selected_ids)

    # --- slots ------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._suspend_item_changed or column != 0:
            return
        layer_id = item.data(0, Qt.UserRole)
        if layer_id is None:
            return
        visible = item.checkState(0) == Qt.Checked
        self.layerVisibilityChanged.emit(str(layer_id), visible)

    def _rename_selected(self) -> None:
        if len(self.selected_layer_ids()) != 1:
            return
        layer_id = self._current_layer_id()
        if not layer_id:
            return
        item = self._items.get(layer_id)
        if not item:
            return
        text, ok = QInputDialog.getText(self, "Rename Layer", "Layer name:", text=item.text(0))
        if ok and text.strip():
            self.layerRenameRequested.emit(layer_id, text.strip())

    def _delete_selected(self) -> None:
        # Snapshot the IDs before emitting. Receivers commonly remove each
        # corresponding tree item synchronously, which mutates the selection.
        for layer_id in self.selected_layer_ids():
            self.layerRemoveRequested.emit(layer_id)

    def _style_selected(self) -> None:
        layer_id = self._current_layer_id()
        if not layer_id:
            return
        self.layerStyleRequested.emit(layer_id)

    def prompt_color(self, title: str = "Select Color"):
        return QColorDialog.getColor(parent=self, title=title)
