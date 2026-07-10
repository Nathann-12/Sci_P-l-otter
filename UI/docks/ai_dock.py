# UI/docks/ai_dock.py
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class AiAssistantDock(QWidget):
    """โครง UI ของผู้ช่วย AI — transcript อ่านอย่างเดียว + ช่องพิมพ์ + ปุ่มส่ง

    ยังไม่มี backend AI จริง เป็นแค่เปลือก UI: เมื่อส่งข้อความที่ไม่ว่าง จะ echo
    บรรทัดของผู้ใช้ลง transcript แล้วส่งสัญญาณ ``message_submitted``
    """

    message_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AiAssistantDock")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.transcript = QTextEdit(self)
        self.transcript.setObjectName("AiTranscript")
        self.transcript.setReadOnly(True)
        # Low minimum so the bottom dock can stay compact; content scrolls.
        self.transcript.setMinimumHeight(36)
        layout.addWidget(self.transcript, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self.input_edit = QLineEdit(self)
        self.input_edit.setObjectName("AiInput")
        self.input_edit.setPlaceholderText("Ask AI or type a command...")
        input_row.addWidget(self.input_edit, 1)

        self.send_button = QPushButton("Send", self)
        self.send_button.setObjectName("AiSendButton")
        input_row.addWidget(self.send_button)

        layout.addLayout(input_row)

        self.send_button.clicked.connect(self._submit)
        self.input_edit.returnPressed.connect(self._submit)

    def _submit(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.append_message("You", text)
        self.input_edit.clear()
        self.message_submitted.emit(text)

    def append_message(self, sender: str, text: str) -> None:
        """เพิ่มข้อความหนึ่งบรรทัดลง transcript (ใช้ได้ทั้งฝั่งผู้ใช้และ AI)"""
        self.transcript.append(f"{sender}: {text}")

    def transcript_text(self) -> str:
        """คืนข้อความทั้งหมดใน transcript (มีไว้ให้เทสต์ตรวจ)"""
        return self.transcript.toPlainText()

    def clear(self) -> None:
        """ล้าง transcript"""
        self.transcript.clear()
