# UI/welcome.py
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class WelcomeWidget(QWidget):
    """หน้าจอต้อนรับ (empty state) ที่เป็นมิตร — ชื่อ + ปุ่มเปิดไฟล์ + ไฟล์ล่าสุด

    ปุ่ม "เปิดไฟล์" ส่งสัญญาณ ``open_requested`` ส่วนรายการไฟล์ล่าสุดส่ง
    ``recent_file_activated`` พร้อม path เมื่อ double-click
    """

    open_requested = Signal()
    recent_file_activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomeWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        # Center the whole block vertically so it reads as a calm empty-state,
        # not a form crammed against the top.
        layout.setAlignment(Qt.AlignCenter)

        layout.addStretch(2)

        # --- friendly app glyph above the title (optional, best-effort) ---
        self.glyph_label = QLabel(self)
        self.glyph_label.setObjectName("WelcomeGlyph")
        self.glyph_label.setAlignment(Qt.AlignCenter)
        pixmap = self._load_glyph()
        if pixmap is not None and not pixmap.isNull():
            self.glyph_label.setPixmap(pixmap)
            layout.addWidget(self.glyph_label, 0, Qt.AlignHCenter)
            layout.addSpacing(20)
        else:
            self.glyph_label.hide()

        # --- title: large heading, no border/box ---
        self.title_label = QLabel("ลากไฟล์มาวาง หรือเปิดไฟล์", self)
        self.title_label.setObjectName("WelcomeTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        layout.addSpacing(8)

        # --- subtitle: muted, smaller ---
        self.subtitle_label = QLabel("เริ่มต้นวิเคราะห์ข้อมูลของคุณได้เลย", self)
        self.subtitle_label.setObjectName("WelcomeSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subtitle_label)

        layout.addSpacing(28)

        # --- primary accent button ---
        self.open_button = QPushButton("เปิดไฟล์", self)
        self.open_button.setObjectName("WelcomeOpenButton")
        self.open_button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.open_button, 0, Qt.AlignCenter)

        layout.addSpacing(36)

        # --- recent files section ---
        self.recent_label = QLabel("ไฟล์ล่าสุด", self)
        self.recent_label.setObjectName("WelcomeRecentLabel")
        self.recent_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.recent_label, 0, Qt.AlignHCenter)

        layout.addSpacing(8)

        self.recent_list = QListWidget(self)
        self.recent_list.setObjectName("WelcomeRecentList")
        # A friendly placeholder shows through when the list is empty so the
        # area never reads as a sad black void.
        try:
            self.recent_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        except Exception:
            pass
        layout.addWidget(self.recent_list, 0, Qt.AlignHCenter)

        # Empty-state message overlaid on the recent list
        self.recent_empty_label = QLabel("ยังไม่มีไฟล์ล่าสุด", self.recent_list)
        self.recent_empty_label.setObjectName("WelcomeRecentEmpty")
        self.recent_empty_label.setAlignment(Qt.AlignCenter)

        layout.addStretch(3)

        self.open_button.clicked.connect(self.open_requested.emit)
        self.recent_list.itemDoubleClicked.connect(self._on_recent_activated)

        self._update_recent_empty_state()

    # ------------------------------------------------------------------
    def _load_glyph(self) -> QPixmap | None:
        """Best-effort load of an app glyph from assets for the welcome header."""
        try:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidates = [
                os.path.join(base, "assets", "icons", "icon_app.png"),
                os.path.join(base, "logo", "logo.png"),
            ]
            for path in candidates:
                if os.path.isfile(path):
                    pm = QPixmap(path)
                    if not pm.isNull():
                        return pm.scaled(
                            QSize(72, 72),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
        except Exception:
            return None
        return None

    def set_recent_files(self, paths: List[str]) -> None:
        """ตั้งรายการไฟล์ล่าสุดที่แสดง (แทนที่ของเดิมทั้งหมด)"""
        self.recent_list.clear()
        for path in paths:
            self.recent_list.addItem(path)
        self._update_recent_empty_state()

    def recent_files(self) -> List[str]:
        """คืนรายการไฟล์ล่าสุดที่กำลังแสดง"""
        return [self.recent_list.item(i).text() for i in range(self.recent_list.count())]

    def _update_recent_empty_state(self) -> None:
        """Show the placeholder when there are no recent files; hide otherwise."""
        empty = self.recent_list.count() == 0
        self.recent_empty_label.setVisible(empty)
        if empty:
            self.recent_empty_label.resize(self.recent_list.viewport().size())
            self.recent_empty_label.move(0, 0)

    def resizeEvent(self, event):  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        # Keep the empty-state label centered over the recent list.
        if self.recent_empty_label.isVisible():
            self.recent_empty_label.resize(self.recent_list.viewport().size())

    def _on_recent_activated(self, item) -> None:
        if item is not None:
            self.recent_file_activated.emit(item.text())
