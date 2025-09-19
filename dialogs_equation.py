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
    QWidget,
)


class EquationPlotDialog(QDialog):
    """Dialog collecting expressions, domain, parameters, and plot options."""

    _PLACEHOLDER_2D = (
        "Examples:\n"
        "sin(2*pi*x) + a*x**2\n"
        "exp(-x)*cos(5*x)\n"
        "Tips: use y = ... (or x = ...) form\n"
    )
    _PLACEHOLDER_3D = (
        "Examples:\n"
        "sin(x) * cos(y)\n"
        "x**2 + y**2\n"
        "Tips: use z = f(x, y) form\n"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equation Plotter (Desmos-like)")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Plot mode:"))
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("2D: y = f(x)", userData="2d")
        self.mode_combo.addItem("3D: z = f(x, y)", userData="3d_surface")
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.expr_label = QLabel("Enter expressions (one line = one plot):")
        layout.addWidget(self.expr_label)
        self.expr_edit = QTextEdit(self)
        self.expr_edit.setPlaceholderText(self._PLACEHOLDER_2D)
        self.expr_edit.setFixedHeight(160)
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

        # Surface (3D) domain options
        self.surface_widget = QWidget(self)
        surface_form = QFormLayout(self.surface_widget)
        self.ymin = QDoubleSpinBox()
        self.ymin.setRange(-1e9, 1e9)
        self.ymin.setValue(-10.0)
        surface_form.addRow("y_min:", self.ymin)

        self.ymax = QDoubleSpinBox()
        self.ymax.setRange(-1e9, 1e9)
        self.ymax.setValue(10.0)
        surface_form.addRow("y_max:", self.ymax)

        self.nypoints = QSpinBox()
        self.nypoints.setRange(10, 2_000_000)
        self.nypoints.setValue(200)
        surface_form.addRow("Y points:", self.nypoints)
        layout.addWidget(self.surface_widget)

        self.wireframe_chk = QCheckBox("Show wireframe (faster for 3D)")
        self.wireframe_chk.setChecked(False)
        layout.addWidget(self.wireframe_chk)

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
        self.mode_combo.currentIndexChanged.connect(self._update_mode)

        self._update_mode()

    def _update_mode(self) -> None:
        mode = self.mode_combo.currentData()
        surface = mode == "3d_surface"
        self.surface_widget.setVisible(surface)
        self.wireframe_chk.setVisible(surface)
        self.wireframe_chk.setEnabled(surface)
        if not surface:
            self.wireframe_chk.setChecked(False)
        self.y_scale.setEnabled(not surface)
        if surface:
            self.expr_label.setText("Enter surface expressions z = f(x, y) (one line = one surface):")
            self.expr_edit.setPlaceholderText(self._PLACEHOLDER_3D)
        else:
            self.expr_label.setText("Enter expressions (one line = one plot):")
            self.expr_edit.setPlaceholderText(self._PLACEHOLDER_2D)

    def get_values(self) -> dict:
        """Return dialog values as a dictionary."""
        expressions = [
            line.strip() for line in self.expr_edit.toPlainText().splitlines() if line.strip()
        ]
        mode = self.mode_combo.currentData()
        values = {
            "wireframe": False,
            "mode": mode,
            "expressions": expressions,
            "x_min": float(self.xmin.value()),
            "x_max": float(self.xmax.value()),
            "n_points": int(self.npoints.value()),
            "params": self.params_edit.text(),
            "y_scale": self.y_scale.currentText(),
            "overlay": self.overlay_chk.isChecked(),
        }
        if mode == "3d_surface":
            values["wireframe"] = self.wireframe_chk.isChecked()
            values.update({
                "y_min": float(self.ymin.value()),
                "y_max": float(self.ymax.value()),
                "n_y_points": int(self.nypoints.value()),
            })
        else:
            values["wireframe"] = False
            values.update({
                "y_min": None,
                "y_max": None,
                "n_y_points": None,
            })
        return values
