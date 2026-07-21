from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QInputDialog

from widgets.layer_manager import LayerManagerWidget


def _manager_with_layers() -> LayerManagerWidget:
    manager = LayerManagerWidget()
    manager.add_layer("line-a", "Line A", "line")
    manager.add_layer("line-b", "Line B", "line")
    manager.add_layer("line-c", "Line C", "line")
    return manager


def test_layer_tree_uses_extended_selection_and_reports_visual_order():
    manager = _manager_with_layers()
    emitted = []
    manager.layerSelectionChanged.connect(lambda layer_ids: emitted.append(list(layer_ids)))

    assert manager.tree.selectionMode() == QAbstractItemView.ExtendedSelection

    # Select out of order; callers receive the stable order shown in the tree.
    manager.tree.topLevelItem(2).setSelected(True)
    manager.tree.topLevelItem(0).setSelected(True)

    assert manager.selected_layer_ids() == ["line-a", "line-c"]
    assert emitted[-1] == ["line-a", "line-c"]


def test_button_state_reflects_single_and_multiple_selection():
    manager = _manager_with_layers()

    assert not manager.btnRename.isEnabled()
    assert not manager.btnDelete.isEnabled()
    assert not manager.btnStyle.isEnabled()

    manager.tree.topLevelItem(0).setSelected(True)
    assert manager.btnRename.isEnabled()
    assert manager.btnDelete.isEnabled()
    assert manager.btnStyle.isEnabled()

    manager.tree.topLevelItem(1).setSelected(True)
    assert not manager.btnRename.isEnabled()
    assert manager.btnDelete.isEnabled()
    assert manager.btnStyle.isEnabled()


def test_style_request_is_emitted_once_for_current_selected_layer():
    manager = _manager_with_layers()
    requested = []
    manager.layerStyleRequested.connect(requested.append)

    first = manager.tree.topLevelItem(0)
    last = manager.tree.topLevelItem(2)
    first.setSelected(True)
    last.setSelected(True)
    manager.tree.setCurrentItem(last)
    first.setSelected(True)

    manager._style_selected()

    assert requested == ["line-c"]


def test_remove_emits_each_selected_id_safely_when_receiver_removes_items():
    manager = _manager_with_layers()
    removed = []

    def remove_immediately(layer_id: str) -> None:
        removed.append(layer_id)
        manager.remove_layer(layer_id)

    manager.layerRemoveRequested.connect(remove_immediately)
    manager.tree.topLevelItem(2).setSelected(True)
    manager.tree.topLevelItem(0).setSelected(True)

    manager._delete_selected()

    assert removed == ["line-a", "line-c"]
    assert manager.tree.topLevelItemCount() == 1
    assert manager.tree.topLevelItem(0).data(0, Qt.UserRole) == "line-b"


def test_rename_is_ignored_for_multiple_selection(monkeypatch):
    manager = _manager_with_layers()
    dialog_calls = []
    rename_requests = []
    manager.layerRenameRequested.connect(lambda *args: rename_requests.append(args))

    def fake_get_text(*args, **kwargs):
        dialog_calls.append((args, kwargs))
        return "Renamed", True

    monkeypatch.setattr(QInputDialog, "getText", fake_get_text)
    manager.tree.topLevelItem(0).setSelected(True)
    manager.tree.topLevelItem(1).setSelected(True)

    manager._rename_selected()

    assert dialog_calls == []
    assert rename_requests == []


def test_programmatic_canvas_selection_emits_once_in_visual_order():
    manager = _manager_with_layers()
    emitted = []
    manager.layerSelectionChanged.connect(lambda ids: emitted.append(list(ids)))

    manager.select_layer_ids(["line-c", "line-a"])

    assert manager.selected_layer_ids() == ["line-a", "line-c"]
    assert emitted == [["line-a", "line-c"]]
