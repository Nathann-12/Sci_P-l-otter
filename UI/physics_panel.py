"""Physics / General Lab module context panel."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class PhysicsPanel(QWidget):
    ohm_requested = Signal()
    rc_requested = Signal()
    pendulum_requested = Signal()
    uncertainty_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PhysicsPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Physics / General Lab", self)
        title.setObjectName("PhysicsTitle")
        layout.addWidget(title)

        hint = QLabel("Use active Books for classic lab fits and uncertainty calculations.", self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.btn_ohm = QPushButton("Ohm's Law Fit...", self)
        self.btn_ohm.setToolTip("Fit V = R I and report resistance/conductance")
        self.btn_rc = QPushButton("RC Time Constant...", self)
        self.btn_rc.setToolTip("Estimate tau from charge/discharge exponential data")
        self.btn_pendulum = QPushButton("Pendulum g Fit...", self)
        self.btn_pendulum.setToolTip("Fit T^2 vs L and estimate g")
        self.btn_uncertainty = QPushButton("Uncertainty Propagation...", self)
        self.btn_uncertainty.setToolTip("Propagate uncertainty for Q = c A^a B^b C^c")

        for btn in (self.btn_ohm, self.btn_rc, self.btn_pendulum, self.btn_uncertainty):
            btn.setMinimumHeight(34)
            layout.addWidget(btn)
        layout.addStretch(1)

        self.btn_ohm.clicked.connect(self.ohm_requested.emit)
        self.btn_rc.clicked.connect(self.rc_requested.emit)
        self.btn_pendulum.clicked.connect(self.pendulum_requested.emit)
        self.btn_uncertainty.clicked.connect(self.uncertainty_requested.emit)

        self.setStyleSheet(
            """
            #PhysicsTitle { font-size: 13pt; font-weight: 600; color: #e6e6e6; }
            #PhysicsPanel QLabel { color: #aab0b6; }
            #PhysicsPanel QPushButton {
                text-align: left; padding: 6px 10px; border-radius: 8px;
                background: #262b33; border: 1px solid rgba(255,255,255,0.08);
                color: #e6e6e6;
            }
            #PhysicsPanel QPushButton:hover {
                background: #2f3540; border-color: #93C5FD;
            }
            """
        )
