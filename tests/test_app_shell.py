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

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from UI.shell.app_shell import AppShell


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_register_context_stays_hidden_until_explicitly_shown(qapp):
    shell = AppShell()

    page_data = QLabel("data context")
    page_plot = QLabel("plot context")

    shell.register_context("data", "ข้อมูล", page_data)
    shell.register_context("plot", "กราฟ", page_plot)

    # first registered context is selected internally, but visually parked so
    # startup stays sheet-first instead of module-first.
    assert shell.current_context_id() == "data"
    assert shell.context_stack.currentWidget() is page_data
    assert shell.rail.isHidden()
    assert shell.context_stack.isHidden()

    shell.show_activity_context()
    assert not shell.rail.isHidden()
    assert not shell.context_stack.isHidden()

    # switching the rail switches the visible context page
    shell.rail.set_active("plot")
    assert shell.current_context_id() == "plot"
    assert shell.context_stack.currentWidget() is page_plot


def test_set_workspace_and_inspector(qapp):
    shell = AppShell()

    workspace = QLabel("workspace")
    inspector = QLabel("inspector")

    shell.set_workspace(workspace)
    shell.set_inspector(inspector)

    assert shell.workspace_widget() is workspace
    assert shell.inspector_widget() is inspector
    assert workspace.parent() is shell.workspace_container
    assert inspector.parent() is shell.inspector_container

    # replacing the workspace re-parents the old one away
    new_workspace = QLabel("workspace2")
    shell.set_workspace(new_workspace)
    assert shell.workspace_widget() is new_workspace
    assert new_workspace.parent() is shell.workspace_container


def test_add_dock_creates_tab(qapp):
    shell = AppShell()
    dock = QLabel("AI")
    index = shell.add_dock("AI", dock)

    assert not shell.dock_tabs.isHidden()
    assert shell.dock_tabs.count() == 1
    assert shell.dock_tabs.widget(index) is dock
    assert shell.dock_tabs.tabText(index) == "AI"


def test_add_side_panel_creates_parked_vertical_tab(qapp):
    from widgets.side_panel_tabs import SidePanelTabs

    shell = AppShell()
    explorer = QLabel("Project Explorer")
    log = QLabel("Messages")

    first = shell.add_side_panel("Project Explorer (1)", explorer)
    second = shell.add_side_panel("Messages Log", log)

    assert not shell.side_tabs.isHidden()
    assert shell.side_tabs.count() == 2
    assert shell.side_tabs.widget(first) is explorer
    assert shell.side_tabs.widget(second) is log
    assert shell.side_panel_widget("Project Explorer (1)") is explorer
    assert shell.side_tabs.is_collapsed()
    assert shell.layout().itemAt(0).widget() is shell.side_tabs
    assert shell.side_tabs.maximumWidth() == SidePanelTabs.COLLAPSED_WIDTH

    shell.side_tabs.tab_bar.tabBarClicked.emit(first)
    assert not shell.side_tabs.is_collapsed()
    shell.side_tabs.tab_bar.tabBarClicked.emit(first)
    assert shell.side_tabs.is_collapsed()


def test_command_palette_hook(qapp):
    shell = AppShell()

    class FakePalette(QWidget):
        def __init__(self):
            super().__init__()
            self.opened = 0

        def open_palette(self):
            self.opened += 1

    palette = FakePalette()
    shell.set_command_palette(palette)
    assert shell.command_palette() is palette

    shell.open_command_palette()
    assert palette.opened == 1


def test_shell_stylesheet_is_loaded(qapp):
    shell = AppShell()
    # shell.qss is layered onto the shell's own stylesheet on construction
    assert "#ActivityRail" in shell.styleSheet()
    assert "#SidePanelTabs" in shell.styleSheet()
    assert "#CommandPalette" in shell.styleSheet()


def test_default_layout_sizes(qapp):
    from UI.shell.app_shell import RAIL_WIDTH

    shell = AppShell()
    # rail has a fixed, deterministic width
    assert shell.rail.width() == RAIL_WIDTH
    assert shell.rail.minimumWidth() == RAIL_WIDTH

    # splitter handles are thin (1px)
    assert shell._top_splitter.handleWidth() == 1
    assert shell._main_splitter.handleWidth() == 1

    # bottom dock is collapsible via the splitter; top panes are not
    assert shell._main_splitter.isCollapsible(1)
    assert not shell._top_splitter.childrenCollapsible()
    assert shell.layout().itemAt(0).widget() is shell.side_tabs
    assert shell.layout().itemAt(1).widget() is shell.rail


def test_rail_stays_hidden_until_context_is_explicitly_opened(qapp):
    shell = AppShell()
    assert shell.rail.isHidden()
    assert shell.context_stack.isHidden()

    shell.register_context("gas", "Gas Sensor", QLabel("gas module"))
    assert shell.rail.isHidden()
    assert shell.context_stack.isHidden()

    shell.show_activity_context("gas")
    assert not shell.rail.isHidden()
    assert not shell.context_stack.isHidden()

    shell.hide_activity_context()
    assert shell.rail.isHidden()
    assert shell.context_stack.isHidden()


def test_reselecting_active_activity_toggles_the_panel(qapp):
    shell = AppShell()
    shell.register_context("gas", "Gas", QLabel("gas"))
    shell.register_context("data", "Data", QLabel("data"))
    assert shell.rail.isHidden()
    assert shell.context_stack.isHidden()

    shell.show_activity_context("gas")
    assert not shell.context_stack.isHidden()

    # click the active activity again → panel collapses (rail stays)
    shell.rail.button_for("gas").click()
    assert shell.context_stack.isHidden()
    assert not shell.rail.isHidden()

    # click once more → panel comes back
    shell.rail.button_for("gas").click()
    assert not shell.context_stack.isHidden()

    # collapse, then switch to another activity → panel reopens on it
    shell.rail.button_for("gas").click()
    assert shell.context_stack.isHidden()
    shell.rail.button_for("data").click()
    assert not shell.context_stack.isHidden()
    assert shell.current_context_id() == "data"


def test_set_inspector_visible_collapses_the_column(qapp):
    shell = AppShell()

    # visible by default; hiding must hide the *container* so the splitter
    # reclaims the inspector column instead of leaving a dead strip
    assert not shell.inspector_container.isHidden()
    shell.set_inspector_visible(False)
    assert shell.inspector_container.isHidden()
    shell.set_inspector_visible(True)
    assert not shell.inspector_container.isHidden()


def test_register_context_passes_icon_to_rail(qapp):
    from PySide6.QtGui import QIcon

    shell = AppShell()
    page = QLabel("data context")
    shell.register_context("data", "Data", page, icon=QIcon())

    btn = shell.rail.button_for("data")
    assert btn is not None
    # icon=None path must keep working too
    shell.register_context("plot", "Plot", QLabel("plot"), icon=None)
    assert shell.rail.button_for("plot") is not None
