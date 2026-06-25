# widgets/command_palette.py
from __future__ import annotations

import logging
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

Command = Tuple[str, Callable[[], None]]


class CommandPalette(QDialog):
    """กล่องคำสั่งแบบ Ctrl+K — ช่องค้นหาด้านบน + รายการคำสั่งด้านล่าง

    พิมพ์เพื่อกรองรายการ (substring แบบไม่สนตัวพิมพ์ใหญ่เล็ก)
    Enter หรือ double-click เพื่อรันคำสั่งที่เลือกแล้วปิด, Esc เพื่อปิด
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CommandPalette")
        self.setWindowTitle("Command Palette")
        self.setModal(False)

        self._commands: List[Command] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("CommandPaletteSearch")
        self.search_edit.setPlaceholderText("พิมพ์เพื่อค้นหาคำสั่ง...")
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("CommandPaletteList")
        layout.addWidget(self.list_widget)

        self.search_edit.textChanged.connect(self._apply_filter)
        self.search_edit.returnPressed.connect(self._run_selected)
        self.list_widget.itemActivated.connect(self._run_item)
        self.list_widget.itemDoubleClicked.connect(self._run_item)

        self.resize(420, 320)

    def set_commands(self, commands: List[Command]) -> None:
        """ตั้งรายการคำสั่ง — แต่ละรายการเป็น tuple ``(label, callable)``"""
        self._commands = list(commands)
        self.search_edit.clear()
        self._apply_filter("")

    def commands(self) -> List[Command]:
        """คืนรายการคำสั่งทั้งหมดที่ตั้งไว้"""
        return list(self._commands)

    def visible_labels(self) -> List[str]:
        """คืน label ของรายการที่กำลังแสดง (หลังกรอง) — มีไว้ให้เทสต์ตรวจ"""
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

    def _apply_filter(self, text: str = "") -> None:
        needle = (text or self.search_edit.text()).strip().lower()
        self.list_widget.clear()
        for index, (label, _callback) in enumerate(self._commands):
            if needle and needle not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, index)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _run_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item is None and self.list_widget.count() > 0:
            item = self.list_widget.item(0)
        if item is not None:
            self._run_item(item)

    def _run_item(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        index = item.data(Qt.UserRole)
        if index is None or index < 0 or index >= len(self._commands):
            return
        _label, callback = self._commands[index]
        self.accept()
        if callable(callback):
            try:
                callback()
            except Exception:
                logger.debug("Command palette callback failed", exc_info=True)

    def open_palette(self) -> None:
        """แสดง palette แบบ non-modal พร้อมโฟกัสที่ช่องค้นหา"""
        self.search_edit.clear()
        self._apply_filter("")
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_edit.setFocus()
