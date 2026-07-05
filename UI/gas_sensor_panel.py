# UI/gas_sensor_panel.py
"""Gas Sensor module context panel — the first specialty module living in the
activity rail (UX_FLOW rule 5). Pure view: buttons emit signals; the
MainWindowGasSensorMixin owns the actual analysis flows."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class GasSensorPanel(QWidget):
    analyze_requested = Signal()
    cycles_requested = Signal()
    calibration_requested = Signal()
    dilution_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GasSensorPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Gas Sensor", self)
        title.setObjectName("GasSensorTitle")
        layout.addWidget(title)

        hint = QLabel("เปิดข้อมูลใน Book ที่ active แล้วเลือกเครื่องมือ", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ป้ายสั้นกันโดนตัดในแผงแคบ — ข้อความเต็มอยู่ใน tooltip
        self.btn_analyze = QPushButton("Response (t90)…", self)
        self.btn_analyze.setToolTip("วิเคราะห์ Response % / sensitivity / response-recovery time (t90)")
        self.btn_cycles = QPushButton("รอบเปิด-ปิดแก๊ส…", self)
        self.btn_cycles.setToolTip("ตรวจจับรอบเปิด-ปิดแก๊สอัตโนมัติ + response ต่อรอบ")
        self.btn_calibration = QPushButton("Calibration + LOD…", self)
        self.btn_calibration.setToolTip("ฟิต calibration curve (linear/power) + LOD/LOQ")
        self.btn_dilution = QPushButton("เจือจางแก๊ส (ppm)…", self)
        self.btn_dilution.setToolTip("คำนวณความเข้มข้นหลังเจือจางจากอัตราไหล (sccm)")
        for btn in (self.btn_analyze, self.btn_cycles,
                    self.btn_calibration, self.btn_dilution):
            btn.setMinimumHeight(34)
            layout.addWidget(btn)
        layout.addStretch(1)

        self.btn_analyze.clicked.connect(self.analyze_requested.emit)
        self.btn_cycles.clicked.connect(self.cycles_requested.emit)
        self.btn_calibration.clicked.connect(self.calibration_requested.emit)
        self.btn_dilution.clicked.connect(self.dilution_requested.emit)

        self.setStyleSheet(
            """
            #GasSensorTitle { font-size: 13pt; font-weight: 600; color: #e6e6e6; }
            #GasSensorPanel QLabel { color: #aab0b6; }
            #GasSensorPanel QPushButton {
                text-align: left; padding: 6px 10px; border-radius: 8px;
                background: #262b33; border: 1px solid rgba(255,255,255,0.08);
                color: #e6e6e6;
            }
            #GasSensorPanel QPushButton:hover {
                background: #2f3540; border-color: #4F9CF9;
            }
            """
        )
