# -*- coding: utf-8 -*-
"""Dialog for entering one or more equations to plot."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)


class EquationPlotDialog(QDialog):
    """Dialog collecting expressions, domain, parameters, and plot options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equation Plotter (Desmos-like)")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Enter expressions (one line = one plot):"))
        self.expr_edit = QTextEdit(self)
        self.expr_edit.setPlaceholderText(
            "Examples:\n"
            "sin(2*pi*x) + a*x**2\n"
            "exp(-x)*cos(5*x)"
        )
        self.expr_edit.setFixedHeight(140)
        layout.addWidget(self.expr_edit)

        form = QFormLayout()
        self.xmin = QDoubleSpinBox()
        self.xmin.setRange(-1e9, 1e9)
        self.xmin.setValue(-10.0)
        form.addRow("x_min:", self.xmin)

        self.xmax = QDoubleSpinBox()
        self.xmax.setRange(-1e9, 1e9)
        self.xmax.setValue(10.0)
        form.addRow("x_max:", self.xmax)

        self.npoints = QSpinBox()
        self.npoints.setRange(10, 2_000_000)
        self.npoints.setValue(2000)
        form.addRow("Points:", self.npoints)
        layout.addLayout(form)

        layout.addWidget(QLabel("Parameters (e.g. a=1, b=0.5):"))
        self.params_edit = QLineEdit(self)
        self.params_edit.setPlaceholderText("a=1, b=0.5")
        layout.addWidget(self.params_edit)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Y scale:"))
        self.y_scale = QComboBox()
        self.y_scale.addItems(["linear", "log"])
        scale_row.addWidget(self.y_scale)
        scale_row.addStretch(1)
        layout.addLayout(scale_row)

        self.overlay_chk = QCheckBox("Plot over existing graph (do not clear axes)")
        self.overlay_chk.setChecked(True)
        layout.addWidget(self.overlay_chk)

        btn_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok = QPushButton("Plot")
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

    def get_values(self) -> dict:
        """Return dialog values as a dictionary."""
        expressions = [
            line.strip() for line in self.expr_edit.toPlainText().splitlines() if line.strip()
        ]
        return {
            "expressions": expressions,
            "x_min": float(self.xmin.value()),
            "x_max": float(self.xmax.value()),
            "n_points": int(self.npoints.value()),
            "params": self.params_edit.text(),
            "y_scale": self.y_scale.currentText(),
            "overlay": self.overlay_chk.isChecked(),
        }