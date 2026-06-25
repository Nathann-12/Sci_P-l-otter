# UI/shell/app_shell.py
from __future__ import annotations

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


class AppShell(QWidget):
    """โครงหลัก (shell) ของ Research OS — เป็น layout ล้วน ไม่ผูกกับ MainWindow

    การจัดวาง: ActivityRail (ซ้าย) | context stack | workspace กลาง | inspector ขวา
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
        self._command_palette: Optional[QWidget] = None

        # --- left: activity rail ---
        self.rail = ActivityRail(self)
        self.rail.activity_changed.connect(self._on_activity_changed)

        # --- context stack (เปลี่ยนตามกิจกรรมที่เลือกใน rail) ---
        self.context_stack = QStackedWidget(self)
        self.context_stack.setObjectName("ContextStack")

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

        # --- vertical splitter: (top row) over (bottom dock) ---
        top_splitter = QSplitter(Qt.Horizontal, self)
        top_splitter.setObjectName("ShellTopSplitter")
        top_splitter.addWidget(self.context_stack)
        top_splitter.addWidget(self.workspace_container)
        top_splitter.addWidget(self.inspector_container)
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setStretchFactor(2, 0)
        self._top_splitter = top_splitter

        main_splitter = QSplitter(Qt.Vertical, self)
        main_splitter.setObjectName("ShellMainSplitter")
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self.dock_tabs)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        self._main_splitter = main_splitter

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.rail)
        root.addWidget(main_splitter, 1)

    # ------------------------------------------------------------------
    # Injection API
    # ------------------------------------------------------------------
    def register_context(self, activity_id: str, label: str, context_widget: QWidget, icon=None) -> None:
        """เพิ่มกิจกรรมใน rail + หน้า context ที่ผูกกัน เปลี่ยน rail แล้วหน้านี้จะโชว์"""
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

    def add_dock(self, title: str, widget: QWidget) -> int:
        """เพิ่ม tab ใหม่ในพื้นที่ dock ด้านล่าง คืน index ของ tab"""
        index = self.dock_tabs.addTab(widget, title)
        self._docks[title] = widget
        return index

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
