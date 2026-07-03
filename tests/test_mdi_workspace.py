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

from PySide6.QtWidgets import QApplication, QWidget

from UI.mdi_workspace import MdiWorkspace
from widgets.plot_tabs import GraphTab


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Host(QWidget):
    """Stand-in for MainWindow: provides plot_mode that the adapter reads."""

    def __init__(self, plot_mode="REPLACE"):
        super().__init__()
        self.plot_mode = plot_mode


def test_starts_with_one_graph(qapp):
    host = _Host()
    ws = MdiWorkspace(host)

    assert ws.count() == 1
    assert isinstance(ws.currentWidget(), GraphTab)

    tab_id = ws.get_current_tab_id()
    assert tab_id is not None
    assert tab_id in ws.tabs
    assert ws.tabs[tab_id] is ws.currentWidget()


def test_widget_and_indexof_insertion_order(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    first = ws.currentWidget()
    second_id = ws.add_tab("Graph 2")

    assert ws.count() == 2
    assert ws.widget(0) is first
    assert ws.widget(1) is ws.tabs[second_id]
    assert ws.indexOf(ws.tabs[second_id]) == 1


def test_add_tab_emits_signals_and_activates(qapp):
    host = _Host()
    ws = MdiWorkspace(host)

    created = []
    changed = []
    ws.tabCreated.connect(created.append)
    ws.currentChanged.connect(changed.append)

    new_id = ws.add_tab("Graph 2")

    assert new_id in created
    assert changed, "currentChanged should fire when a second graph is added"
    # The newly created graph becomes the active one.
    assert ws.get_current_tab_id() == new_id
    assert ws.currentWidget() is ws.tabs[new_id]


def test_add_series_to_current_tab_lands_on_axes(qapp):
    host = _Host(plot_mode="OVERLAY")
    ws = MdiWorkspace(host)
    tab_id = ws.get_current_tab_id()
    graph_tab = ws.tabs[tab_id]

    created = ws.add_series_to_current_tab(
        [1, 2, 3], [10, 20, 15], label="demo", style="line"
    )

    assert created, "a layer should be created"
    assert len(graph_tab.get_axes().lines) == 1
    assert len(graph_tab.layers) == 1
    layer = next(iter(graph_tab.layers.values()))
    assert layer["style"] == "line"


def test_plot_to_tabs_replace_mode(qapp):
    host = _Host(plot_mode="REPLACE")
    ws = MdiWorkspace(host)
    tab_id = ws.get_current_tab_id()
    graph_tab = ws.tabs[tab_id]

    ws.plot_to_tabs([tab_id], [1, 2, 3], [4, 5, 6], label="line1", style="line")
    assert len(graph_tab.get_axes().lines) == 1

    # REPLACE mode clears previous content before plotting the new series.
    ws.plot_to_tabs([tab_id], [1, 2, 3], [7, 8, 9], label="line2", style="line")
    assert len(graph_tab.get_axes().lines) == 1
    assert len(graph_tab.layers) == 1


def test_plot_to_tabs_overlay_mode_accumulates(qapp):
    host = _Host(plot_mode="OVERLAY")
    ws = MdiWorkspace(host)
    tab_id = ws.get_current_tab_id()
    graph_tab = ws.tabs[tab_id]

    ws.plot_to_tabs([tab_id], [1, 2, 3], [4, 5, 6], label="a", style="line")
    ws.plot_to_tabs([tab_id], [1, 2, 3], [7, 8, 9], label="b", style="line")

    assert len(graph_tab.get_axes().lines) == 2
    assert len(graph_tab.layers) == 2


def test_scatter_lands_as_collection(qapp):
    host = _Host(plot_mode="OVERLAY")
    ws = MdiWorkspace(host)
    tab_id = ws.get_current_tab_id()
    graph_tab = ws.tabs[tab_id]

    ws.add_series_to_tabs([tab_id], [1, 2, 3], [4, 5, 6], label="pts", style="scatter")

    assert len(graph_tab.get_axes().collections) == 1
    scatter = next(iter(graph_tab.layers.values()))
    assert scatter["style"] == "scatter"


def test_get_open_tabs(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    ws.add_tab("Graph 2")

    open_tabs = ws.get_open_tabs()
    assert len(open_tabs) == 2
    ids = [tid for tid, _name in open_tabs]
    names = [name for _tid, name in open_tabs]
    assert set(ids) == set(ws.tabs.keys())
    assert "Graph 1" in names and "Graph 2" in names


def test_remove_all_tabs_emits_removed(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    ws.add_tab("Graph 2")

    removed = []
    ws.tabRemoved.connect(removed.append)

    ws.remove_all_tabs()

    assert ws.count() == 0
    assert ws.tabs == {}
    assert len(removed) == 2


def test_set_current_index_activates(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    first_id = ws.get_current_tab_id()
    second_id = ws.add_tab("Graph 2")

    ws.setCurrentIndex(0)
    assert ws.get_current_tab_id() == first_id

    ws.setCurrentIndex(1)
    assert ws.get_current_tab_id() == second_id
    assert ws.currentIndex() == 1


def test_add_book_creates_sub_window(qapp):
    host = _Host()
    ws = MdiWorkspace(host)

    added = []
    ws.subWindowAdded.connect(lambda kind, title: added.append((kind, title)))

    book_widget = QWidget()
    sub = ws.add_book(book_widget, "Book1")

    assert sub is not None
    assert sub.widget() is book_widget
    assert sub.windowTitle() == "Book1"
    assert ("book", "Book1") in added

    kinds = [k for k, _t, _s in ws.sub_windows()]
    assert "book" in kinds
    assert "graph" in kinds


def test_addtab_compat_with_graphtab(qapp):
    host = _Host()
    ws = MdiWorkspace(host)

    gt = GraphTab("tab_external", "External", ws)
    idx = ws.addTab(gt, "External")

    assert ws.count() == 2
    assert ws.widget(idx) is gt
    assert "tab_external" in ws.tabs


def test_all_windows_matches_sub_windows(qapp):
    host = _Host()
    ws = MdiWorkspace(host)  # starts with one graph
    ws.add_book(QWidget(), "Book1")
    ws.add_tab("Graph 2")

    # all_windows() is the Project Explorer alias of sub_windows().
    assert ws.all_windows() == ws.sub_windows()

    kinds = [k for k, _t, _s in ws.all_windows()]
    titles = [t for _k, t, _s in ws.all_windows()]
    assert kinds.count("graph") == 2
    assert kinds.count("book") == 1
    assert "Graph 1" in titles and "Graph 2" in titles and "Book1" in titles


def test_rename_tab_updates_title(qapp):
    host = _Host()
    ws = MdiWorkspace(host)
    tab_id = ws.get_current_tab_id()

    renamed = []
    ws.subWindowRenamed.connect(lambda kind, title: renamed.append((kind, title)))

    ws.rename_tab(tab_id, "Renamed Graph")

    assert ws.tabs[tab_id].name == "Renamed Graph"
    assert ws.get_open_tabs()[0][1] == "Renamed Graph"
    assert ("graph", "Renamed Graph") in renamed
