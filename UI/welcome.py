# UI/welcome.py
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.title_label = QLabel("ลากไฟล์มาวาง หรือเปิดไฟล์", self)
        self.title_label.setObjectName("WelcomeTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        title_font = self.title_label.font()
        title_font.setPointSize(max(title_font.pointSize() + 6, 16))
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("เริ่มต้นวิเคราะห์ข้อมูลของคุณได้เลย", self)
        self.subtitle_label.setObjectName("WelcomeSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subtitle_label)

        self.open_button = QPushButton("เปิดไฟล์", self)
        self.open_button.setObjectName("WelcomeOpenButton")
        layout.addWidget(self.open_button, 0, Qt.AlignCenter)

        self.recent_label = QLabel("ไฟล์ล่าสุด", self)
        self.recent_label.setObjectName("WelcomeRecentLabel")
        layout.addWidget(self.recent_label)

        self.recent_list = QListWidget(self)
        self.recent_list.setObjectName("WelcomeRecentList")
        layout.addWidget(self.recent_list, 1)

        self.open_button.clicked.connect(self.open_requested.emit)
        self.recent_list.itemDoubleClicked.connect(self._on_recent_activated)

    def set_recent_files(self, paths: List[str]) -> None:
        """ตั้งรายการไฟล์ล่าสุดที่แสดง (แทนที่ของเดิมทั้งหมด)"""
        self.recent_list.clear()
        for path in paths:
            self.recent_list.addItem(path)

    def recent_files(self) -> List[str]:
        """คืนรายการไฟล์ล่าสุดที่กำลังแสดง"""
        return [self.recent_list.item(i).text() for i in range(self.recent_list.count())]

    def _on_recent_activated(self, item) -> None:
        if item is not None:
            self.recent_file_activated.emit(item.text())
