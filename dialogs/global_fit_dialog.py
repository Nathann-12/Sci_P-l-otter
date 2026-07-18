"""Beginner-safe setup dialog for simultaneous/global fitting."""
from __future__ import annotations

from typing import Iterable

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QCheckBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


MODEL_PARAMETERS = {
    "gaussian": ("amplitude", "center", "sigma", "offset"),
    "lorentzian": ("amplitude", "center", "gamma", "offset"),
    "voigt": ("amplitude", "center", "sigma", "gamma", "offset"),
    "exponential": ("amplitude", "rate", "offset"),
    "exponential_decay": ("amplitude", "tau", "offset"),
}


class GlobalFitDialog(QDialog):
    def __init__(self, numeric_columns: Iterable[str], parent=None):
        super().__init__(parent)
        columns = [str(value) for value in numeric_columns]
        self.setWindowTitle("Global Fit")
        self.resize(690, 760)
        self._constraint_widgets = {}
        layout = QVBoxLayout(self)

        description = QLabel(
            "Fit two or more Y columns at once. Shared parameters use one value across all "
            "datasets; unshared parameters are estimated separately for each Y column."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        data_box = QGroupBox("Data mapping")
        data_form = QFormLayout(data_box)
        self.x_combo = QComboBox()
        self.x_combo.addItems(columns)
        data_form.addRow("X column:", self.x_combo)
        self.y_list = QListWidget()
        self.y_list.addItems(columns)
        self.y_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.y_list.setMinimumHeight(125)
        data_form.addRow("Y datasets:", self.y_list)
        self.sigma_combo = QComboBox()
        self.sigma_combo.addItem("None", None)
        for column in columns:
            self.sigma_combo.addItem(column, column)
        data_form.addRow("Shared sigma column:", self.sigma_combo)
        self.absolute_sigma = QCheckBox("Treat sigma as absolute measurement uncertainty")
        self.absolute_sigma.setChecked(True)
        self.absolute_sigma.setEnabled(False)
        self.sigma_combo.currentIndexChanged.connect(
            lambda: self.absolute_sigma.setEnabled(self.sigma_combo.currentData() is not None)
        )
        data_form.addRow("Uncertainty meaning:", self.absolute_sigma)
        layout.addWidget(data_box)

        model_box = QGroupBox("Model and constraints")
        model_form = QFormLayout(model_box)
        self.model_combo = QComboBox()
        for name in MODEL_PARAMETERS:
            self.model_combo.addItem(name.replace("_", " ").title(), name)
        self.model_combo.currentIndexChanged.connect(self._refresh_parameters)
        model_form.addRow("Model:", self.model_combo)
        self.shared_list = QListWidget()
        self.shared_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.shared_list.setMinimumHeight(105)
        model_form.addRow("Shared parameters:", self.shared_list)
        self.constraint_table = QTableWidget(0, 6)
        self.constraint_table.setHorizontalHeaderLabels(
            ("Parameter", "Initial", "Lower", "Upper", "Fixed", "Fixed value")
        )
        self.constraint_table.verticalHeader().setVisible(False)
        self.constraint_table.setMinimumHeight(155)
        self.constraint_table.horizontalHeader().setStretchLastSection(True)
        model_form.addRow("Parameter constraints:", self.constraint_table)
        self.loss_combo = QComboBox()
        self.loss_combo.addItem("Ordinary least squares", "linear")
        self.loss_combo.addItem("Robust: soft L1", "soft_l1")
        self.loss_combo.addItem("Robust: Huber", "huber")
        self.loss_combo.addItem("Robust: Cauchy", "cauchy")
        model_form.addRow("Loss:", self.loss_combo)
        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(50.0, 99.99)
        self.confidence.setDecimals(2)
        self.confidence.setValue(95.0)
        self.confidence.setSuffix(" %")
        model_form.addRow("Confidence level:", self.confidence)
        layout.addWidget(model_box)

        self.validation = QLabel("")
        self.validation.setWordWrap(True)
        self.validation.setStyleSheet("color:#e29b52")
        layout.addWidget(self.validation)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Fit All Datasets")
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.x_combo.currentTextChanged.connect(self._refresh_validation)
        self.y_list.itemSelectionChanged.connect(self._refresh_validation)
        self.sigma_combo.currentIndexChanged.connect(self._refresh_validation)
        self._refresh_parameters()
        if columns:
            self.x_combo.setCurrentIndex(0)
            for index in range(1, self.y_list.count()):
                self.y_list.item(index).setSelected(True)
        self._refresh_validation()

    def values(self) -> dict:
        initial, fixed, bounds = self._constraint_values()
        values = {
            "x": self.x_combo.currentText(),
            "ys": [item.text() for item in self.y_list.selectedItems()],
            "sigma": self.sigma_combo.currentData(),
            "model": self.model_combo.currentData(),
            "shared": [item.text() for item in self.shared_list.selectedItems()],
            "loss": self.loss_combo.currentData(),
            "confidence": self.confidence.value() / 100.0,
            "absolute_sigma": bool(self.sigma_combo.currentData()) and self.absolute_sigma.isChecked(),
        }
        if initial:
            values["initial"] = initial
        if fixed:
            values["fixed"] = fixed
        if bounds:
            values["bounds"] = bounds
        return values

    def _refresh_parameters(self, *_args) -> None:
        previous = {item.text() for item in self.shared_list.selectedItems()}
        self.shared_list.clear()
        self.constraint_table.setRowCount(0)
        self._constraint_widgets = {}
        model = self.model_combo.currentData()
        params = MODEL_PARAMETERS.get(model, ())
        self.shared_list.addItems(params)
        preferred = previous.intersection(params)
        if not preferred:
            preferred = {p for p in params if p not in {"amplitude", "offset"}}
        for index in range(self.shared_list.count()):
            item = self.shared_list.item(index)
            item.setSelected(item.text() in preferred)
        self.constraint_table.setRowCount(len(params))
        for row, parameter in enumerate(params):
            name_item = QTableWidgetItem(parameter)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.constraint_table.setItem(row, 0, name_item)
            initial = QLineEdit()
            initial.setPlaceholderText("Auto")
            lower = QLineEdit()
            lower.setPlaceholderText("Required with upper")
            upper = QLineEdit()
            upper.setPlaceholderText("Required with lower")
            fixed = QCheckBox()
            fixed_value = QLineEdit()
            fixed_value.setPlaceholderText("Value")
            fixed_value.setEnabled(False)
            fixed.toggled.connect(fixed_value.setEnabled)
            for widget in (initial, lower, upper, fixed_value):
                widget.textChanged.connect(self._refresh_validation)
            fixed.toggled.connect(self._refresh_validation)
            for column, widget in enumerate((initial, lower, upper, fixed, fixed_value), start=1):
                self.constraint_table.setCellWidget(row, column, widget)
            self._constraint_widgets[parameter] = {
                "initial": initial, "lower": lower, "upper": upper,
                "fixed": fixed, "fixed_value": fixed_value,
            }
        self.constraint_table.resizeColumnsToContents()
        self._refresh_validation()

    def _problem(self) -> str:
        x_column = self.x_combo.currentText()
        y_columns = [item.text() for item in self.y_list.selectedItems()]
        sigma_column = self.sigma_combo.currentData()
        if not x_column:
            return "Select an X column."
        if len(y_columns) < 2:
            return "Select at least two Y columns for a global fit."
        if x_column in y_columns:
            return "The X column cannot also be a Y dataset."
        if sigma_column in y_columns or sigma_column == x_column:
            return "The uncertainty column must be separate from X and Y."
        constraint_problem = self._constraint_problem()
        if constraint_problem:
            return constraint_problem
        return ""

    def _constraint_problem(self) -> str:
        for parameter, widgets in self._constraint_widgets.items():
            parsed = {}
            for key in ("initial", "lower", "upper", "fixed_value"):
                text = widgets[key].text().strip()
                if not text:
                    parsed[key] = None
                    continue
                try:
                    value = float(text)
                except ValueError:
                    return f"{parameter}: {key.replace('_', ' ')} must be a number."
                if not math.isfinite(value):
                    return f"{parameter}: constraints must be finite numbers."
                parsed[key] = value
            if (parsed["lower"] is None) != (parsed["upper"] is None):
                return f"{parameter}: enter both lower and upper bounds, or leave both blank."
            if parsed["lower"] is not None and parsed["lower"] >= parsed["upper"]:
                return f"{parameter}: lower bound must be smaller than upper bound."
            if widgets["fixed"].isChecked() and parsed["fixed_value"] is None:
                return f"{parameter}: enter a fixed value or clear Fixed."
            if widgets["fixed"].isChecked() and parsed["lower"] is not None:
                if not parsed["lower"] <= parsed["fixed_value"] <= parsed["upper"]:
                    return f"{parameter}: fixed value must lie inside its bounds."
        return ""

    def _constraint_values(self):
        problem = self._constraint_problem()
        if problem:
            raise ValueError(problem)
        initial, fixed, bounds = {}, {}, {}
        for parameter, widgets in self._constraint_widgets.items():
            initial_text = widgets["initial"].text().strip()
            lower_text = widgets["lower"].text().strip()
            upper_text = widgets["upper"].text().strip()
            fixed_text = widgets["fixed_value"].text().strip()
            if initial_text and not widgets["fixed"].isChecked():
                initial[parameter] = float(initial_text)
            if lower_text and upper_text:
                bounds[parameter] = (float(lower_text), float(upper_text))
            if widgets["fixed"].isChecked():
                fixed[parameter] = float(fixed_text)
        return initial, fixed, bounds

    def _refresh_validation(self, *_args) -> None:
        problem = self._problem()
        count = len(self.y_list.selectedItems())
        self.validation.setText(problem or f"Ready: {count} datasets will be fitted simultaneously.")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not problem)

    def _accept_if_valid(self) -> None:
        self._refresh_validation()
        if not self._problem():
            self.accept()


__all__ = ["GlobalFitDialog", "MODEL_PARAMETERS"]
