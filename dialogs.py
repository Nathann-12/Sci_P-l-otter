# dialogs.py
from __future__ import annotations
from typing import Iterable, Dict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QFormLayout, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QListWidget, QListWidgetItem, QTableView, QCheckBox,
    QLineEdit, QTextEdit, QMessageBox, QSplitter
)
from PySide6 import QtCore  # UI-REFINE: สำหรับ PandasModel
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # UI-FIT: preview canvas
from matplotlib.figure import Figure  # UI-FIT
import numpy as np
import pandas as pd
from calc_columns_editor import CalculatedColumnsEditor, evaluate_formula


# ---------- เลือกตัวแปรจาก CDF/NetCDF ----------
class MultiDimSliceDialog(QDialog):
    """
    ใช้ได้ทั้ง CDF/NetCDF:
      - เลือก data variable
      - เลือก time variable
      - ระบุ index ของแกนอื่น ๆ (ใส่ 0 ถ้าไม่แน่ใจ)
    """
    def __init__(self, parent, path: str, variables: Iterable[str], time_candidates: Iterable[str]):
        super().__init__(parent)
        self.setWindowTitle("เลือกตัวแปร (CDF/NetCDF)")
        self.resize(520, 260)
        self.path = path
        self.index_spins: Dict[str, QSpinBox] = {}

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.cbData = QComboBox(self); self.cbData.addItems([str(v) for v in variables])
        self.cbTime = QComboBox(self); self.cbTime.addItems([str(v) for v in time_candidates])
        form.addRow(QLabel("Data variable:"), self.cbData)
        form.addRow(QLabel("Time variable:"), self.cbTime)
        layout.addLayout(form)

        layout.addWidget(QLabel("Indices for extra axes (ใส่ 0 ถ้าไม่แน่ใจ):"))
        grid = QFormLayout()
        # ใส่ spinbox มาตรฐานไว้ 3 ช่องพอ (DEP1..DEP3) — พอสำหรับไฟล์วิทยาศาสตร์ส่วนใหญ่
        for i in range(1, 4):
            lab = f"DEP{i}"
            sp = QSpinBox(self); sp.setMinimum(0); sp.setMaximum(10**6)
            grid.addRow(QLabel(lab+":"), sp)
            self.index_spins[lab] = sp
        wrap = QWidget(); wrap.setLayout(grid); layout.addWidget(wrap)

        row = QHBoxLayout()
        btnOk = QPushButton("OK"); btnCancel = QPushButton("Cancel")
        row.addStretch(1); row.addWidget(btnOk); row.addWidget(btnCancel)
        layout.addLayout(row)

        btnOk.clicked.connect(self.accept)
        btnCancel.clicked.connect(self.reject)

    def get_selection(self):
        data_var = self.cbData.currentText()
        time_var = self.cbTime.currentText()
        index_map = {k: w.value() for k, w in self.index_spins.items()}
        return data_var, time_var, index_map


# ---------- จัดชนิดคอลัมน์ ----------
class ColumnTypeDialog(QDialog):
    """
    รับรายการคอลัมน์ แล้วให้เลือกชนิด:
      Auto / String / Integer / Float / Datetime
    ส่งออก mapping ผ่าน get_mapping()
    """
    def __init__(self, parent, columns: Iterable[str]):
        super().__init__(parent)
        self.setWindowTitle("กำหนดชนิดคอลัมน์")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Column", "Type"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        cols = [str(c) for c in columns]
        self.table.setRowCount(len(cols))
        types = ["Auto", "String", "Integer", "Float", "Datetime"]
        for r, col in enumerate(cols):
            self.table.setItem(r, 0, QTableWidgetItem(col))
            cb = QComboBox(self); cb.addItems(types)
            # เดา default แบบง่าย
            cb.setCurrentText("Float" if any(k in col.lower() for k in ("x","y","z","val","mag","amp","freq")) else "Auto")
            self.table.setCellWidget(r, 1, cb)

        layout.addWidget(self.table)
        row = QHBoxLayout()
        btnOk = QPushButton("Apply"); btnCancel = QPushButton("Cancel")
        row.addStretch(1); row.addWidget(btnOk); row.addWidget(btnCancel)
        layout.addLayout(row)
        btnOk.clicked.connect(self.accept); btnCancel.clicked.connect(self.reject)

    def get_mapping(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for r in range(self.table.rowCount()):
            col = self.table.item(r, 0).text()
            typ = self.table.cellWidget(r, 1).currentText()
            out[col] = typ
        return out


# ---------- FFTDialog ----------
class FFTDialog(QDialog):
    """
    Dialog ตั้งค่าการคำนวณ FFT:
      - เลือกคอลัมน์ X (เวลา/ระยะ) และ Y (สัญญาณ)
      - เลือก window function
      - เลือก detrend
    คืนค่า (x_col, y_col, window, detrend)
    """
    def __init__(self, parent, columns: Iterable[str]):
        super().__init__(parent)
        self.setWindowTitle("FFT Settings")
        self.resize(420, 220)

        cols = [str(c) for c in columns]

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.cbX = QComboBox(self); self.cbX.addItems(cols)
        self.cbY = QComboBox(self); self.cbY.addItems(cols)

        # ให้ชื่อ window ตรงกับที่โค้ดคำนวณรองรับใน processors.py (hann/hamming/none)
        self.cbWindow = QComboBox(self)
        self.cbWindow.addItems(["hann", "hamming", "none"])

        # detrend ใน processors.py เป็น boolean (True/False)
        self.cbDetrend = QComboBox(self)
        self.cbDetrend.addItems(["True", "False"])

        form.addRow(QLabel("X column:"), self.cbX)
        form.addRow(QLabel("Y column:"), self.cbY)
        form.addRow(QLabel("Window:"), self.cbWindow)
        form.addRow(QLabel("Detrend:"), self.cbDetrend)

        layout.addLayout(form)

        row = QHBoxLayout()
        btnOk = QPushButton("OK"); btnCancel = QPushButton("Cancel")
        row.addStretch(1); row.addWidget(btnOk); row.addWidget(btnCancel)
        layout.addLayout(row)

        btnOk.clicked.connect(self.accept)
        btnCancel.clicked.connect(self.reject)

    def get_settings(self):
        x_col = self.cbX.currentText()
        y_col = self.cbY.currentText()

        # map window 'hann' -> 'hanning' ให้สอดคล้องกับ processors.compute_fft
        win = self.cbWindow.currentText()
        if win == "hann":
            win = "hanning"  # processors.py รองรับ 'hanning'/'hamming'/'none'

        detrend = (self.cbDetrend.currentText() == "True")
        return x_col, y_col, win, detrend
class FFTDialog(QDialog):
    """
    Dialog ตั้งค่าการคำนวณ FFT:
      - เลือกคอลัมน์ X (เวลา/ความถี่) และ Y (ข้อมูล)
      - เลือก window function
      - เลือก detrend
    คืนค่า get_settings() -> (x_col, y_col, window, detrend)
    """
    def __init__(self, parent, columns=None):
        super().__init__(parent)
        self.setWindowTitle("FFT Settings")
        self.resize(420, 200)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.cbX = QComboBox(self)
        self.cbY = QComboBox(self)
        if columns is None:
            columns = []
        self.cbX.addItems([str(c) for c in columns])
        self.cbY.addItems([str(c) for c in columns])

        self.cbWindow = QComboBox(self)
        self.cbWindow.addItems(["hann", "hamming", "blackman", "bartlett", "rectangular"])

        self.cbDetrend = QComboBox(self)
        self.cbDetrend.addItems(["none", "mean", "linear"])

        form.addRow(QLabel("X column:"), self.cbX)
        form.addRow(QLabel("Y column:"), self.cbY)
        form.addRow(QLabel("Window:"), self.cbWindow)
        form.addRow(QLabel("Detrend:"), self.cbDetrend)
        layout.addLayout(form)

        row = QHBoxLayout()
        btnOk = QPushButton("OK"); btnCancel = QPushButton("Cancel")
        row.addStretch(1); row.addWidget(btnOk); row.addWidget(btnCancel)
        layout.addLayout(row)

        btnOk.clicked.connect(self.accept)
        btnCancel.clicked.connect(self.reject)

    def get_settings(self):
        return (
            self.cbX.currentText(),
            self.cbY.currentText(),
            self.cbWindow.currentText(),
            self.cbDetrend.currentText(),
        )


# UI-REFINE: Aggregate Dialog — รวมคะแนนตามรหัสนิสิตและสร้างกราฟแท่ง
class AggregateDialog(QDialog):
    """
    UI-REFINE: Dialog สำหรับ Aggregate
    คืนค่า params เป็น dict: {"id_col": str, "value_cols": [str], "agg": str, "stacked": bool}
    รองรับ Preview 10 แถวด้วย QTableView
    """
    def __init__(self, parent, df: pd.DataFrame, columns: Iterable[str]):
        super().__init__(parent)
        self.setWindowTitle("Aggregate…")
        self.resize(540, 420)
        self._df = df
        cols = [str(c) for c in columns]

        layout = QVBoxLayout(self)
        # Calculated columns editor (above aggregate controls)
        self._calc_formulas: list[tuple[str,str]] = []
        self._df_work = self._df.copy()
        def _on_calc_changed(formulas):
            self._calc_formulas = formulas or []
            self._recompute_calculated_columns()
            self._refresh_value_columns_list()
        self.calc_editor = CalculatedColumnsEditor(get_df=lambda: self._df, on_changed=_on_calc_changed)
        layout.addWidget(self.calc_editor)
        form = QFormLayout()

        # ID column
        self.cbId = QComboBox(self); self.cbId.addItems([""] + cols)
        form.addRow(QLabel("ID column:"), self.cbId)

        # Value columns (checklist)
        self.lstValues = QListWidget(self)
        for c in cols:
            it = QListWidgetItem(str(c))
            it.setCheckState(Qt.Unchecked)
            self.lstValues.addItem(it)
        form.addRow(QLabel("Value columns:"), self.lstValues)

        # Aggregation
        self.cbAgg = QComboBox(self); self.cbAgg.addItems(["sum", "mean", "count", "max", "min"])
        form.addRow(QLabel("Aggregation:"), self.cbAgg)

        # Stacked toggle
        self.cbStacked = QComboBox(self); self.cbStacked.addItems(["stacked: off", "stacked: on"])
        form.addRow(QLabel("Bar mode:"), self.cbStacked)

        layout.addLayout(form)

        # Preview table (hidden to avoid duplication with top preview)
        self.tbl = QTableView(self)
        self.tbl.setVisible(False)
        layout.addWidget(self.tbl)

        # Buttons
        row = QHBoxLayout()
        self.btnPreview = QPushButton("Preview")
        self.btnCreate = QPushButton("Create Plot")
        self.btnCreate.setEnabled(False)  # ป้องกันตอนยังไม่เลือกครบ
        row.addStretch(1); row.addWidget(self.btnPreview); row.addWidget(self.btnCreate)
        layout.addLayout(row)

        # signals
        self.btnPreview.clicked.connect(self._do_preview)
        self.btnCreate.clicked.connect(self.accept)
        self.cbId.currentTextChanged.connect(self._update_create_enabled)
        self.lstValues.itemChanged.connect(lambda _: self._update_create_enabled())

        self._update_create_enabled()

    def _selected_values(self) -> list[str]:
        vals: list[str] = []
        for i in range(self.lstValues.count()):
            it = self.lstValues.item(i)
            if it.checkState() == Qt.Checked:
                vals.append(it.text())
        return vals

    def _update_create_enabled(self):
        ok = bool(self.cbId.currentText().strip()) and (len(self._selected_values()) > 0)
        self.btnCreate.setEnabled(ok)

    def _do_preview(self):
        try:
            params = self.get_params()
            id_col = params.get("id_col"); value_cols = params.get("value_cols", []); agg = params.get("agg", "sum")
            if not id_col or not value_cols:
                # ล้าง preview ถ้าเลือกไม่ครบ
                self.tbl.setModel(None)
                return
            # groupby preview (with calculated columns)
            self._recompute_calculated_columns()
            df = self._df_work
            if agg == "sum":
                out = df.groupby(id_col)[value_cols].sum().reset_index()
            elif agg == "mean":
                out = df.groupby(id_col)[value_cols].mean().reset_index()
            elif agg == "count":
                out = df.groupby(id_col)[value_cols].count().reset_index()
            elif agg == "max":
                out = df.groupby(id_col)[value_cols].max().reset_index()
            else:
                out = df.groupby(id_col)[value_cols].min().reset_index()
            # แสดง 10 แถวแรก
            model = PandasModel(out.head(10))
            self.tbl.setModel(model)
        except Exception:
            self.tbl.setModel(None)

    def get_params(self) -> dict:
        return {
            "id_col": self.cbId.currentText().strip(),
            "value_cols": self._selected_values(),
            "agg": self.cbAgg.currentText(),
            "stacked": (self.cbStacked.currentIndex() == 1),
        }

    # ---- Calculated columns helpers ----
    def _recompute_calculated_columns(self):
        self._df_work = self._df.copy()
        for name, expr in getattr(self, '_calc_formulas', []) or []:
            try:
                self._df_work[name] = evaluate_formula(self._df_work, expr)
            except Exception as e:
                print("[Aggregate] formula '{}' failed: {}".format(name, e))
        # Propagate newly computed columns to main window so X/Y combos see them
        try:
            parent = self.parent()
            if parent is not None and hasattr(parent, '_df'):
                for name, _ in getattr(self, '_calc_formulas', []) or []:
                    try:
                        parent._df[name] = self._df_work[name]
                    except Exception:
                        pass
                # Ask main window to refresh X/Y combos
                if hasattr(parent, 'refresh_xy_columns'):
                    try:
                        parent.refresh_xy_columns()
                    except Exception:
                        pass
        except Exception:
            pass

    def _refresh_value_columns_list(self):
        self.lstValues.clear()
        df = getattr(self, '_df_work', None) or self._df
        for c in df.columns:
            try:
                if pd.api.types.is_numeric_dtype(df[c]):
                    it = QListWidgetItem(str(c))
                    it.setCheckState(Qt.Unchecked)
                    self.lstValues.addItem(it)
            except Exception:
                continue


# UI-REFINE: Model แสดง DataFrame แบบง่ายใน QTableView
class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df.copy()

    def rowCount(self, parent=None):
        return len(self._df)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            val = self._df.iloc[index.row(), index.column()]
            return str(val)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(section)


# UI-FIT: Dialog ฟิตเส้นโค้งให้ซีรีส์ปัจจุบัน
class FitDialog(QDialog):
    """
    UI-FIT: เลือกรายการซีรีส์, โมเดล, ออปชัน แล้ว preview ผลฟิตใน mini-canvas
    get_params() -> {
      "series_label": str,
      "model": str,               # linear | polynomial | exponential | power | gaussian | sine
      "degree": Optional[int],
      "show_eq": bool,
      "show_resid": bool,
    }
    """
    def __init__(self, parent, series_labels: Iterable[str], series_data: dict[str, tuple[np.ndarray, np.ndarray]]):
        super().__init__(parent)
        self.setWindowTitle("Curve Fit…")
        self.resize(620, 420)
        self._series_labels = [str(s) for s in series_labels]
        self._series_data = series_data

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.cbSeries = QComboBox(self); self.cbSeries.addItems(self._series_labels)
        form.addRow(QLabel("Series:"), self.cbSeries)

        self.cbModel = QComboBox(self)
        self.cbModel.addItems(["Linear", "Polynomial", "Exponential", "Power-law", "Gaussian", "Sine"])
        form.addRow(QLabel("Model:"), self.cbModel)

        self.spDegree = QSpinBox(self); self.spDegree.setRange(2, 10); self.spDegree.setValue(2)
        form.addRow(QLabel("Degree (poly):"), self.spDegree)

        self.chkEq = QCheckBox("Show equation on plot"); self.chkEq.setChecked(True)
        self.chkResid = QCheckBox("Show residuals panel")
        rowChk = QHBoxLayout(); rowChk.addWidget(self.chkEq); rowChk.addWidget(self.chkResid)
        wChk = QWidget(self); wChk.setLayout(rowChk)
        form.addRow(wChk)

        layout.addLayout(form)

        # mini-canvas preview
        self.fig = Figure(figsize=(4, 2.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        row = QHBoxLayout()
        self.btnPreview = QPushButton("Preview")
        self.btnOk = QPushButton("OK")
        self.btnCancel = QPushButton("Cancel")
        row.addStretch(1); row.addWidget(self.btnPreview); row.addWidget(self.btnOk); row.addWidget(self.btnCancel)
        layout.addLayout(row)

        # signals
        self.cbModel.currentTextChanged.connect(self._update_degree_visibility)
        self.btnPreview.clicked.connect(self._preview)
        self.btnOk.clicked.connect(self.accept)
        self.btnCancel.clicked.connect(self.reject)
        self._update_degree_visibility()

    def _update_degree_visibility(self):
        self.spDegree.setVisible(self.cbModel.currentText().lower().startswith("poly"))

    def get_params(self) -> dict:
        model_map = {
            "linear": "linear",
            "polynomial": "polynomial",
            "exponential": "exponential",
            "power-law": "power",
            "gaussian": "gaussian",
            "sine": "sine",
        }
        m = model_map.get(self.cbModel.currentText().lower(), "linear")
        return {
            "series_label": self.cbSeries.currentText(),
            "model": m,
            "degree": int(self.spDegree.value()) if m == "polynomial" else None,
            "show_eq": bool(self.chkEq.isChecked()),
            "show_resid": bool(self.chkResid.isChecked()),
        }

    def _preview(self):
        # UI-FIT: แสดงเส้นข้อมูล + ผลฟิตอย่างหยาบด้วย NumPy (ไม่ใช้ SciPy เพื่อรักษา dependency)
        try:
            params = self.get_params()
            label = params["series_label"]; model = params["model"]; deg = params.get("degree")
            if label not in self._series_data:
                return
            x, y = self._series_data[label]
            import numpy as _np
            import math as _math
            # clean
            x = _np.asarray(x); y = _np.asarray(y)
            mask = _np.isfinite(x) & _np.isfinite(y)
            x = x[mask]; y = y[mask]
            if x.size < 5:
                return
            xs = _np.linspace(_np.nanmin(x), _np.nanmax(x), 200)
            ys = _np.zeros_like(xs)

            def _polyfit(d):
                c = _np.polyfit(x, y, d)
                return _np.poly1d(c)(xs)

            if model == "linear":
                ys = _polyfit(1)
            elif model == "polynomial":
                d = max(2, int(deg or 2))
                ys = _polyfit(d)
            elif model == "exponential":
                # y ~ a*exp(bx) + c (c≈min)
                c0 = float(_np.nanmin(y))
                y1 = _np.clip(y - c0, 1e-9, _np.inf)
                b, a0 = _np.polyfit(x, _np.log(y1), 1)
                a = _np.exp(a0)
                ys = a * _np.exp(b * xs) + c0
            elif model == "power":
                # y ~ a*x^b (x>0,y>0)
                m = (x > 0) & (y > 0)
                if m.sum() >= 2:
                    b, a0 = _np.polyfit(_np.log(x[m]), _np.log(y[m]), 1)
                    a = _np.exp(a0)
                    ys = a * xs**b
            elif model == "gaussian":
                # y ~ A*exp(-(x-μ)^2/(2σ^2)) + C, ประมาณง่ายๆ
                mu = float(x[_np.argmax(y)])
                p5, p95 = _np.percentile(x, [5, 95])
                sigma = max(1e-9, float((p95 - p5) / 4.0))
                G = _np.exp(-0.5 * ((xs - mu) / sigma) ** 2)
                # LS สำหรับ A,C: y ≈ A*G + C
                X = _np.vstack([G, _np.ones_like(G)]).T
                sol, *_ = _np.linalg.lstsq(X, _np.interp(xs, x, y), rcond=None)
                A, C = float(sol[0]), float(sol[1])
                ys = A * G + C
            else:  # sine
                # y ~ A*sin(2π f x + φ) + C
                xnum = x
                dt = _np.median(_np.diff(_np.sort(xnum)))
                if not _np.isfinite(dt) or dt <= 0:
                    dt = 1.0
                Y = _np.fft.rfft(y - _np.mean(y))
                freq = _np.fft.rfftfreq(y.size, d=dt)
                if freq.size > 1:
                    k = int(_np.argmax(_np.abs(Y[1:])) + 1)
                    f0 = float(freq[k])
                else:
                    f0 = 1.0
                w = 2 * _np.pi * f0
                S = _np.sin(w * x); Cc = _np.cos(w * x)
                A_mat = _np.vstack([S, Cc, _np.ones_like(S)]).T
                beta, *_ = _np.linalg.lstsq(A_mat, y, rcond=None)
                s, c, c0 = beta
                A = float(_np.sqrt(s**2 + c**2)); phi = float(_np.arctan2(c, s)); C0 = float(c0)
                ys = A * _np.sin(w * xs + phi) + C0

            self.ax.clear(); self.ax.plot(x, y, ".", alpha=0.6, label="data")
            self.ax.plot(xs, ys, "-", label="fit")
            # Note: beautify_axes not available in this context, keep original styling
            self.ax.legend(loc="best"); self.fig.tight_layout(); self.canvas.draw()
        except Exception:
            self.ax.clear(); self.canvas.draw()

# ---------- Create Derived Column Dialog ----------
class DerivedColumnDialog(QDialog):
    """
    Dialog สำหรับสร้างคอลัมน์ใหม่จากนิพจน์ทางคณิตศาสตร์
    รองรับการอ้างอิงคอลัมน์ด้วย backtick และฟังก์ชัน numpy ที่ปลอดภัย
    """
    
    def __init__(self, parent, dataframe: pd.DataFrame):
        super().__init__(parent)
        self.dataframe = dataframe
        self.result_series = None  # เก็บผลลัพธ์สำหรับ Apply
        
        self.setWindowTitle("สร้างคอลัมน์ใหม่ (Create Derived Column)")
        self.setModal(True)
        self.resize(800, 600)
        
        self.setup_ui()
        self.setup_connections()
        
        # โหลดรายชื่อคอลัมน์
        self.populate_columns()
    
    def setup_ui(self):
        """สร้าง UI สำหรับ dialog"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # ชื่อคอลัมน์ใหม่
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("ชื่อคอลัมน์ใหม่:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("เช่น B_magnitude, Speed_kmh")
        # Styling will be applied by Dark Theme
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # แบ่งหน้าจอเป็น 2 ส่วน: ซ้าย (นิพจน์) และขวา (คอลัมน์)
        splitter = QSplitter(Qt.Horizontal)
        
        # ซ้าย: นิพจน์และปุ่มฟังก์ชัน
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # คำอธิบาย
        help_label = QLabel("""
        <b>วิธีใช้:</b><br>
        • อ้างอิงคอลัมน์ด้วย backtick: <code>`Bx`</code>, <code>`Mag Field`</code><br>
        • ใช้ฟังก์ชัน: sqrt(), abs(), sin(), cos(), log(), exp()<br>
        • คลิกสองครั้งที่คอลัมน์เพื่อแทรกชื่อลงในนิพจน์<br>
        • ตัวอย่าง: <code>sqrt(`Bx`**2 + `By`**2 + `Bz`**2)</code>
        """)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
                font-size: 11px;
                color: #495057;
            }
        """)
        left_layout.addWidget(help_label)
        
        # ช่องนิพจน์
        expr_label = QLabel("นิพจน์:")
        expr_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        left_layout.addWidget(expr_label)
        
        self.expression_edit = QTextEdit()
        self.expression_edit.setMaximumHeight(120)
        self.expression_edit.setPlaceholderText("พิมพ์นิพจน์ที่นี่... เช่น `Bx * By` หรือ `sqrt(`Bx`**2 + `By`**2)`")
        # Styling will be applied by Dark Theme
        left_layout.addWidget(self.expression_edit)
        
        # ปุ่มฟังก์ชันลัด
        functions_label = QLabel("ฟังก์ชันลัด:")
        functions_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        left_layout.addWidget(functions_label)
        
        # สร้างปุ่มฟังก์ชันในแถว
        functions_layout = QVBoxLayout()
        
        # แถวที่ 1: ฟังก์ชันพื้นฐาน
        row1 = QHBoxLayout()
        basic_functions = [
            ("sqrt()", "sqrt()"), ("abs()", "abs()"), 
            ("sin()", "sin()"), ("cos()", "cos()"), ("tan()", "tan()")
        ]
        for text, func in basic_functions:
            btn = QPushButton(text)
            # Styling will be applied by Dark Theme
            btn.clicked.connect(lambda checked, f=func: self.insert_function(f))
            row1.addWidget(btn)
        functions_layout.addLayout(row1)
        
        # แถวที่ 2: ฟังก์ชันเพิ่มเติม
        row2 = QHBoxLayout()
        advanced_functions = [
            ("log()", "log()"), ("exp()", "exp()"), 
            ("min()", "min()"), ("max()", "max()"), ("mean()", "mean()")
        ]
        for text, func in advanced_functions:
            btn = QPushButton(text)
            # Styling will be applied by Dark Theme
            btn.clicked.connect(lambda checked, f=func: self.insert_function(f))
            row2.addWidget(btn)
        functions_layout.addLayout(row2)
        
        left_layout.addLayout(functions_layout)
        left_layout.addStretch()
        
        splitter.addWidget(left_widget)
        
        # ขวา: รายชื่อคอลัมน์
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        columns_label = QLabel("คอลัมน์ที่มีอยู่ (คลิกสองครั้งเพื่อแทรก):")
        columns_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        right_layout.addWidget(columns_label)
        
        self.columns_list = QListWidget()
        # Styling will be applied by Dark Theme
        right_layout.addWidget(self.columns_list)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 300])  # แบ่งสัดส่วน 4:3
        
        layout.addWidget(splitter)
        
        # พรีวิวผลลัพธ์
        preview_label = QLabel("พรีวิวผลลัพธ์ (10 แถวแรก):")
        preview_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(preview_label)
        
        self.preview_table = QTableWidget(10, 2)
        self.preview_table.setHorizontalHeaderLabels(["Index", "Value"])
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.preview_table.setMaximumHeight(200)
        # Styling will be applied by Dark Theme
        layout.addWidget(self.preview_table)
        
        # ปุ่มควบคุม
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.preview_btn = QPushButton("🔍 Preview")
        # Styling will be applied by Dark Theme
        
        self.apply_btn = QPushButton("✅ Apply")
        self.apply_btn.setEnabled(False)  # เปิดใช้งานเมื่อ Preview สำเร็จ
        # Styling will be applied by Dark Theme
        
        self.cancel_btn = QPushButton("❌ Cancel")
        # Styling will be applied by Dark Theme
        
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Apply Dark Theme styling
        self.apply_dark_theme()
    
    def setup_connections(self):
        """เชื่อมต่อ signals และ slots"""
        self.preview_btn.clicked.connect(self.preview_expression)
        self.apply_btn.clicked.connect(self.apply_expression)
        self.cancel_btn.clicked.connect(self.reject)
        
        # คลิกสองครั้งที่คอลัมน์เพื่อแทรกชื่อลงในนิพจน์
        self.columns_list.itemDoubleClicked.connect(self.insert_column_name)
        
        # เปลี่ยนชื่อคอลัมน์เมื่อพิมพ์
        self.name_edit.textChanged.connect(self.validate_inputs)
        self.expression_edit.textChanged.connect(self.validate_inputs)
    
    def populate_columns(self):
        """โหลดรายชื่อคอลัมน์ทั้งหมดลงใน ListWidget"""
        self.columns_list.clear()
        
        for col in self.dataframe.columns:
            item = QListWidgetItem(str(col))
            # แสดงข้อมูลเพิ่มเติมสำหรับคอลัมน์
            dtype = str(self.dataframe[col].dtype)
            non_null = self.dataframe[col].notna().sum()
            total = len(self.dataframe[col])
            item.setToolTip(f"Type: {dtype}\nNon-null: {non_null}/{total}")
            self.columns_list.addItem(item)
    
    def insert_column_name(self, item: QListWidgetItem):
        """แทรกชื่อคอลัมน์ลงในนิพจน์โดยครอบด้วย backtick"""
        col_name = item.text()
        # ตรวจสอบว่าชื่อคอลัมน์มีช่องว่างหรือไม่
        if ' ' in col_name or '-' in col_name or '+' in col_name:
            # ถ้ามีอักขระพิเศษ ให้ครอบด้วย backtick
            text_to_insert = f"`{col_name}`"
        else:
            # ถ้าไม่มี ให้ครอบด้วย backtick เพื่อความชัดเจน
            text_to_insert = f"`{col_name}`"
        
        # แทรกข้อความลงในตำแหน่งเคอร์เซอร์ปัจจุบัน
        cursor = self.expression_edit.textCursor()
        cursor.insertText(text_to_insert)
        self.expression_edit.setTextCursor(cursor)
        self.expression_edit.setFocus()
    
    def insert_function(self, func_name: str):
        """แทรกฟังก์ชันลงในนิพจน์"""
        cursor = self.expression_edit.textCursor()
        cursor.insertText(func_name)
        self.expression_edit.setTextCursor(cursor)
        self.expression_edit.setFocus()
    
    def validate_inputs(self):
        """ตรวจสอบความถูกต้องของข้อมูลที่ป้อน"""
        name = self.name_edit.text().strip()
        expression = self.expression_edit.toPlainText().strip()
        
        # ตรวจสอบว่ามีข้อมูลครบถ้วน
        has_name = bool(name)
        has_expression = bool(expression)
        
        # ตรวจสอบชื่อคอลัมน์ซ้ำ
        name_exists = name in self.dataframe.columns if has_name else False
        
        # อัปเดตสถานะปุ่ม
        self.preview_btn.setEnabled(has_name and has_expression and not name_exists)
        
        # แสดงข้อความเตือน
        if has_name and name_exists:
            self.name_edit.setStyleSheet("""
                QLineEdit {
                    padding: 8px;
                    border: 2px solid #dc3545;
                    border-radius: 4px;
                    font-size: 12px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background-color: #f8d7da;
                }
            """)
        else:
            self.name_edit.setStyleSheet("""
                QLineEdit {
                    padding: 8px;
                    border: 2px solid #ddd;
                    border-radius: 4px;
                    font-size: 12px;
                    font-family: 'Segoe UI', Arial, sans-serif;
                }
                QLineEdit:focus {
                    border-color: #007bff;
                }
            """)
    
    def preview_expression(self):
        """พรีวิวผลลัพธ์ของนิพจน์"""
        try:
            # ดึงข้อมูลจาก UI
            expression = self.expression_edit.toPlainText().strip()
            if not expression:
                QMessageBox.warning(self, "คำเตือน", "กรุณาใส่นิพจน์")
                return
            
            # ประเมินนิพจน์
            from processors import evaluate_expression
            result_series = evaluate_expression(self.dataframe, expression)
            
            # เก็บผลลัพธ์สำหรับ Apply
            self.result_series = result_series
            
            # แสดงพรีวิวในตาราง
            self.preview_table.setRowCount(min(10, len(result_series)))
            
            for i in range(min(10, len(result_series))):
                # Index
                index_item = QTableWidgetItem(str(result_series.index[i]))
                index_item.setFlags(index_item.flags() & ~Qt.ItemIsEditable)
                self.preview_table.setItem(i, 0, index_item)
                
                # Value
                value = result_series.iloc[i]
                if pd.isna(value):
                    value_str = "NaN"
                elif np.isinf(value):
                    value_str = "Inf" if value > 0 else "-Inf"
                else:
                    value_str = f"{value:.6g}"
                
                value_item = QTableWidgetItem(value_str)
                value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
                self.preview_table.setItem(i, 1, value_item)
            
            # เปิดใช้งานปุ่ม Apply
            self.apply_btn.setEnabled(True)
            
            # แสดงสถิติพื้นฐาน
            stats_text = f"""
            <b>สถิติผลลัพธ์:</b><br>
            • จำนวนแถว: {len(result_series):,}<br>
            • ค่าเฉลี่ย: {result_series.mean():.6g}<br>
            • ค่าต่ำสุด: {result_series.min():.6g}<br>
            • ค่าสูงสุด: {result_series.max():.6g}<br>
            • ค่า NaN: {result_series.isna().sum():,}
            """
            
            # แสดงข้อความสถิติใน tooltip ของตาราง
            self.preview_table.setToolTip(stats_text)
            
        except Exception as e:
            # แสดงข้อผิดพลาด
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถประเมินนิพจน์ได้:\n{str(e)}")
            
            # ล้างตารางพรีวิว
            self.preview_table.setRowCount(0)
            self.apply_btn.setEnabled(False)
            self.result_series = None
    
    def apply_expression(self):
        """ใช้ผลลัพธ์สร้างคอลัมน์ใหม่ใน DataFrame"""
        if self.result_series is None:
            QMessageBox.warning(self, "คำเตือน", "กรุณา Preview ก่อน")
            return
        
        try:
            # ดึงชื่อคอลัมน์ใหม่
            new_name = self.name_edit.text().strip()
            if not new_name:
                QMessageBox.warning(self, "คำเตือน", "กรุณาใส่ชื่อคอลัมน์ใหม่")
                return
            
            # ตรวจสอบชื่อซ้ำ
            if new_name in self.dataframe.columns:
                reply = QMessageBox.question(
                    self, "ยืนยัน", 
                    f"คอลัมน์ '{new_name}' มีอยู่แล้ว ต้องการแทนที่หรือไม่?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            
            # สร้างคอลัมน์ใหม่
            self.dataframe[new_name] = self.result_series
            
            # แสดงข้อความสำเร็จ
            QMessageBox.information(
                self, "สำเร็จ", 
                f"สร้างคอลัมน์ '{new_name}' เรียบร้อยแล้ว\nจำนวนแถว: {len(self.result_series):,}"
            )
            
            # ปิด dialog
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถสร้างคอลัมน์ได้:\n{str(e)}")
    
    def apply_dark_theme(self):
        """Apply Dark Theme styling to the dialog"""
        dark_theme_qss = """
        /* Main Dialog Background */
        DerivedColumnDialog {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        
        /* QLineEdit - ชื่อคอลัมน์ใหม่ */
        DerivedColumnDialog QLineEdit {
            background-color: #1e1e1e;
            color: #ffffff;
            border: 2px solid #404040;
            border-radius: 4px;
            padding: 8px;
            font-size: 12px;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        DerivedColumnDialog QLineEdit:focus {
            border-color: #007acc;
        }
        DerivedColumnDialog QLineEdit:disabled {
            background-color: #3c3c3c;
            color: #808080;
        }
        
        /* QTextEdit - นิพจน์ */
        DerivedColumnDialog QTextEdit {
            background-color: #1e1e1e;
            color: #ffffff;
            border: 2px solid #404040;
            border-radius: 4px;
            padding: 8px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
        }
        DerivedColumnDialog QTextEdit:focus {
            border-color: #007acc;
        }
        DerivedColumnDialog QTextEdit:disabled {
            background-color: #3c3c3c;
            color: #808080;
        }
        
        /* QListWidget - รายชื่อคอลัมน์ */
        DerivedColumnDialog QListWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #404040;
            border-radius: 4px;
            font-size: 11px;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        DerivedColumnDialog QListWidget::item {
            padding: 6px 8px;
            border-bottom: 1px solid #404040;
            background-color: transparent;
        }
        DerivedColumnDialog QListWidget::item:hover {
            background-color: #007acc;
            color: #ffffff;
        }
        DerivedColumnDialog QListWidget::item:selected {
            background-color: #007acc;
            color: #ffffff;
        }
        DerivedColumnDialog QListWidget::item:selected:active {
            background-color: #0056b3;
        }
        
        /* QTableWidget - พรีวิวผลลัพธ์ */
        DerivedColumnDialog QTableWidget {
            background-color: #1e1e1e;
            color: #dcdcdc;
            border: 1px solid #404040;
            border-radius: 4px;
            gridline-color: #404040;
            font-size: 11px;
            font-family: 'Consolas', 'Monaco', monospace;
        }
        DerivedColumnDialog QTableWidget::item {
            padding: 4px 8px;
            border: none;
            background-color: transparent;
        }
        DerivedColumnDialog QTableWidget::item:selected {
            background-color: #007acc;
            color: #ffffff;
        }
        DerivedColumnDialog QTableWidget::item:alternate {
            background-color: #252525;
        }
        
        /* QHeaderView - หัวตาราง */
        DerivedColumnDialog QHeaderView::section {
            background-color: #333333;
            color: #ffffff;
            padding: 6px 8px;
            border: none;
            border-bottom: 1px solid #404040;
            font-weight: bold;
            font-size: 11px;
        }
        DerivedColumnDialog QHeaderView::section:hover {
            background-color: #404040;
        }
        
        /* QPushButton - ปุ่มฟังก์ชันลัด */
        DerivedColumnDialog QPushButton {
            background-color: #0e639c;
            color: #ffffff;
            border: 1px solid #0e639c;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 11px;
            font-weight: bold;
            font-family: 'Consolas', 'Monaco', monospace;
            min-width: 50px;
        }
        DerivedColumnDialog QPushButton:hover {
            background-color: #1177bb;
            border-color: #1177bb;
        }
        DerivedColumnDialog QPushButton:pressed {
            background-color: #0a4d7a;
            border-color: #0a4d7a;
        }
        
        /* ปุ่ม Preview */
        DerivedColumnDialog QPushButton[text*="Preview"] {
            background-color: #007acc;
            border-color: #007acc;
        }
        DerivedColumnDialog QPushButton[text*="Preview"]:hover {
            background-color: #0088dd;
            border-color: #0088dd;
        }
        DerivedColumnDialog QPushButton[text*="Preview"]:pressed {
            background-color: #0066aa;
            border-color: #0066aa;
        }
        
        /* ปุ่ม Apply */
        DerivedColumnDialog QPushButton[text*="Apply"] {
            background-color: #0e9c57;
            border-color: #0e9c57;
        }
        DerivedColumnDialog QPushButton[text*="Apply"]:hover {
            background-color: #10ad62;
            border-color: #10ad62;
        }
        DerivedColumnDialog QPushButton[text*="Apply"]:pressed {
            background-color: #0c8a4a;
            border-color: #0c8a4a;
        }
        DerivedColumnDialog QPushButton[text*="Apply"]:disabled {
            background-color: #6c757d;
            border-color: #6c757d;
            color: #adb5bd;
        }
        
        /* ปุ่ม Cancel */
        DerivedColumnDialog QPushButton[text*="Cancel"] {
            background-color: #c23c2a;
            border-color: #c23c2a;
        }
        DerivedColumnDialog QPushButton[text*="Cancel"]:hover {
            background-color: #d44330;
            border-color: #d44330;
        }
        DerivedColumnDialog QPushButton[text*="Cancel"]:pressed {
            background-color: #a63525;
            border-color: #a63525;
        }
        
        /* QLabel - ป้ายกำกับ */
        DerivedColumnDialog QLabel {
            color: #ffffff;
            background-color: transparent;
        }
        
        /* QLabel - คำอธิบาย */
        DerivedColumnDialog QLabel[text*="วิธีใช้"] {
            background-color: #2b2b2b;
            border: 1px solid #404040;
            border-radius: 4px;
            padding: 8px;
            color: #dcdcdc;
        }
        
        /* Scrollbars */
        DerivedColumnDialog QScrollBar:vertical {
            background-color: #2b2b2b;
            width: 12px;
            border-radius: 6px;
        }
        DerivedColumnDialog QScrollBar::handle:vertical {
            background-color: #555555;
            border-radius: 6px;
            min-height: 20px;
        }
        DerivedColumnDialog QScrollBar::handle:vertical:hover {
            background-color: #666666;
        }
        DerivedColumnDialog QScrollBar::add-line:vertical,
        DerivedColumnDialog QScrollBar::sub-line:vertical {
            height: 0px;
        }
        
        DerivedColumnDialog QScrollBar:horizontal {
            background-color: #2b2b2b;
            height: 12px;
            border-radius: 6px;
        }
        DerivedColumnDialog QScrollBar::handle:horizontal {
            background-color: #555555;
            border-radius: 6px;
            min-width: 20px;
        }
        DerivedColumnDialog QScrollBar::handle:horizontal:hover {
            background-color: #666666;
        }
        DerivedColumnDialog QScrollBar::add-line:horizontal,
        DerivedColumnDialog QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        
        /* Selection colors */
        DerivedColumnDialog QLineEdit::selection,
        DerivedColumnDialog QTextEdit::selection {
            background-color: #264f78;
            color: #ffffff;
        }
        """
        
        # Apply the dark theme styling
        self.setStyleSheet(dark_theme_qss)
