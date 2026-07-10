# UI/shell/app_shell.py
from __future__ import annotations

import logging
import os
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from widgets.activity_rail import ActivityRail
from widgets.side_panel_tabs import SidePanelTabs

logger = logging.getLogger(__name__)

# Default sizes for the shell layout (px). Kept here so MainWindow stays thin.
RAIL_WIDTH = 76
CONTEXT_WIDTH = 200
INSPECTOR_WIDTH = 280
DOCK_HEIGHT = 110

_SHELL_QSS_CACHE: Optional[str] = None
_SHELL_QSS_LOGGED = False


class AppShell(QWidget):
    """โครงหลัก (shell) ของ Research OS — เป็น layout ล้วน ไม่ผูกกับ MainWindow

    การจัดวาง: parked side tabs (ซ้ายสุด) | ActivityRail | context stack | workspace กลาง | inspector ขวา
    พร้อม dock ด้านล่าง (QTabWidget) และ hook สำหรับเปิด command palette

    ทุก panel/widget จริงถูก "inject" เข้ามาผ่าน API ด้านล่าง เพื่อให้ MainWindow
    เอา TabManager / panel เดิมมาวางในภายหลังได้โดย shell ไม่ต้องรู้จัก MainWindow
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AppShell")

        self._context_pages: Dict[str, QWidget] = {}
        self._context_index: Dict[str, int] = {}
        self._docks: Dict[str, QWidget] = {}
        self._side_panels: Dict[str, QWidget] = {}
        self._command_palette: Optional[QWidget] = None

        # --- left: activity rail ---
        # Hidden by default even after module registration. Startup should stay
        # sheet-first; callers must explicitly show module contexts.
        self.rail = ActivityRail(self)
        self.rail.setFixedWidth(RAIL_WIDTH)
        self.rail.activity_changed.connect(self._on_activity_changed)
        # คลิกกิจกรรมที่ active ซ้ำ = ยุบ/กางแผง context (แบบ VS Code)
        self.rail.activity_toggled.connect(self._toggle_context_panel)
        self.rail.hide()

        # --- context stack (เปลี่ยนตามกิจกรรมที่เลือกใน rail) ---
        self.context_stack = QStackedWidget(self)
        self.context_stack.setObjectName("ContextStack")
        self.context_stack.setMinimumWidth(180)
        self.context_stack.hide()

        self.side_tabs = SidePanelTabs(self)
        self.side_tabs.hide()

        # --- central workspace ---
        self.workspace_container = QWidget(self)
        self.workspace_container.setObjectName("WorkspaceContainer")
        self._workspace_layout = QVBoxLayout(self.workspace_container)
        self._workspace_layout.setContentsMargins(0, 0, 0, 0)
        self._workspace_layout.setSpacing(0)
        self._workspace_widget: Optional[QWidget] = None

        # --- right inspector ---
        self.inspector_container = QWidget(self)
        self.inspector_container.setObjectName("InspectorContainer")
        self._inspector_layout = QVBoxLayout(self.inspector_container)
        self._inspector_layout.setContentsMargins(0, 0, 0, 0)
        self._inspector_layout.setSpacing(0)
        self._inspector_widget: Optional[QWidget] = None

        # --- bottom dock area ---
        self.dock_tabs = QTabWidget(self)
        self.dock_tabs.setObjectName("DockTabs")
        self.dock_tabs.setTabPosition(QTabWidget.South)
        # Explicit minimum so the splitter can actually shrink the dock to
        # DOCK_HEIGHT — otherwise the pages' minimumSizeHint (text edits/lists)
        # pins the dock at ~180px and steals workspace height.
        self.dock_tabs.setMinimumHeight(64)
        self.dock_tabs.hide()

        # --- vertical splitter: (top row) over (bottom dock) ---
        top_splitter = QSplitter(Qt.Horizontal, self)
        top_splitter.setObjectName("ShellTopSplitter")
        top_splitter.setHandleWidth(1)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.addWidget(self.context_stack)
        top_splitter.addWidget(self.workspace_container)
        top_splitter.addWidget(self.inspector_container)
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setStretchFactor(2, 0)
        # workspace dominates on startup so graphs/sheets get the room
        top_splitter.setSizes([CONTEXT_WIDTH, 1200, INSPECTOR_WIDTH])
        self._top_splitter = top_splitter

        main_splitter = QSplitter(Qt.Vertical, self)
        main_splitter.setObjectName("ShellMainSplitter")
        main_splitter.setHandleWidth(1)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self.dock_tabs)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        # bottom dock starts modest and is collapsible via the splitter
        main_splitter.setCollapsible(1, True)
        main_splitter.setSizes([700, DOCK_HEIGHT])
        self._main_splitter = main_splitter

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.side_tabs)
        root.addWidget(self.rail)
        root.addWidget(main_splitter, 1)

        # --- layer the shell stylesheet on top of the app theme ---
        self._apply_shell_stylesheet()

    def _apply_shell_stylesheet(self) -> None:
        """Load styles/shell.qss and append it so it layers on top of the
        existing dark theme without replacing it. Robust if the file is missing."""
        global _SHELL_QSS_CACHE, _SHELL_QSS_LOGGED
        try:
            # UI/shell/app_shell.py -> repo root is two levels up
            if _SHELL_QSS_CACHE is None:
                repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                qss_path = os.path.join(repo_root, "styles", "shell.qss")
                if not os.path.isfile(qss_path):
                    logger.debug("shell.qss not found at %s; skipping", qss_path)
                    _SHELL_QSS_CACHE = ""
                    return
                with open(qss_path, "r", encoding="utf-8") as f:
                    _SHELL_QSS_CACHE = f.read()
                if not _SHELL_QSS_LOGGED:
                    logger.info("Shell QSS loaded: %s (%d chars)", qss_path, len(_SHELL_QSS_CACHE))
                    _SHELL_QSS_LOGGED = True
            qss = _SHELL_QSS_CACHE
            if not qss:
                return
            existing = self.styleSheet() or ""
            self.setStyleSheet(existing + "\n" + qss if existing else qss)
        except Exception:
            logger.debug("Shell QSS load skipped", exc_info=True)

    # ------------------------------------------------------------------
    # Injection API
    # ------------------------------------------------------------------
    def register_context(self, activity_id: str, label: str, context_widget: QWidget, icon=None) -> None:
        """เพิ่มกิจกรรมใน rail + หน้า context ที่ผูกกันโดยไม่เปิด UI เอง"""
        if activity_id in self._context_pages:
            # แทนที่หน้าเดิมถ้าลงทะเบียนซ้ำ
            old = self._context_pages[activity_id]
            index = self.context_stack.indexOf(old)
            if index != -1:
                self.context_stack.removeWidget(old)
                old.setParent(None)
        index = self.context_stack.addWidget(context_widget)
        self._context_pages[activity_id] = context_widget
        self._context_index[activity_id] = index

        self.rail.add_activity(activity_id, label, icon=icon)
        # ถ้านี่เป็นกิจกรรมแรก rail จะ set active ให้ → sync หน้าตอนนี้
        if self.rail.current_activity() == activity_id:
            self.context_stack.setCurrentIndex(index)
        # Register only. Startup remains clean; use show_activity_context() to
        # reveal the rail/context when a module is explicitly opened.

    def show_activity_context(self, activity_id: Optional[str] = None) -> None:
        """Explicitly reveal the activity rail + context panel."""
        if not self._context_pages:
            return
        target = activity_id or self.rail.current_activity()
        if target not in self._context_index:
            return
        self.rail.show()
        self.context_stack.setCurrentIndex(self._context_index[target])
        if self.rail.current_activity() != target:
            self.rail.set_active(target)
        self.context_stack.show()

    def hide_activity_context(self) -> None:
        """Hide the specialty activity UI and return focus to the workspace."""
        self.context_stack.hide()
        self.rail.hide()

    def set_workspace(self, widget: QWidget) -> None:
        """วาง widget กลาง (เช่น TabManager) ในพื้นที่ workspace"""
        if self._workspace_widget is not None:
            self._workspace_layout.removeWidget(self._workspace_widget)
            self._workspace_widget.setParent(None)
        self._workspace_widget = widget
        if widget is not None:
            self._workspace_layout.addWidget(widget)

    def set_inspector(self, widget: QWidget) -> None:
        """วาง widget ตรวจสอบ (inspector) ด้านขวา"""
        if self._inspector_widget is not None:
            self._inspector_layout.removeWidget(self._inspector_widget)
            self._inspector_widget.setParent(None)
        self._inspector_widget = widget
        if widget is not None:
            self._inspector_layout.addWidget(widget)

    def set_inspector_visible(self, visible: bool) -> None:
        """ซ่อน/แสดง "ทั้งคอลัมน์" inspector ใน splitter

        ต้องซ่อนที่ container ไม่ใช่แค่ widget ข้างใน — ไม่งั้น splitter ยังกัน
        พื้นที่ INSPECTOR_WIDTH ไว้เป็นแถบว่างทางขวาของ workspace
        """
        self.inspector_container.setVisible(bool(visible))

    def add_dock(self, title: str, widget: QWidget) -> int:
        """เพิ่ม tab ใหม่ในพื้นที่ dock ด้านล่าง คืน index ของ tab"""
        index = self.dock_tabs.addTab(widget, title)
        self._docks[title] = widget
        self.dock_tabs.show()
        return index

    def add_side_panel(self, title: str, widget: QWidget) -> int:
        index = self.side_tabs.add_panel(title, widget)
        self._side_panels[title] = widget
        self.side_tabs.show()
        return index

    def side_panel_widget(self, title: str) -> Optional[QWidget]:
        return self._side_panels.get(title)

    def set_command_palette(self, palette: QWidget) -> None:
        """ผูก command palette เข้ากับ shell (ยังไม่เปิดจนกว่าจะเรียก open)"""
        self._command_palette = palette

    def open_command_palette(self) -> None:
        """เปิด command palette ที่ผูกไว้ (ถ้ามี)"""
        palette = self._command_palette
        if palette is None:
            return
        if hasattr(palette, "open_palette"):
            palette.open_palette()
        elif hasattr(palette, "show"):
            palette.show()
            palette.raise_()
            palette.activateWindow()

    # ------------------------------------------------------------------
    # Accessors / helpers
    # ------------------------------------------------------------------
    def context_widget(self, activity_id: str) -> Optional[QWidget]:
        """คืนหน้า context ของกิจกรรมที่ระบุ"""
        return self._context_pages.get(activity_id)

    def current_context_id(self) -> Optional[str]:
        """คืน id กิจกรรมที่กำลังแสดง"""
        return self.rail.current_activity()

    def workspace_widget(self) -> Optional[QWidget]:
        return self._workspace_widget

    def inspector_widget(self) -> Optional[QWidget]:
        return self._inspector_widget

    def command_palette(self) -> Optional[QWidget]:
        return self._command_palette

    def _on_activity_changed(self, activity_id: str) -> None:
        index = self._context_index.get(activity_id)
        if index is not None:
            self.context_stack.setCurrentIndex(index)
            if self.rail.isHidden():
                return
            # สลับไปโมดูลอื่นขณะแผงถูกยุบอยู่ → กางแผงกลับมาให้
            if self._context_pages and self.context_stack.isHidden():
                self.context_stack.show()

    def _toggle_context_panel(self, _activity_id: str = "") -> None:
        """ยุบ/กางแผง context (rail ยังอยู่ให้กดเรียกกลับ)"""
        if not self._context_pages:
            return
        self.context_stack.setVisible(self.context_stack.isHidden())
