"""Electrochemistry module context panel."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ElectrochemistryPanel(QWidget):
    cv_requested = Signal()
    randles_requested = Signal()
    tafel_requested = Signal()
    gcd_requested = Signal()
    eis_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ElectrochemistryPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Electrochemistry", self)
        title.setObjectName("ElectrochemistryTitle")
        layout.addWidget(title)

        hint = QLabel("Use the active Book, then run a domain analysis.", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.btn_cv = QPushButton("CV Peak Metrics...", self)
        self.btn_cv.setToolTip("Oxidation/reduction peak current, peak potential, and delta Ep")
        self.btn_randles = QPushButton("Randles-Sevcik + ECSA...", self)
        self.btn_randles.setToolTip("Fit ip vs sqrt(scan rate), then estimate ECSA")
        self.btn_tafel = QPushButton("Tafel Analysis...", self)
        self.btn_tafel.setToolTip("Fit overpotential vs log10 current")
        self.btn_gcd = QPushButton("GCD / Supercapacitor Metrics...", self)
        self.btn_gcd.setToolTip("Capacitance, specific capacitance, energy, and power")
        self.btn_eis = QPushButton("EIS Nyquist / Bode...", self)
        self.btn_eis.setToolTip("Estimate Rs/Rct and plot Nyquist plus Bode views")

        for btn in (self.btn_cv, self.btn_randles, self.btn_tafel, self.btn_gcd, self.btn_eis):
            btn.setMinimumHeight(34)
            layout.addWidget(btn)
        layout.addStretch(1)

        self.btn_cv.clicked.connect(self.cv_requested.emit)
        self.btn_randles.clicked.connect(self.randles_requested.emit)
        self.btn_tafel.clicked.connect(self.tafel_requested.emit)
        self.btn_gcd.clicked.connect(self.gcd_requested.emit)
        self.btn_eis.clicked.connect(self.eis_requested.emit)

        self.setStyleSheet(
            """
            #ElectrochemistryTitle { font-size: 13pt; font-weight: 600; color: #e6e6e6; }
            #ElectrochemistryPanel QLabel { color: #aab0b6; }
            #ElectrochemistryPanel QPushButton {
                text-align: left; padding: 6px 10px; border-radius: 8px;
                background: #262b33; border: 1px solid rgba(255,255,255,0.08);
                color: #e6e6e6;
            }
            #ElectrochemistryPanel QPushButton:hover {
                background: #2f3540; border-color: #6EE7B7;
            }
            """
        )
