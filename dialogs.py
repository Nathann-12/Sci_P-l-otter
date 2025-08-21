# dialogs.py
from __future__ import annotations
from typing import Iterable, Dict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QFormLayout, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QListWidget, QListWidgetItem, QTableView, QCheckBox
)
from PySide6 import QtCore  # UI-REFINE: สำหรับ PandasModel
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas  # UI-FIT: preview canvas
from matplotlib.figure import Figure  # UI-FIT
import numpy as np
import pandas as pd


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

        # Preview table
        self.tbl = QTableView(self)
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
            # groupby preview
            df = self._df
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
            self.ax.legend(loc="best"); self.fig.tight_layout(); self.canvas.draw()
        except Exception:
            self.ax.clear(); self.canvas.draw()