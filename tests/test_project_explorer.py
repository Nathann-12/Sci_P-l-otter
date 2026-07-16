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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidgetItem, QWidget

from UI.mdi_workspace import MdiWorkspace
from UI.project_explorer import ProjectExplorer


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Host(QWidget):
    """Stand-in for MainWindow: provides plot_mode that the workspace reads."""

    def __init__(self, plot_mode="REPLACE"):
        super().__init__()
        self.plot_mode = plot_mode


def _leaf_titles(explorer):
    """Return titles of every window (leaf) node mapped to a sub-window."""
    return sorted(item.text(0) for item in explorer._item_to_sub.keys())


def _find_leaf(explorer, title):
    for item, sub in explorer._item_to_sub.items():
        if item.text(0) == title:
            return item, sub
    return None, None


def test_all_windows_helper_lists_graphs_and_books(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # starts with "Graph 1"
    ws.add_book(QWidget(), "Book1")

    windows = ws.all_windows()
    kinds = {kind for kind, _t, _s in windows}
    assert kinds == {"graph", "book"}
    titles = {t for _k, t, _s in windows}
    assert "Graph 1" in titles and "Book1" in titles


def test_explorer_lists_both_book_and_graph(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    ws.add_book(QWidget(), "Book1")

    explorer = ProjectExplorer(host, workspace=ws)

    titles = _leaf_titles(explorer)
    assert "Graph 1" in titles
    assert "Book1" in titles
    # Two window leaves total (one graph, one book).
    assert len(explorer._item_to_sub) == 2


def test_explorer_grows_on_signal(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    explorer = ProjectExplorer(host, workspace=ws)

    assert len(explorer._item_to_sub) == 1

    ws.add_tab("Graph 2")  # emits subWindowAdded -> explorer rebuilds

    titles = _leaf_titles(explorer)
    assert "Graph 1" in titles and "Graph 2" in titles
    assert len(explorer._item_to_sub) == 2


def test_double_click_activates_sub_window(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    ws.add_tab("Graph 2")  # Graph 2 is now active
    explorer = ProjectExplorer(host, workspace=ws)

    item, sub = _find_leaf(explorer, "Graph 1")
    assert item is not None and sub is not None

    # Simulate the double-click / activation path.
    explorer._on_item_activated(item, 0)

    assert ws.mdi.activeSubWindow() is sub


def test_activate_book_sub_window(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    book_sub = ws.add_book(QWidget(), "Book1")
    explorer = ProjectExplorer(host, workspace=ws)

    item, sub = _find_leaf(explorer, "Book1")
    assert sub is book_sub

    explorer._on_item_activated(item, 0)
    assert ws.mdi.activeSubWindow() is book_sub


def test_rename_reflects_in_tree(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    tab_id = ws.get_current_tab_id()
    explorer = ProjectExplorer(host, workspace=ws)

    assert "Graph 1" in _leaf_titles(explorer)

    ws.rename_tab(tab_id, "Renamed Graph")  # emits subWindowRenamed

    titles = _leaf_titles(explorer)
    assert "Renamed Graph" in titles
    assert "Graph 1" not in titles


def test_remove_reflects_in_tree(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    second = ws.add_tab("Graph 2")
    explorer = ProjectExplorer(host, workspace=ws)

    assert len(explorer._item_to_sub) == 2

    ws._remove_tab_by_id(second)  # emits subWindowRemoved

    titles = _leaf_titles(explorer)
    assert "Graph 2" not in titles
    assert len(explorer._item_to_sub) == 1


def test_closed_book_is_dropped_from_tree(qapp):
    # Regression: closing a Book used to keep it in the registry/Explorer. Now
    # closing a Book removes it (and the tree also filters hidden windows).
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    ws.add_book(QWidget(), "Book1")
    book2 = ws.add_book(QWidget(), "Book2")  # need >1 (last Book can't close)
    explorer = ProjectExplorer(host, workspace=ws)
    assert "Book2" in _leaf_titles(explorer)

    book2.close()             # removes it (emits subWindowRemoved -> refresh)

    assert "Book2" not in _leaf_titles(explorer)
    assert "Book1" in _leaf_titles(explorer)
    assert "Graph 1" in _leaf_titles(explorer)  # untouched


def test_close_from_context_menu_removes_book_node(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    ws.add_book(QWidget(), "Book1")
    ws.add_book(QWidget(), "Book2")
    explorer = ProjectExplorer(host, workspace=ws)

    _item, sub = _find_leaf(explorer, "Book2")
    explorer._close_item(sub)   # the Explorer's "Close" action

    assert "Book2" not in _leaf_titles(explorer)
    assert "Book1" in _leaf_titles(explorer)


def test_last_book_close_is_blocked_and_stays_in_tree(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    ws.add_book(QWidget(), "Book1")  # the only Book
    explorer = ProjectExplorer(host, workspace=ws)

    _item, sub = _find_leaf(explorer, "Book1")
    explorer._close_item(sub)   # blocked by the last-Book guard

    assert "Book1" in _leaf_titles(explorer)


def test_rename_book_from_explorer_updates_tree_and_registry(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    ws.add_book(QWidget(), "Book1")
    explorer = ProjectExplorer(host, workspace=ws)

    _item, sub = _find_leaf(explorer, "Book1")
    explorer._rename_book(sub, "Measurements")

    assert "Measurements" in _leaf_titles(explorer)
    assert "Book1" not in _leaf_titles(explorer)
    # registry key stays in sync with the window title
    assert "Measurements" in ws._books and "Book1" not in ws._books
    assert sub.windowTitle() == "Measurements"


def test_graph_tab_id_resolution_for_rename(qapp):
    # _rename_item opens a modal dialog (can't run headless); exercise the
    # tab-id resolution it relies on, plus the rename_tab plumbing.
    host = _Host()
    ws = MdiWorkspace(host)  # "Graph 1"
    explorer = ProjectExplorer(host, workspace=ws)

    _item, sub = _find_leaf(explorer, "Graph 1")
    tab_id = explorer._graph_tab_id_for(sub)
    assert tab_id is not None
    ws.rename_tab(tab_id, "Signal")
    assert "Signal" in _leaf_titles(explorer)


def test_set_workspace_rebinds_and_refreshes(qapp):
    host = _Host()
    ws1 = MdiWorkspace(host)
    explorer = ProjectExplorer(host)  # no workspace yet
    assert len(explorer._item_to_sub) == 0

    explorer.set_workspace(ws1)
    assert "Graph 1" in _leaf_titles(explorer)

    # Rebinding to a different workspace should re-wire signals and refresh.
    ws2 = MdiWorkspace(host)
    ws2.add_tab("Graph X")
    explorer.set_workspace(ws2)

    titles = _leaf_titles(explorer)
    assert "Graph X" in titles

    # Signals from the old workspace no longer touch the tree.
    ws1.add_tab("Ghost")
    assert "Ghost" not in _leaf_titles(explorer)
