# -*- coding: utf-8 -*-
"""Dialog for entering one or more equations to plot."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class EquationPlotDialog(QDialog):
    """Dialog collecting expressions, domain, parameters, and plot options."""

    _PLACEHOLDER_2D = "e.g.  sin(2*pi*x) + a*x**2      (one expression per line)"
    _PLACEHOLDER_3D = "e.g.  sin(x) * cos(y)      (one surface per line)"

    # Quick-insert chips: (button label, text appended to the editor).
    _EXAMPLES_2D = (
        ("sin(x)", "sin(x)"),
        ("x**2", "x**2"),
        ("exp(-x)*cos(5*x)", "exp(-x)*cos(5*x)"),
        ("a*sin(b*x)", "a*sin(b*x)"),
    )
    _EXAMPLES_3D = (
        ("sin(x)*cos(y)", "sin(x)*cos(y)"),
        ("x**2 + y**2", "x**2 + y**2"),
        ("sin(sqrt(x**2+y**2))", "sin(sqrt(x**2+y**2))"),
    )

    _REFERENCE = (
        "Functions: sin cos tan exp log log10 sqrt abs floor ceil min max where  •  "
        "Constants: pi e  •  Variable: x  •  Use a, b… as parameters (set below)"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Equation Plotter (Desmos-like)")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- mode ---------------------------------------------------------
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Plot mode:"))
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("2D: y = f(x)", userData="2d")
        self.mode_combo.addItem("3D: z = f(x, y)", userData="3d_surface")
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        # --- expressions --------------------------------------------------
        self.expr_label = QLabel("Enter expressions (one line = one plot):")
        layout.addWidget(self.expr_label)
        self.expr_edit = QTextEdit(self)
        self.expr_edit.setPlaceholderText(self._PLACEHOLDER_2D)
        self.expr_edit.setMinimumHeight(96)
        self.expr_edit.setAcceptRichText(False)
        layout.addWidget(self.expr_edit)

        # Quick-insert example chips
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips_row.addWidget(QLabel("Quick insert:"))
        self._chip_container = QWidget(self)
        self._chip_layout = QHBoxLayout(self._chip_container)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(6)
        chips_row.addWidget(self._chip_container)
        chips_row.addStretch(1)
        layout.addLayout(chips_row)

        # Function / variable reference
        self.ref_label = QLabel(self._REFERENCE)
        self.ref_label.setWordWrap(True)
        self.ref_label.setObjectName("equationReference")
        self.ref_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        layout.addWidget(self.ref_label)

        # --- domain -------------------------------------------------------
        domain_box = QGroupBox("Domain", self)
        domain_grid = QGridLayout(domain_box)
        domain_grid.setHorizontalSpacing(10)
        self.xmin = self._make_spin(-10.0)
        self.xmax = self._make_spin(10.0)
        self.npoints = QSpinBox()
        self.npoints.setRange(10, 2_000_000)
        self.npoints.setValue(2000)
        domain_grid.addWidget(QLabel("X min:"), 0, 0)
        domain_grid.addWidget(self.xmin, 0, 1)
        domain_grid.addWidget(QLabel("X max:"), 0, 2)
        domain_grid.addWidget(self.xmax, 0, 3)
        domain_grid.addWidget(QLabel("Points:"), 0, 4)
        domain_grid.addWidget(self.npoints, 0, 5)

        # Surface (3D) domain row — lives in the same grid, hidden in 2D.
        self.ymin = self._make_spin(-10.0)
        self.ymax = self._make_spin(10.0)
        self.nypoints = QSpinBox()
        self.nypoints.setRange(10, 2_000_000)
        self.nypoints.setValue(200)
        self._ylabel_min = QLabel("Y min:")
        self._ylabel_max = QLabel("Y max:")
        self._ylabel_pts = QLabel("Y points:")
        domain_grid.addWidget(self._ylabel_min, 1, 0)
        domain_grid.addWidget(self.ymin, 1, 1)
        domain_grid.addWidget(self._ylabel_max, 1, 2)
        domain_grid.addWidget(self.ymax, 1, 3)
        domain_grid.addWidget(self._ylabel_pts, 1, 4)
        domain_grid.addWidget(self.nypoints, 1, 5)
        layout.addWidget(domain_box)

        # --- options ------------------------------------------------------
        options_box = QGroupBox("Options", self)
        options_form = QFormLayout(options_box)
        self.params_edit = QLineEdit(self)
        self.params_edit.setPlaceholderText("a=1, b=0.5")
        options_form.addRow("Parameters:", self.params_edit)

        self.y_scale = QComboBox()
        self.y_scale.addItems(["linear", "log"])
        options_form.addRow("Y scale:", self.y_scale)

        self.wireframe_chk = QCheckBox("Show wireframe (faster for 3D)")
        options_form.addRow("", self.wireframe_chk)

        self.overlay_chk = QCheckBox("Plot over existing graph (do not clear axes)")
        self.overlay_chk.setChecked(True)
        options_form.addRow("", self.overlay_chk)
        layout.addWidget(options_box)

        # --- footer: hint + buttons --------------------------------------
        btn_row = QHBoxLayout()
        self._hint_label = QLabel("Tip: press Ctrl+Enter to plot")
        self._hint_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        btn_row.addWidget(self._hint_label)
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok = QPushButton("Plot")
        self.btn_ok.setObjectName("equationPlotButton")
        self.btn_ok.setDefault(True)
        self.btn_ok.setAutoDefault(True)
        self.btn_ok.setStyleSheet(
            "QPushButton#equationPlotButton{background:#4F9CF9;color:#ffffff;"
            "font-weight:600;padding:6px 20px;border-radius:4px;}"
            "QPushButton#equationPlotButton:hover{background:#5aa6ff;}"
            "QPushButton#equationPlotButton:disabled{background:#3a3f44;color:#7d848c;}"
        )
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)
        self.mode_combo.currentIndexChanged.connect(self._update_mode)
        self.expr_edit.textChanged.connect(self._update_ok_enabled)

        # Ctrl+Enter plots (plain Enter adds a newline in the editor).
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(self._accept_if_ready)

        self._update_mode()
        self._update_ok_enabled()

    # ------------------------------------------------------------------ helpers
    def _make_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setValue(value)
        spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return spin

    def _rebuild_chips(self, examples) -> None:
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label, text in examples:
            chip = QPushButton(label, self._chip_container)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFlat(True)
            chip.setStyleSheet(
                "QPushButton{border:1px solid #3a3f44;border-radius:10px;"
                "padding:2px 10px;color:#cfd3d6;background:transparent;}"
                "QPushButton:hover{border-color:#4F9CF9;color:#ffffff;}"
            )
            chip.clicked.connect(lambda _=False, t=text: self._insert_example(t))
            self._chip_layout.addWidget(chip)

    def _insert_example(self, text: str) -> None:
        current = self.expr_edit.toPlainText()
        if current.strip() and not current.endswith("\n"):
            current += "\n"
        self.expr_edit.setPlainText(current + text)
        self.expr_edit.setFocus()

    def _accept_if_ready(self) -> None:
        if self.btn_ok.isEnabled():
            self.accept()

    def _update_ok_enabled(self) -> None:
        has_expr = any(
            line.strip() for line in self.expr_edit.toPlainText().splitlines()
        )
        self.btn_ok.setEnabled(has_expr)

    def _update_mode(self) -> None:
        mode = self.mode_combo.currentData()
        surface = mode == "3d_surface"
        for widget in (self._ylabel_min, self.ymin, self._ylabel_max, self.ymax,
                       self._ylabel_pts, self.nypoints):
            widget.setVisible(surface)
        self.wireframe_chk.setVisible(surface)
        self.wireframe_chk.setEnabled(surface)
        if not surface:
            self.wireframe_chk.setChecked(False)
        self.y_scale.setEnabled(not surface)
        if surface:
            self.expr_label.setText(
                "Enter surface expressions z = f(x, y) (one line = one surface):")
            self.expr_edit.setPlaceholderText(self._PLACEHOLDER_3D)
            self._rebuild_chips(self._EXAMPLES_3D)
        else:
            self.expr_label.setText("Enter expressions (one line = one plot):")
            self.expr_edit.setPlaceholderText(self._PLACEHOLDER_2D)
            self._rebuild_chips(self._EXAMPLES_2D)

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
