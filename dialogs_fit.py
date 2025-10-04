
"""Nonlinear curve fitting dialog."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from processors import FitResult, nonlinear_fit

MODEL_ITEMS: List[Tuple[str, str]] = [
    ("Gaussian", "gaussian"),
    ("Lorentzian", "lorentzian"),
    ("Voigt", "voigt"),
    ("Logistic", "logistic"),
    ("Exp1", "exp1"),
    ("Exp2", "exp2"),
    ("Power", "power"),
    ("Sine", "sine"),
    ("Custom", "custom"),
]

MODEL_PARAMS: Dict[str, List[str]] = {
    "gaussian": ["A", "x0", "sigma", "C"],
    "lorentzian": ["A", "x0", "gamma", "C"],
    "voigt": ["A", "x0", "sigma", "gamma", "C"],
    "logistic": ["L", "k", "x0", "C"],
    "exp1": ["A", "tau", "C"],
    "exp2": ["A1", "tau1", "A2", "tau2", "C"],
    "power": ["A", "n", "C"],
    "sine": ["A", "omega", "phi", "C"],
}

POSITIVE_DEFAULT_MIN = {"sigma", "gamma", "tau", "tau1", "tau2"}

WEIGHTING_ITEMS: List[Tuple[str, str]] = [
    ("None", "none"),
    ("Sigma (std dev)", "sigma"),
    ("1 / sigma^2", "1/sigma^2"),
]

MODEL_DEFAULT_FIELDS: Dict[str, Dict[str, Dict[str, float]]] = {
    "gaussian": {
        "A": {"init": 1.0},
        "x0": {"init": 0.0},
        "sigma": {"init": 1.0, "min": 0.0},
        "C": {"init": 0.0},
    },
    "lorentzian": {
        "A": {"init": 1.0},
        "x0": {"init": 0.0},
        "gamma": {"init": 1.0, "min": 0.0},
        "C": {"init": 0.0},
    },
    "voigt": {
        "A": {"init": 1.0},
        "x0": {"init": 0.0},
        "sigma": {"init": 1.0, "min": 0.0},
        "gamma": {"init": 1.0, "min": 0.0},
        "C": {"init": 0.0},
    },
    "logistic": {
        "L": {"init": 1.0, "min": 0.0},
        "k": {"init": 1.0},
        "x0": {"init": 0.0},
        "C": {"init": 0.0},
    },
    "exp1": {
        "A": {"init": 1.0},
        "tau": {"init": 1.0, "min": 0.0},
        "C": {"init": 0.0},
    },
    "exp2": {
        "A1": {"init": 1.0},
        "tau1": {"init": 1.0, "min": 0.0},
        "A2": {"init": 0.5},
        "tau2": {"init": 2.0, "min": 0.0},
        "C": {"init": 0.0},
    },
    "power": {
        "A": {"init": 1.0},
        "n": {"init": 1.0},
        "C": {"init": 0.0},
    },
    "sine": {
        "A": {"init": 1.0},
        "omega": {"init": 1.0, "min": 0.0},
        "phi": {"init": 0.0},
        "C": {"init": 0.0},
    },
}


def _format_float(val: Optional[float]) -> str:
    if val is None:
        return ""
    try:
        num = float(val)
    except (TypeError, ValueError):
        return ""
    if np.isnan(num):
        return "NaN"
    return f"{num:.6g}"


class NonlinearFitDialog(QDialog):
    """หน้าต่าง Fit เส้นโค้งแบบไม่เชิงเส้น."""

    def __init__(self, parent, dataframe: pd.DataFrame):
        super().__init__(parent)
        self.df = dataframe
        self._current_model_key = MODEL_ITEMS[0][1]
        self._param_widgets: Dict[str, Dict[str, QLineEdit]] = {}
        self._last_result: Optional[FitResult] = None
        self._x_used: Optional[np.ndarray] = None
        self._y_used: Optional[np.ndarray] = None
        self._sigma_used: Optional[np.ndarray] = None
        self.setWindowTitle("Nonlinear Curve Fit")
        self.resize(840, 680)
        self._build_ui()
        self._connect_signals()
        self._update_weighting_state()
        self._refresh_param_form()
        self._update_auto_guesses()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        def _configure_form(form: QFormLayout) -> None:
            form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(8)

        def _label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setMinimumWidth(140)
            return lbl

        # --- Column selection ---
        columns_box = QGroupBox("เลือกคอลัมน์")
        columns_form = QFormLayout()
        _configure_form(columns_form)
        columns_box.setLayout(columns_form)

        self.cb_x = QComboBox()
        self.cb_y = QComboBox()
        self.cb_sigma = QComboBox()
        self.cb_sigma.addItem("(ไม่ใช้)", userData=None)
        for combo in (self.cb_x, self.cb_y, self.cb_sigma):
            combo.setMinimumWidth(240)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for col in self.df.columns:
            self.cb_x.addItem(col)
            self.cb_y.addItem(col)
            self.cb_sigma.addItem(col, userData=col)

        columns_form.addRow(_label("X column:"), self.cb_x)
        columns_form.addRow(_label("Y column:"), self.cb_y)
        columns_form.addRow(_label("Y error column:"), self.cb_sigma)
        content_layout.addWidget(columns_box)

        # --- Model configuration ---
        model_box = QGroupBox("ตั้งค่าโมเดล")
        model_form = QFormLayout()
        _configure_form(model_form)
        model_box.setLayout(model_form)

        self.model_combo = QComboBox()
        for text_label, key in MODEL_ITEMS:
            self.model_combo.addItem(text_label, userData=key)
        self.weight_combo = QComboBox()
        for text_label, key in WEIGHTING_ITEMS:
            self.weight_combo.addItem(text_label, userData=key)
        self.weight_combo.setCurrentIndex(0)
        self.ci_checkbox = QCheckBox("แสดง 95% CI")
        self.ci_checkbox.setChecked(True)
        self.custom_expr_edit = QLineEdit()
        self.custom_expr_edit.setPlaceholderText("y = A*exp(...)+C")
        self.custom_expr_edit.setClearButtonEnabled(True)
        self.custom_params_edit = QLineEdit()
        self.custom_params_edit.setPlaceholderText("A, x0, sigma, C")
        self.custom_params_edit.setClearButtonEnabled(True)

        model_form.addRow(_label("Model:"), self.model_combo)
        model_form.addRow(_label("Weighting:"), self.weight_combo)
        model_form.addRow(_label("Custom expr:"), self.custom_expr_edit)
        model_form.addRow(_label("Custom params:"), self.custom_params_edit)
        options_widget = QWidget()
        options_row = QHBoxLayout(options_widget)
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.addWidget(self.ci_checkbox)
        options_row.addStretch()
        model_form.addRow(_label("ตัวเลือก:"), options_widget)
        content_layout.addWidget(model_box)

        # --- Parameter editor ---
        params_box = QGroupBox("พารามิเตอร์")
        params_box_layout = QVBoxLayout()
        params_box_layout.setContentsMargins(12, 10, 12, 10)
        params_box_layout.setSpacing(6)
        self.params_layout = QFormLayout()
        _configure_form(self.params_layout)
        self.params_layout.setHorizontalSpacing(12)
        self.params_layout.setVerticalSpacing(6)
        params_box_layout.addLayout(self.params_layout)
        params_box.setLayout(params_box_layout)
        content_layout.addWidget(params_box)

        # --- Results ---
        results_box = QGroupBox("ผลลัพธ์")
        results_layout = QVBoxLayout()
        results_layout.setContentsMargins(12, 10, 12, 10)
        results_layout.setSpacing(8)
        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Name", "Value", "StdErr"])
        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionMode(QTableWidget.NoSelection)
        self.results_table.setFocusPolicy(Qt.NoFocus)
        self.results_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        results_layout.addWidget(self.results_table)
        self.stats_label = QLabel("รอการฟิต")
        self.stats_label.setTextFormat(Qt.RichText)
        self.stats_label.setWordWrap(True)
        results_layout.addWidget(self.stats_label)
        results_box.setLayout(results_layout)
        content_layout.addWidget(results_box)

        content_layout.addStretch(1)
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # --- Buttons ---
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        buttons.addStretch()
        self.btn_fit = QPushButton("Fit")
        self.btn_overlay = QPushButton("Overlay to Graph")
        self.btn_save = QPushButton("Save Report")
        self.btn_close = QPushButton("Close")
        self.btn_overlay.setEnabled(False)
        self.btn_save.setEnabled(False)
        for btn in (self.btn_fit, self.btn_overlay, self.btn_save, self.btn_close):
            btn.setMinimumWidth(110)
        buttons.addWidget(self.btn_fit)
        buttons.addWidget(self.btn_overlay)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_close)
        main_layout.addLayout(buttons)
    def _connect_signals(self) -> None:
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.cb_x.currentIndexChanged.connect(self._update_auto_guesses)
        self.cb_y.currentIndexChanged.connect(self._update_auto_guesses)
        self.cb_sigma.currentIndexChanged.connect(self._update_weighting_state)
        self.custom_params_edit.textChanged.connect(self._on_custom_params_changed)
        self.custom_expr_edit.textChanged.connect(self._update_custom_state)
        self.btn_fit.clicked.connect(self._perform_fit)
        self.btn_overlay.clicked.connect(self.overlay_to_graph)
        self.btn_save.clicked.connect(self.save_report)
        self.btn_close.clicked.connect(self.reject)

    def _on_model_changed(self) -> None:
        self._current_model_key = self.model_combo.currentData()
        self._refresh_param_form()
        self._update_custom_state()
        self._update_auto_guesses()

    def _on_custom_params_changed(self) -> None:
        if self._current_model_key == "custom":
            self._refresh_param_form()
            self._update_custom_state()
            self._update_auto_guesses()

    def _refresh_param_form(self) -> None:
        while self.params_layout.rowCount():
            self.params_layout.removeRow(0)
        self._param_widgets.clear()
        for name in self._current_param_list():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            init_edit = QLineEdit()
            init_edit.setPlaceholderText("Initial")
            min_edit = QLineEdit()
            min_edit.setPlaceholderText("Min")
            max_edit = QLineEdit()
            max_edit.setPlaceholderText("Max")
            row_layout.addWidget(init_edit)
            row_layout.addWidget(min_edit)
            row_layout.addWidget(max_edit)
            label = QLabel(f"{name}:")
            label.setMinimumWidth(90)
            self.params_layout.addRow(label, row_widget)
            self._param_widgets[name] = {"init": init_edit, "min": min_edit, "max": max_edit}
        self._update_custom_state()
        self._apply_model_defaults()
    def _current_param_list(self) -> List[str]:
        if self._current_model_key == "custom":
            raw = self.custom_params_edit.text().strip()
            return [name.strip() for name in raw.split(',') if name.strip()]
        return MODEL_PARAMS.get(self._current_model_key, [])

    def _apply_model_defaults(self) -> None:
        defaults = MODEL_DEFAULT_FIELDS.get(self._current_model_key, {})
        for name, widgets in self._param_widgets.items():
            field_defaults = defaults.get(name, {})
            for field_name, default_value in field_defaults.items():
                widget = widgets.get(field_name)
                if widget is None:
                    continue
                if not widget.text().strip():
                    widget.setText(str(default_value))
            if name in POSITIVE_DEFAULT_MIN and not widgets["min"].text().strip():
                widgets["min"].setText("0")

    def _update_custom_state(self) -> None:
        is_custom = self._current_model_key == "custom"
        self.custom_expr_edit.setEnabled(is_custom)
        self.custom_params_edit.setEnabled(is_custom)
        ready = True
        if is_custom:
            ready = bool(self.custom_expr_edit.text().strip() and self.custom_params_edit.text().strip())
        self.btn_fit.setEnabled(ready)

    def _update_weighting_state(self) -> None:
        has_sigma = self.cb_sigma.currentData() is not None
        self.weight_combo.setEnabled(has_sigma)
        if not has_sigma:
            self.weight_combo.setCurrentIndex(0)

    def _assemble_dataframe(self, include_sigma: bool = False) -> Optional[pd.DataFrame]:
        x_col = self.cb_x.currentText()
        y_col = self.cb_y.currentText()
        if not x_col or not y_col:
            return None
        data = pd.DataFrame({
            'x': pd.to_numeric(self.df[x_col], errors='coerce'),
            'y': pd.to_numeric(self.df[y_col], errors='coerce'),
        })
        if include_sigma:
            sigma_key = self.cb_sigma.currentData()
            if sigma_key:
                data['sigma'] = pd.to_numeric(self.df[sigma_key], errors='coerce')
        return data

    def _get_xy_arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        data = self._assemble_dataframe(include_sigma=False)
        if data is None:
            return np.array([]), np.array([])
        data = data.dropna(subset=['x', 'y'])
        return data['x'].to_numpy(dtype=float), data['y'].to_numpy(dtype=float)

    def _prepare_arrays(self) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        data = self._assemble_dataframe(include_sigma=True)
        if data is None:
            return np.array([]), np.array([]), None
        mask = data[['x', 'y']].notna().all(axis=1)
        if 'sigma' in data:
            mask &= data['sigma'].notna() & (data['sigma'] > 0)
        data = data.loc[mask]
        x_vals = data['x'].to_numpy(dtype=float)
        y_vals = data['y'].to_numpy(dtype=float)
        sigma_vals = data['sigma'].to_numpy(dtype=float) if 'sigma' in data else None
        return x_vals, y_vals, sigma_vals

    def _update_auto_guesses(self) -> None:
        x_vals, y_vals = self._get_xy_arrays()
        if not len(x_vals):
            return
        guesses = self._auto_init(self._current_model_key, x_vals, y_vals)
        for name, widgets in self._param_widgets.items():
            if name in guesses:
                widgets['init'].setText(_format_float(guesses[name]))
            if name.lower() in POSITIVE_DEFAULT_MIN and not widgets['min'].text().strip():
                widgets['min'].setText("1e-6")

    def _collect_init_params(self) -> Dict[str, float]:
        params: Dict[str, float] = {}
        for name, widgets in self._param_widgets.items():
            text = widgets['init'].text().strip()
            if not text:
                continue
            try:
                params[name] = float(text)
            except ValueError as exc:
                raise ValueError(f"รูปแบบ Initial ของ {name} ไม่ถูกต้อง") from exc
        return params

    def _collect_bounds_from_form(self) -> Dict[str, Tuple[float, float]]:
        bounds: Dict[str, Tuple[float, float]] = {}
        for name, widgets in self._param_widgets.items():
            min_text = widgets['min'].text().strip()
            max_text = widgets['max'].text().strip()
            lower = float(min_text) if min_text else (-np.inf if name.lower() not in POSITIVE_DEFAULT_MIN else 1e-6)
            upper = float(max_text) if max_text else np.inf
            if lower > upper:
                raise ValueError(f"Bounds ของ {name} ไม่ถูกต้อง (min > max)")
            bounds[name] = (lower, upper)
        return bounds

    def _perform_fit(self) -> None:
        if self._current_model_key == 'custom' and not self.btn_fit.isEnabled():
            QMessageBox.warning(self, "เตือน", "กรุณากรอกสมการและพารามิเตอร์ของโมเดล Custom ให้ครบ")
            return
        try:
            init_params = self._collect_init_params()
            bounds = self._collect_bounds_from_form()
        except ValueError as exc:
            QMessageBox.warning(self, "เตือน", str(exc))
            return
        x_vals, y_vals, sigma_vals = self._prepare_arrays()
        if not len(x_vals):
            QMessageBox.warning(self, "เตือน", "ไม่มีข้อมูลสำหรับการฟิต")
            return
        weighting_key = self.weight_combo.currentData()
        if sigma_vals is None:
            weighting_key = 'none'
        try:
            result = nonlinear_fit(
                x_vals,
                y_vals,
                self._current_model_key,
                init_params,
                bounds=bounds,
                sigma=sigma_vals,
                weighting=weighting_key,
                custom_expr=self.custom_expr_edit.text().strip() if self._current_model_key == 'custom' else None,
                custom_params=self._current_param_list() if self._current_model_key == 'custom' else None,
                calc_ci=self.ci_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", str(exc))
            return
        self._last_result = result
        self._x_used = x_vals
        self._y_used = y_vals
        self._sigma_used = sigma_vals
        self._fill_table(result)
        self._update_stats(result)
        self.btn_overlay.setEnabled(result.success)
        self.btn_save.setEnabled(True)
        if not result.success:
            QMessageBox.information(self, "แจ้งเตือน", result.message or "ปรับค่าเริ่มต้นหรือ bounds แล้วลองใหม่")

    def _fill_table(self, res: FitResult) -> None:
        params = res.params or {}
        self.results_table.setRowCount(len(params))
        for row, (name, value) in enumerate(params.items()):
            stderr = res.stderr.get(name, np.nan) if res.stderr else np.nan
            self.results_table.setItem(row, 0, QTableWidgetItem(name))
            self.results_table.setItem(row, 1, QTableWidgetItem(_format_float(value)))
            self.results_table.setItem(row, 2, QTableWidgetItem(_format_float(stderr)))
        self.results_table.resizeColumnsToContents()

    def _update_stats(self, res: FitResult) -> None:
        lines = [f"<b>สถานะ:</b> {'สำเร็จ' if res.success else 'ล้มเหลว'}"]
        lines.append(f"<b>R²:</b> {_format_float(res.r2)}")
        lines.append(f"<b>RMSE:</b> {_format_float(res.rmse)}")
        lines.append(f"<b>χ²_red:</b> {_format_float(res.chi2_red)}")
        lines.append(f"<b>AIC:</b> {_format_float(res.aic)}")
        lines.append(f"<b>BIC:</b> {_format_float(res.bic)}")
        lines.append(f"<b>ข้อความ:</b> {res.message}")
        self.stats_label.setText("<br>".join(lines))

    def overlay_to_graph(self) -> None:
        if not self._last_result or not self._last_result.success:
            return
        target = getattr(self.parent(), 'plot_fit_result_on_active_tab', None)
        if not callable(target):
            QMessageBox.warning(self, "เตือน", "ไม่พบกราฟสำหรับ Overlay")
            return
        target(self._x_used, self._last_result)

    def save_report(self) -> None:
        if not self._last_result:
            return
        suggested = Path.cwd() / "fit_report.json"
        file_path, _ = QFileDialog.getSaveFileName(self, "บันทึกผลการฟิต", str(suggested), "JSON (*.json)")
        if not file_path:
            return
        json_path = Path(file_path)
        txt_path = json_path.with_suffix('.txt')
        payload = {
            "timestamp": datetime.now().isoformat(timespec='seconds'),
            "model": self.model_combo.currentText(),
            "model_key": self._current_model_key,
            "custom_expr": self.custom_expr_edit.text().strip() if self._current_model_key == 'custom' else None,
            "params": self._last_result.params,
            "stderr": self._last_result.stderr,
            "metrics": {
                "r2": self._last_result.r2,
                "rmse": self._last_result.rmse,
                "chi2_red": self._last_result.chi2_red,
                "aic": self._last_result.aic,
                "bic": self._last_result.bic,
            },
            "message": self._last_result.message,
            "success": self._last_result.success,
        }
        if self._last_result.cov is not None:
            payload["cov"] = self._last_result.cov.tolist()
        if self._last_result.ci95_lower is not None and self._last_result.ci95_upper is not None:
            payload["ci95_lower"] = self._last_result.ci95_lower.tolist()
            payload["ci95_upper"] = self._last_result.ci95_upper.tolist()
        with json_path.open('w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        lines = [
            f"รายงานฟิต: {payload['timestamp']}",
            f"โมเดล: {payload['model']} ({payload['model_key']})",
            f"สถานะ: {'สำเร็จ' if self._last_result.success else 'ล้มเหลว'}",
            f"ข้อความ: {self._last_result.message}",
            "",
            "ค่าพารามิเตอร์:",
        ]
        for name, value in self._last_result.params.items():
            stderr = self._last_result.stderr.get(name, np.nan) if self._last_result.stderr else np.nan
            lines.append(f"  - {name}: {_format_float(value)} ± {_format_float(stderr)}")
        lines.extend([
            "",
            "ค่าสถิติ:",
            f"  - R²: {_format_float(self._last_result.r2)}",
            f"  - RMSE: {_format_float(self._last_result.rmse)}",
            f"  - χ²_red: {_format_float(self._last_result.chi2_red)}",
            f"  - AIC: {_format_float(self._last_result.aic)}",
            f"  - BIC: {_format_float(self._last_result.bic)}",
        ])
        if self._last_result.ci95_lower is not None:
            lines.append("มีช่วงความเชื่อมั่น 95%")
        with txt_path.open('w', encoding='utf-8') as fh:
            fh.write(os.linesep.join(lines))
        QMessageBox.information(self, "บันทึกแล้ว", f"บันทึก {json_path.name} และ {txt_path.name}")

    def _auto_init(self, model_key: str, x: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        guesses: Dict[str, float] = {}
        if not len(x):
            return guesses
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        span_x = np.ptp(x) if np.ptp(x) else 1.0
        span_y = np.ptp(y) if np.ptp(y) else 1.0
        baseline = float(np.nanmin(y)) if y.size else 0.0
        peak = float(np.nanmax(y)) if y.size else baseline + 1.0
        center_idx = int(np.nanargmax(y)) if y.size else 0
        center_x = float(x[center_idx]) if x.size else 0.0
        if model_key == 'gaussian':
            guesses = {
                'A': peak - baseline,
                'x0': center_x,
                'sigma': max(np.std(x), span_x / 6),
                'C': baseline,
            }
        elif model_key == 'lorentzian':
            guesses = {
                'A': peak - baseline,
                'x0': center_x,
                'gamma': max(span_x / 6, 1.0),
                'C': baseline,
            }
        elif model_key == 'voigt':
            width = max(span_x / 6, 1.0)
            guesses = {
                'A': peak - baseline,
                'x0': center_x,
                'sigma': width,
                'gamma': width,
                'C': baseline,
            }
        elif model_key == 'logistic':
            guesses = {
                'L': span_y,
                'k': 1.0 / max(span_x, 1.0),
                'x0': center_x,
                'C': baseline,
            }
        elif model_key == 'exp1':
            guesses = {
                'A': y[0] - baseline if y.size else 1.0,
                'tau': span_x / 3,
                'C': baseline,
            }
        elif model_key == 'exp2':
            guesses = {
                'A1': 0.6 * (y[0] - baseline) if y.size else 1.0,
                'tau1': span_x / 4,
                'A2': 0.4 * (y[0] - baseline) if y.size else 0.5,
                'tau2': span_x / 2,
                'C': baseline,
            }
        elif model_key == 'power':
            guesses = {
                'A': span_y,
                'n': 1.0,
                'C': baseline,
            }
        elif model_key == 'sine':
            period = span_x if span_x else 1.0
            guesses = {
                'A': span_y / 2,
                'omega': 2 * np.pi / period,
                'phi': 0.0,
                'C': baseline + span_y / 2,
            }
        return guesses

