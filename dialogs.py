# dialogs.py
from __future__ import annotations
from typing import Iterable, Dict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QFormLayout, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView
)
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