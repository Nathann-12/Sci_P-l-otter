"""Single-screen peak-analysis configuration dialog."""
from __future__ import annotations

from typing import Iterable

from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class PeakAnalyzerDialog(QDialog):
    def __init__(self, numeric_columns: Iterable[str], parent=None):
        super().__init__(parent)
        columns = [str(value) for value in numeric_columns]
        self.setWindowTitle("Peak Analyzer")
        self.resize(520, 560)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "One workflow estimates the baseline, detects candidate peaks, fits all peaks "
            "simultaneously, and reports center, height, FWHM, area, confidence intervals, and residuals."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        data_box = QGroupBox("Data")
        data_form = QFormLayout(data_box)
        self.x_combo = QComboBox()
        self.x_combo.addItems(columns)
        self.y_combo = QComboBox()
        self.y_combo.addItems(columns)
        if len(columns) > 1:
            self.y_combo.setCurrentIndex(1)
        data_form.addRow("X column:", self.x_combo)
        data_form.addRow("Y signal:", self.y_combo)
        self.sigma_combo = QComboBox()
        self.sigma_combo.addItem("None", None)
        for column in columns:
            self.sigma_combo.addItem(column, column)
        data_form.addRow("Sigma / uncertainty:", self.sigma_combo)
        self.absolute_sigma = QCheckBox("Treat sigma as absolute measurement uncertainty")
        self.absolute_sigma.setChecked(True)
        self.absolute_sigma.setEnabled(False)
        self.sigma_combo.currentIndexChanged.connect(
            lambda: self.absolute_sigma.setEnabled(self.sigma_combo.currentData() is not None)
        )
        data_form.addRow("Uncertainty meaning:", self.absolute_sigma)
        layout.addWidget(data_box)

        options_box = QGroupBox("Detection and fit")
        options = QFormLayout(options_box)
        self.model_combo = QComboBox()
        for name in ("gaussian", "lorentzian", "voigt"):
            self.model_combo.addItem(name.title(), name)
        options.addRow("Peak model:", self.model_combo)
        self.baseline_combo = QComboBox()
        for label, value in (
            ("Linear", "linear"), ("Asymmetric least squares (ALS)", "als"),
            ("Constant", "constant"), ("None", "none"),
        ):
            self.baseline_combo.addItem(label, value)
        self.baseline_combo.currentIndexChanged.connect(self._refresh_baseline_options)
        options.addRow("Baseline:", self.baseline_combo)
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("Positive peaks", "positive")
        self.direction_combo.addItem("Negative peaks", "negative")
        self.direction_combo.addItem("Both directions", "both")
        options.addRow("Direction:", self.direction_combo)
        self.prominence = QDoubleSpinBox()
        self.prominence.setRange(0.0, 1e15)
        self.prominence.setDecimals(8)
        self.prominence.setSpecialValueText("Automatic")
        options.addRow("Minimum prominence:", self.prominence)
        self.height = QDoubleSpinBox()
        self.height.setRange(0.0, 1e15)
        self.height.setDecimals(8)
        self.height.setSpecialValueText("Automatic")
        options.addRow("Minimum absolute height:", self.height)
        self.distance = QSpinBox()
        self.distance.setRange(0, 10_000_000)
        self.distance.setSpecialValueText("Automatic")
        options.addRow("Minimum distance (points):", self.distance)
        self.width = QDoubleSpinBox()
        self.width.setRange(0.0, 10_000_000.0)
        self.width.setDecimals(2)
        self.width.setSpecialValueText("Automatic")
        options.addRow("Minimum width (points):", self.width)
        self.max_peaks = QSpinBox()
        self.max_peaks.setRange(1, 200)
        self.max_peaks.setValue(20)
        options.addRow("Maximum peaks:", self.max_peaks)
        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(50.0, 99.99)
        self.confidence.setValue(95.0)
        self.confidence.setSuffix(" %")
        options.addRow("Confidence level:", self.confidence)
        self.als_lambda = QDoubleSpinBox()
        self.als_lambda.setRange(1.0, 1e14)
        self.als_lambda.setDecimals(1)
        self.als_lambda.setValue(1e5)
        options.addRow("ALS smoothness lambda:", self.als_lambda)
        self.als_p = QDoubleSpinBox()
        self.als_p.setRange(0.0001, 0.4999)
        self.als_p.setDecimals(4)
        self.als_p.setValue(0.01)
        options.addRow("ALS asymmetry p:", self.als_p)
        self.als_iterations = QSpinBox()
        self.als_iterations.setRange(1, 100)
        self.als_iterations.setValue(10)
        options.addRow("ALS iterations:", self.als_iterations)
        self.constant_quantile = QDoubleSpinBox()
        self.constant_quantile.setRange(0.0, 1.0)
        self.constant_quantile.setDecimals(3)
        self.constant_quantile.setValue(0.1)
        options.addRow("Constant baseline quantile:", self.constant_quantile)
        self._baseline_option_rows = (
            (options.labelForField(self.als_lambda), self.als_lambda, "als"),
            (options.labelForField(self.als_p), self.als_p, "als"),
            (options.labelForField(self.als_iterations), self.als_iterations, "als"),
            (options.labelForField(self.constant_quantile), self.constant_quantile, "constant"),
        )
        layout.addWidget(options_box)

        self.validation = QLabel("")
        self.validation.setStyleSheet("color:#e29b52")
        layout.addWidget(self.validation)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Analyze Peaks")
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.x_combo.currentTextChanged.connect(self._refresh_validation)
        self.y_combo.currentTextChanged.connect(self._refresh_validation)
        self.sigma_combo.currentIndexChanged.connect(self._refresh_validation)
        self._refresh_baseline_options()
        self._refresh_validation()

    def values(self) -> dict:
        return {
            "x": self.x_combo.currentText(),
            "y": self.y_combo.currentText(),
            "model": self.model_combo.currentData(),
            "baseline": self.baseline_combo.currentData(),
            "direction": self.direction_combo.currentData(),
            "prominence": self.prominence.value() or None,
            "height": self.height.value() or None,
            "distance": self.distance.value() or None,
            "width": self.width.value() or None,
            "max_peaks": self.max_peaks.value(),
            "confidence": self.confidence.value() / 100.0,
            "sigma": self.sigma_combo.currentData(),
            "absolute_sigma": bool(self.sigma_combo.currentData()) and self.absolute_sigma.isChecked(),
            "als_lambda": self.als_lambda.value(),
            "als_p": self.als_p.value(),
            "als_iterations": self.als_iterations.value(),
            "constant_quantile": self.constant_quantile.value(),
        }

    def _problem(self) -> str:
        if not self.x_combo.currentText() or not self.y_combo.currentText():
            return "Select X and Y columns."
        if self.x_combo.currentText() == self.y_combo.currentText():
            return "X and Y must be different columns."
        sigma = self.sigma_combo.currentData()
        if sigma and sigma in {self.x_combo.currentText(), self.y_combo.currentText()}:
            return "The uncertainty column must be separate from X and Y."
        return ""

    def _refresh_baseline_options(self, *_args) -> None:
        method = self.baseline_combo.currentData()
        for label, widget, wanted in getattr(self, "_baseline_option_rows", ()):
            visible = method == wanted
            label.setVisible(visible)
            widget.setVisible(visible)

    def _refresh_validation(self, *_args) -> None:
        problem = self._problem()
        self.validation.setText(problem or "Ready to detect and fit peaks.")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)

    def _accept_if_valid(self) -> None:
        self._refresh_validation()
        if not self._problem():
            self.accept()


__all__ = ["PeakAnalyzerDialog"]
