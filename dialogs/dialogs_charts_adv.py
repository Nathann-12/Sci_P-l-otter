# -*- coding: utf-8 -*-
"""
Stub module dialogs.dialogs_charts_adv
ไฟล์นี้เป็น stub ขนาดเล็กสำหรับ ChartOptionsDialogPro
เพื่อให้การ import จาก main.py ผ่านในระหว่างการพัฒนา
และไม่ล้มเหลวถ้า PySide6 ยังไม่ได้ติดตั้ง
"""
from __future__ import annotations

try:
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
    from PySide6.QtCore import Qt
except Exception:
    # ถ้า PySide6 ไม่พร้อม ให้สร้าง fallback แบบง่าย
    QDialog = object
    QVBoxLayout = object
    QLabel = object
    QPushButton = object
    Qt = None


class ChartOptionsDialogPro(QDialog):
    """Minimal stub for ChartOptionsDialogPro

    ใช้เพื่อให้ main.py import ได้และเรียกสร้าง dialog แบบพื้นฐานได้
    """

    def __init__(self, kind="line", get_df=None, apply_to_main=None, parent=None):
        # พยายามเรียก QDialog.__init__ ถ้าเป็นไปได้
        try:
            super(ChartOptionsDialogPro, self).__init__(parent)
        except Exception:
            # fallback เมื่อ QDialog เป็น object placeholder
            pass

        self.kind = kind
        self.get_df = get_df
        self.apply_to_main = apply_to_main

        # สร้าง UI อย่างง่าย (ไม่ใช่สิ่งจำเป็น แต่ถ้า PySide6 พร้อมจะทำงาน)
        try:
            self.setWindowTitle(f"Chart Options ({kind})")
            if Qt is not None:
                self.setWindowModality(Qt.NonModal)
            layout = QVBoxLayout(self)
            label = QLabel("Stub dialog for ChartOptionsDialogPro.\nไฟล์นี้เป็นตัวอย่างเล็ก ๆ เพื่อให้โปรแกรมรันได้", self)
            label.setWordWrap(True)
            layout.addWidget(label)
            btn = QPushButton("Close", self)
            btn.clicked.connect(self.close)
            layout.addWidget(btn)
        except Exception:
            # ถ้า element ใดๆ ขาด จะไม่ทำให้โปรแกรมล่ม
            pass

    def show_stub_info(self):
        """Optional helper: return a short description (useful for tests)."""
        return f"ChartOptionsDialogPro stub (kind={self.kind})"
