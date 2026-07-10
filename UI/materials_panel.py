"""Materials Science module context panel."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class MaterialsPanel(QWidget):
    conductivity_requested = Signal()
    arrhenius_requested = Signal()
    thermal_requested = Signal()
    ranking_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MaterialsPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Materials Science", self)
        title.setObjectName("MaterialsTitle")
        layout.addWidget(title)

        hint = QLabel("Analyze active Books for transport, activation energy, thermal transitions, and sample ranking.", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.btn_conductivity = QPushButton("Conductivity / Resistivity...", self)
        self.btn_conductivity.setToolTip("Fit I-V resistance and compute resistivity/conductivity from geometry")
        self.btn_arrhenius = QPushButton("Arrhenius Activation Energy...", self)
        self.btn_arrhenius.setToolTip("Fit ln(sigma) vs 1/T and estimate Ea")
        self.btn_thermal = QPushButton("TGA / DSC Thermal Metrics...", self)
        self.btn_thermal.setToolTip("Find onset and derivative peak temperature")
        self.btn_ranking = QPushButton("Rank Samples...", self)
        self.btn_ranking.setToolTip("Rank samples by a numeric material property")

        for btn in (self.btn_conductivity, self.btn_arrhenius, self.btn_thermal, self.btn_ranking):
            btn.setMinimumHeight(34)
            layout.addWidget(btn)
        layout.addStretch(1)

        self.btn_conductivity.clicked.connect(self.conductivity_requested.emit)
        self.btn_arrhenius.clicked.connect(self.arrhenius_requested.emit)
        self.btn_thermal.clicked.connect(self.thermal_requested.emit)
        self.btn_ranking.clicked.connect(self.ranking_requested.emit)

        self.setStyleSheet(
            """
            #MaterialsTitle { font-size: 13pt; font-weight: 600; color: #e6e6e6; }
            #MaterialsPanel QLabel { color: #aab0b6; }
            #MaterialsPanel QPushButton {
                text-align: left; padding: 6px 10px; border-radius: 8px;
                background: #262b33; border: 1px solid rgba(255,255,255,0.08);
                color: #e6e6e6;
            }
            #MaterialsPanel QPushButton:hover {
                background: #2f3540; border-color: #A3E635;
            }
            """
        )
