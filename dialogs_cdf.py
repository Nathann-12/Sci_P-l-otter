# dialogs_cdf.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QGridLayout,
    QSpinBox, QPushButton, QHBoxLayout, QMessageBox
)

from file_io import (
    inspect_cdf_istp, slice_cdf_istp,
    inspect_netcdf, slice_netcdf,
    read_cdf_quick, read_netcdf_quick
)


class CDFSliceDialog(QDialog):
    """
    Dialog เลือก Data/Time variable และ index มิติอื่น ๆ
    ใช้ได้ทั้ง CDF (kind='cdf') และ NetCDF (kind='nc')
    รองรับ fallback: ถ้า inspect พัง จะดึงคอลัมน์จาก DataFrame มาให้เลือกแทน
    """
    def __init__(self, path: Path, kind: str = "cdf", parent=None):
        super().__init__(parent)
        self.path = path
        self.kind = kind  # 'cdf' | 'nc'

        self.setWindowTitle("Select CDF slice" if kind == "cdf" else "Select NetCDF slice")
        self.resize(560, 280)

        self.info: Dict[str, Any] = {}
        self.index_spins: Dict[str, QSpinBox] = {}
        self.fallback_mode: bool = False
        self.fallback_df: pd.DataFrame | None = None
        self.fallback_meta: Dict[str, Any] = {}

        # UI
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Data variable:"))
        self.comboData = QComboBox(self)
        layout.addWidget(self.comboData)

        layout.addWidget(QLabel("Time variable:"))
        self.comboTime = QComboBox(self)
        layout.addWidget(self.comboTime)

        layout.addWidget(QLabel("Indices for extra axes (if any):"))
        self.grid = QGridLayout()
        layout.addLayout(self.grid)

        hl = QHBoxLayout()
        self.btnOk = QPushButton("OK", self)
        self.btnCancel = QPushButton("Cancel", self)
        hl.addStretch(1)
        hl.addWidget(self.btnOk)
        hl.addWidget(self.btnCancel)
        layout.addLayout(hl)

        self.btnOk.clicked.connect(self.accept)
        self.btnCancel.clicked.connect(self.reject)

        # โหลดข้อมูล
        self._load_info()
        self.comboData.currentTextChanged.connect(self._rebuild_indices)

    # ---------- internal ----------
    def _clear_grid(self):
        # ล้างวิดเจ็ตเก่า ๆ ใน grid อย่างปลอดภัย
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.index_spins.clear()

    def _load_info(self):
        """
        พยายาม inspect ก่อน ถ้าไม่ได้ ให้ fallback อ่าน DataFrame แล้วเดา
        """
        try:
            if self.kind == "cdf":
                self.info = inspect_cdf_istp(self.path)  # อาจโยน error
            else:
                self.info = inspect_netcdf(self.path)

            data_vars = self.info.get("data_vars", [])
            time_vars = self.info.get("time_candidates", [])
            if not data_vars or not time_vars:
                raise RuntimeError("inspect คืนลิสต์ว่าง")

            # เติม dropdown
            self.comboData.clear()
            self.comboTime.clear()
            self.comboData.addItems([str(x) for x in data_vars])
            self.comboTime.addItems([str(x) for x in time_vars])
            self.fallback_mode = False
            self._rebuild_indices()
            return

        except Exception as e_ins:
            # -------- Fallback: ใช้ DataFrame ช่วยเดา --------
            try:
                if self.kind == "cdf":
                    df, meta = read_cdf_quick(self.path)
                else:
                    df, meta = read_netcdf_quick(self.path)
            except Exception as e_quick:
                QMessageBox.critical(
                    self, "Open error",
                    f"วิเคราะห์ไฟล์ไม่สำเร็จ:\n- inspect: {e_ins}\n- quick: {e_quick}"
                )
                self.reject()
                return

            self.fallback_mode = True
            self.fallback_df = df
            self.fallback_meta = meta

            cols = list(map(str, df.columns))
            # time-like: dtype เป็น datetime หรือชื่อมี time/epoch/utc
            time_like: list[str] = []
            for c in cols:
                s = df[c]
                if np.issubdtype(s.dtype, np.datetime64):
                    time_like.append(c)
                elif any(k in c.lower() for k in ("time", "epoch", "utc")):
                    time_like.append(c)
            if not time_like:
                time_like = cols[:]  # ให้เลือกอะไรก็ได้

            self.comboData.clear()
            self.comboTime.clear()
            self.comboData.addItems(cols)
            self.comboTime.addItems(time_like)
            # fallback ไม่มีมิติเพิ่มเติม
            self._clear_grid()

    def _rebuild_indices(self):
        self._clear_grid()
        if self.fallback_mode:
            return  # ไม่มี index ให้เลือก

        var = self.comboData.currentText()
        shapes = self.info.get("var_shape", {})
        shape = shapes.get(var, ())

        # แสดงสปินสำหรับ DEPEND_1.. ตามจำนวนมิติ (ข้ามแกนเวลา DEPEND_0)
        # หมายเหตุ: ไม่รู้แน่ชัดว่าแกนไหนคือเวลาในทุกไฟล์ จึงให้ผู้ใช้กรอก index สำหรับแกนอื่น
        # เริ่มที่ 1 ไปจนถึง len(shape)-1
        for i in range(1, max(1, len(shape))):
            lab = f"DEPEND_{i}"
            spin = QSpinBox(self)
            spin.setMinimum(0)
            # ถ้าทราบขนาดมิติ i ให้ตั้ง max = size-1 ไม่งั้นปล่อย 0
            if i < len(shape):
                spin.setMaximum(max(0, int(shape[i]) - 1))
            else:
                spin.setMaximum(0)
            self.grid.addWidget(QLabel(lab, self), i - 1, 0)
            self.grid.addWidget(spin, i - 1, 1)
            self.index_spins[lab] = spin

    # ---------- public ----------
    def get_slice(self):
        """
        คืน (df, meta)
        - ปกติ: slice ตามตัวแปร/เวลา/ดัชนีที่เลือก
        - fallback: คืน DataFrame ทั้งก้อน ให้ไปเลือก X/Y ในหน้าหลักต่อ
        """
        if self.fallback_mode:
            # ส่งคืนทั้ง DataFrame เพื่อให้ใช้งานต่อได้เลย
            meta = dict(self.fallback_meta)
            meta["note"] = "fallback: used quick DataFrame (inspect failed)"
            return self.fallback_df.copy(), meta

        data_var = self.comboData.currentText()
        time_var = self.comboTime.currentText()
        index_map: Dict[str, int] = {k: w.value() for k, w in self.index_spins.items()}

        if self.kind == "cdf":
            return slice_cdf_istp(self.path, data_var, time_var, index_map)
        else:
            return slice_netcdf(self.path, data_var, time_var, index_map)
