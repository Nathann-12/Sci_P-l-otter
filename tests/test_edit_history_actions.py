from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLineEdit


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp):
    import main as app_main

    window = app_main.MainWindow()
    yield window
    window.close()


def test_main_undo_redo_actions_follow_active_graph_history(win, qapp):
    tab_id = win.tabs.add_tab("History actions")
    tab = win.tabs.tabs[tab_id]
    ax = tab.get_axes()
    win._bind_active_graph_history()
    tab.graph_undo_stack.clear()

    with tab.graph_format_transaction("Edit title"):
        ax.set_title("After")
    qapp.processEvents()

    assert win.actUndo.isEnabled()
    assert "Edit title" in win.actUndo.text()
    win.actUndo.trigger()
    assert ax.get_title() == ""
    assert win.actRedo.isEnabled()
    assert "Edit title" in win.actRedo.text()

    win.actRedo.trigger()
    assert ax.get_title() == "After"


def test_ctrl_z_router_preserves_native_text_editor_undo(win, qapp):
    win.show()
    win.activateWindow()
    tab_id = win.tabs.add_tab("Native editor")
    tab = win.tabs.tabs[tab_id]
    ax = tab.get_axes()
    with tab.graph_format_transaction("Graph title"):
        ax.set_title("Graph changed")

    edit = QLineEdit(win)
    edit.show()
    edit.activateWindow()
    edit.setFocus()
    edit.setText("draft")
    edit.insert(" text")
    qapp.processEvents()
    assert edit.isUndoAvailable()
    win._sync_edit_history_actions()
    assert win.actUndo.isEnabled()
    assert win.actUndo.text() == "Undo Text Edit"

    win._undo_user_edit()
    assert edit.text() != "draft text"
    assert ax.get_title() == "Graph changed"  # graph history was not stolen
    assert tab.graph_undo_stack.canUndo()
    assert win.actRedo.isEnabled()
    assert win.actRedo.text() == "Redo Text Edit"
    edit.close()


def test_annotation_and_graph_undo_follow_edit_chronology_not_tool_mode(win, qapp):
    tab_id = win.tabs.add_tab("Unified timeline")
    tab = win.tabs.tabs[tab_id]
    manager = tab.annotation_manager
    manager.set_enabled(True)
    tab.graph_undo_stack.clear()

    # Older annotation edit, then newer graph edit: graph must undo first even
    # while the annotation tool remains enabled.
    manager._snapshot()
    with tab.graph_format_transaction("Newer graph title"):
        tab.get_axes().set_title("Newest")
    assert manager._undo
    win._undo_user_edit()
    assert tab.get_axes().get_title() == ""
    assert manager._undo

    # Undo the older annotation entry. Redo must then rebuild the original
    # timeline from oldest to newest: annotation first, graph second.
    win._undo_user_edit()
    assert not manager._undo
    assert tab.graph_undo_stack.canRedo()
    assert manager._redo

    win._redo_user_edit()
    assert not manager._redo
    assert tab.get_axes().get_title() == ""
    win._redo_user_edit()
    assert tab.get_axes().get_title() == "Newest"


def test_canvas_layer_hit_test_skips_hidden_overlapping_artist(win):
    from matplotlib.backend_bases import MouseEvent

    tab_id = win.tabs.add_tab("Hit testing")
    tab = win.tabs.tabs[tab_id]
    visible, = tab.get_axes().plot([0, 1], [0, 1], linewidth=5)
    hidden, = tab.get_axes().plot([0, 1], [0, 1], linewidth=8)
    visible_id = tab.register_layer([visible], "Visible", "line")
    hidden_id = tab.register_layer([hidden], "Hidden", "line")
    tab._set_layer_visibility(hidden_id, False, refresh=False)
    tab.canvas.draw()
    x, y = tab.get_axes().transData.transform((0.5, 0.5))
    event = MouseEvent("button_press_event", tab.canvas, x, y, button=1)

    assert win._layer_id_at_event(tab, event) == visible_id


def test_new_annotation_edit_invalidates_abandoned_graph_redo_branch(win):
    tab_id = win.tabs.add_tab("Redo branch")
    tab = win.tabs.tabs[tab_id]
    with tab.graph_format_transaction("Graph branch"):
        tab.get_axes().set_title("Changed")
    tab.graph_undo_stack.undo()
    assert tab.graph_undo_stack.canRedo()

    tab.annotation_manager._snapshot()
    win._sync_edit_history_actions()

    assert tab._graph_redo_invalidated is True
    assert win._history_owner(tab, tab.annotation_manager, redo=True) is None
    assert win.actRedo.isEnabled() is False
