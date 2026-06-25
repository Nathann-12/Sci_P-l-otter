# UI/docks/log_dock.py
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class OperationLogDock(QWidget):
    """โครง UI ของ operation log — รายการ log + ปุ่ม "รันซ้ำล่าสุด"

    เก็บรายการการทำงานเพื่อ reproducibility ปุ่มรันซ้ำส่งสัญญาณ ``rerun_requested``
    (ยังเป็น stub — ตัว dock ไม่รันงานเอง)
    """

    rerun_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("OperationLogDock")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.log_list = QListWidget(self)
        self.log_list.setObjectName("OperationLogList")
        layout.addWidget(self.log_list, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)
        button_row.addStretch()

        self.rerun_button = QPushButton("รันซ้ำล่าสุด", self)
        self.rerun_button.setObjectName("RerunButton")
        button_row.addWidget(self.rerun_button)

        layout.addLayout(button_row)

        self.rerun_button.clicked.connect(self.rerun_requested.emit)

    def add_entry(self, text: str) -> None:
        """เพิ่มรายการ log หนึ่งบรรทัด แล้วเลื่อนไปบรรทัดล่าสุด"""
        self.log_list.addItem(text)
        self.log_list.setCurrentRow(self.log_list.count() - 1)
        self.log_list.scrollToBottom()

    def entries(self) -> list[str]:
        """คืนรายการ log ทั้งหมดเป็น list ของ str"""
        return [self.log_list.item(i).text() for i in range(self.log_list.count())]

    def clear(self) -> None:
        """ล้าง log ทั้งหมด"""
        self.log_list.clear()
