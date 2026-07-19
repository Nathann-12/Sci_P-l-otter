"""
2-Point Calibration Dialog
Provides an interface for calibrating raw values to true values.

Presentation is theme-neutral: it inherits the application's active theme
instead of hardcoding light colours, so it looks right in both dark and light
modes. The calibration maths is unchanged.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QDoubleSpinBox, QPushButton, QGroupBox, QFrame
)
from PySide6.QtCore import Qt, QLocale


class CalibrateDialog(QDialog):
    """Dialog for 2-point calibration (y_true = a·y_raw + b)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Force English locale for Arabic numerals
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))

        self.setWindowTitle("2-Point Calibration")
        self.setModal(True)
        self.resize(420, 340)

        # Calibration coefficients
        self.a = 1.0
        self.b = 0.0

        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Title
        title_label = QLabel("Enter two known points to derive the calibration line")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        f = title_label.font()
        f.setBold(True)
        title_label.setFont(f)
        layout.addWidget(title_label)

        # Calibration inputs
        calib_group = QGroupBox("Calibration Points")
        calib_layout = QFormLayout(calib_group)
        calib_layout.setSpacing(10)

        # Raw values
        self.raw1_spin = self._spin(0.0, " (raw)")
        self.raw2_spin = self._spin(100.0, " (raw)")
        # True values
        self.true1_spin = self._spin(0.0, " (true)")
        self.true2_spin = self._spin(100.0, " (true)")

        calib_layout.addRow("Raw #1:", self.raw1_spin)
        calib_layout.addRow("True #1:", self.true1_spin)
        calib_layout.addRow("Raw #2:", self.raw2_spin)
        calib_layout.addRow("True #2:", self.true2_spin)

        layout.addWidget(calib_group)

        # Compute button
        self.compute_btn = QPushButton("Compute a, b")
        layout.addWidget(self.compute_btn)

        # Results display
        results_group = QGroupBox("Results")
        results_layout = QFormLayout(results_group)
        results_layout.setSpacing(10)

        self.a_label = self._mono_label("1.000000")
        self.b_label = self._mono_label("0.000000")

        self.equation_label = QLabel("y_true = a × y_raw + b")
        self.equation_label.setAlignment(Qt.AlignCenter)
        ef = self.equation_label.font()
        ef.setItalic(True)
        self.equation_label.setFont(ef)

        results_layout.addRow("Coefficient a:", self.a_label)
        results_layout.addRow("Coefficient b:", self.b_label)
        results_layout.addRow("", self.equation_label)

        layout.addWidget(results_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setDefault(True)
        self.ok_btn.setEnabled(False)  # Disabled until computed

        self.cancel_btn = QPushButton("Cancel")

        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _spin(self, value: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setDecimals(6)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _mono_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFrameStyle(QFrame.Box)
        mf = lbl.font()
        mf.setFamily("Consolas")
        mf.setStyleHint(mf.StyleHint.Monospace)
        lbl.setFont(mf)
        lbl.setMargin(6)
        return lbl

    def setup_connections(self):
        """Setup signal connections."""
        self.compute_btn.clicked.connect(self.compute_calibration)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        # Update results when values change
        self.raw1_spin.valueChanged.connect(self.update_preview)
        self.raw2_spin.valueChanged.connect(self.update_preview)
        self.true1_spin.valueChanged.connect(self.update_preview)
        self.true2_spin.valueChanged.connect(self.update_preview)

    def compute_calibration(self):
        """Compute calibration coefficients."""
        try:
            raw1 = self.raw1_spin.value()
            true1 = self.true1_spin.value()
            raw2 = self.raw2_spin.value()
            true2 = self.true2_spin.value()

            if raw1 == raw2:
                self.show_error("Raw values must be different for calibration")
                return

            # Calculate a and b for y_true = a * y_raw + b
            self.a = (true2 - true1) / (raw2 - raw1)
            self.b = true1 - self.a * raw1

            # Update display
            self.a_label.setText(f"{self.a:.6f}")
            self.b_label.setText(f"{self.b:.6f}")

            # Update equation
            if self.b >= 0:
                eq_text = f"y_true = {self.a:.4f} × y_raw + {self.b:.4f}"
            else:
                eq_text = f"y_true = {self.a:.4f} × y_raw - {abs(self.b):.4f}"
            self.equation_label.setText(eq_text)

            # Enable OK button + feedback
            self.ok_btn.setEnabled(True)
            self.compute_btn.setText("✓ Computed")

        except Exception as e:
            self.show_error(f"Error computing calibration: {str(e)}")

    def update_preview(self):
        """Reset state when any input changes; force recompute before OK."""
        self.compute_btn.setText("Compute a, b")
        self.ok_btn.setEnabled(False)

    def show_error(self, message: str):
        """Show an error message on the equation line."""
        self.equation_label.setText(f"⚠ {message}")

    def get_calibration(self) -> tuple:
        """Get calibration coefficients (a, b)."""
        return self.a, self.b


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = CalibrateDialog()
    dialog.show()
    sys.exit(app.exec())
