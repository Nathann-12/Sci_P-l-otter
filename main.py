# -*- coding: utf-8 -*-
import os, sys
import numpy as np
import pandas as pd

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QDockWidget, QMessageBox, QSpinBox, QCheckBox,
    QDialog, QInputDialog
)

# Matplotlib (ฝังใน Qt)
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib
from matplotlib.figure import Figure

# ฟอนต์ไทย
matplotlib.rcParams["font.sans-serif"] = ["Tahoma", "Noto Sans Thai", "Arial", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

# ไลบรารีวิทยาศาสตร์ (ถ้ามี)
try:
    import xarray as xr   # สำหรับ NetCDF (.nc) หรือบาง .cdf
except Exception:
    xr = None

try:
    import cdflib         # สำหรับ NASA CDF (.cdf)
except Exception:
    cdflib = None

APP_TITLE = "SciPlotter (On‑Demand CDF/NetCDF)"

# ---------------- Dialog: slice มิติ ----------------
class MultiDimSliceDialog(QDialog):
    def __init__(self, parent, var_name, dims, shape):
        super().__init__(parent)
        self.setWindowTitle(f"เลือก slice สำหรับ {var_name}")
        self.resize(450, 400)

        layout = QVBoxLayout(self)
        
        # คำอธิบาย
        for text in [
            f"ตัวแปร: {var_name}",
            f"มิติ: {list(dims)}",
            f"ขนาด: {list(shape)}",
            "เลือกมิติที่ต้องการให้เป็นแกนหลัก (ยาว) และใส่ index สำหรับมิติอื่น ๆ\n"
            "เช่น var(time, lat, lon) → เลือก time เป็นแกนหลัก แล้วใส่ index ของ lat/lon"
        ]:
            lab = QLabel(text)
            lab.setWordWrap(True)
            layout.addWidget(lab)

        # เลือกมิติหลัก
        layout.addWidget(QLabel("เลือกมิติที่ต้องการให้เป็นแกนหลัก (ยาว):"))
        self.primary_dim_combo = QComboBox()
        for dim in dims:
            self.primary_dim_combo.addItem(f"{dim} (ขนาด: {shape[dims.index(dim)]})")
        layout.addWidget(self.primary_dim_combo)

        # แยกเส้น
        line = QLabel()
        line.setFrameStyle(QLabel.HLine | QLabel.Sunken)
        layout.addWidget(line)

        # Spin boxes สำหรับมิติอื่น ๆ
        layout.addWidget(QLabel("ใส่ index สำหรับมิติอื่น ๆ:"))
        self.index_boxes = {}
        for i, (dim, size) in enumerate(zip(dims, shape)):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{dim} (0–{size-1}):"))
            sb = QSpinBox()
            sb.setRange(0, max(0, size-1))
            sb.setValue(0)
            self.index_boxes[dim] = sb
            row.addWidget(sb)
            
            # ปิดการใช้งานมิติหลัก
            if i == 0:  # มิติแรกเป็น default
                sb.setEnabled(False)
            
            layout.addLayout(row)

        # เชื่อมต่อการเปลี่ยนแปลงมิติหลัก
        self.primary_dim_combo.currentIndexChanged.connect(self._on_primary_dim_changed)

        # ปุ่ม
        rowb = QHBoxLayout()
        btnOk = QPushButton("ตกลง")
        btnCancel = QPushButton("ยกเลิก")
        btnOk.clicked.connect(self.accept)
        btnCancel.clicked.connect(self.reject)
        rowb.addStretch(1)
        rowb.addWidget(btnCancel)
        rowb.addWidget(btnOk)
        layout.addLayout(rowb)

    def _on_primary_dim_changed(self, index):
        """เมื่อเปลี่ยนมิติหลัก ให้ปิดการใช้งาน spin box ของมิตินั้น"""
        for i, (dim, sb) in enumerate(self.index_boxes.items()):
            if i == index:
                sb.setEnabled(False)
                sb.setValue(0)  # รีเซ็ตค่า
            else:
                sb.setEnabled(True)

    def get_primary_dim(self):
        """คืนค่ามิติหลักที่เลือก"""
        return list(self.index_boxes.keys())[self.primary_dim_combo.currentIndex()]

    def get_indices(self):
        """คืนค่า indices สำหรับมิติที่ไม่ใช่หลัก (มิติหลักจะถูก slice ทั้งหมด)"""
        return {dim: sb.value() for dim, sb in self.index_boxes.items()}

# ---------------- Canvas กราฟ ----------------
class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.fig.tight_layout()

    def clear(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout()
        self.draw()

# ---------------- Main Window ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 760)
        self._df = None
        self._current_path = None

        # Central
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        self.canvas = PlotCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, self)
        v.addWidget(self.toolbar)
        v.addWidget(self.canvas)

        # UI
        self._init_controls()
        self._init_menu()

        self.statusBar().showMessage("พร้อมใช้งาน • เปิดไฟล์ → เลือกตัวแปรแบบ On‑Demand • รองรับ CSV/XLSX/NC/CDF")
        self.setAcceptDrops(True)

    # ---------- Helpers ----------
    def _cdf_to_datetime(self, arr):
        """แปลง CDF Epoch/TT2000 เป็น datetime (ถ้าได้)"""
        try:
            return cdflib.cdfepoch.to_datetime(arr)
        except Exception:
            return arr

    def _cdf_var_names(self, cdf):
        """ดึงชื่อทุกตัวแปรจาก CDF (รองรับรูปแบบ object/dict)"""
        info = cdf.cdf_info()
        if hasattr(info, "zVariables") or hasattr(info, "rVariables"):
            zvars = getattr(info, "zVariables", []) or []
            rvars = getattr(info, "rVariables", []) or []
        else:
            # เผื่อเป็น dict-like
            zvars = info.get("zVariables", []) or []
            rvars = info.get("rVariables", []) or []
        return sorted(set(list(zvars) + list(rvars)))

    # ---------- UI ----------
    def _init_controls(self):
        dock = QDockWidget("แผงควบคุม", self)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        panel = QWidget()
        dock.setWidget(panel)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)

        layout = QVBoxLayout(panel)

        self.lblFile = QLabel("ยังไม่ได้เปิดไฟล์")
        self.lblFile.setWordWrap(True)
        layout.addWidget(self.lblFile)

        self.btnLoadCols = QPushButton("โหลดคอลัมน์จากข้อมูล")
        self.btnLoadCols.setToolTip("กดหลังจากเปิดไฟล์ (หรือเลือกตัวแปรแล้ว) เพื่อดึงคอลัมน์มาใส่ X/Y")
        layout.addWidget(self.btnLoadCols)

        layout.addWidget(QLabel("เลือกคอลัมน์แกน X"))
        self.cbX = QComboBox()
        layout.addWidget(self.cbX)

        layout.addWidget(QLabel("เลือกคอลัมน์แกน Y"))
        self.cbY = QComboBox()
        layout.addWidget(self.cbY)

        styleRow = QHBoxLayout()
        styleRow.addWidget(QLabel("ความหนาเส้น"))
        self.spLineWidth = QSpinBox()
        self.spLineWidth.setRange(1, 10)
        self.spLineWidth.setValue(2)
        styleRow.addWidget(self.spLineWidth)
        layout.addLayout(styleRow)

        markerRow = QHBoxLayout()
        self.chkMarker = QCheckBox("แสดงจุดข้อมูล")
        self.chkMarker.setChecked(False)
        markerRow.addWidget(self.chkMarker)
        markerRow.addStretch(1)
        layout.addLayout(markerRow)

        btnRow = QHBoxLayout()
        self.btnLine = QPushButton("แสดงกราฟเส้น")
        self.btnScatter = QPushButton("แสดงกราฟจุด (Scatter)")
        btnRow.addWidget(self.btnLine)
        btnRow.addWidget(self.btnScatter)
        layout.addLayout(btnRow)

        otherRow = QHBoxLayout()
        self.btnClear = QPushButton("ล้างกราฟ")
        self.btnExport = QPushButton("บันทึกรูปภาพ (PNG)")
        otherRow.addWidget(self.btnClear)
        otherRow.addWidget(self.btnExport)
        layout.addLayout(otherRow)

        layout.addStretch(1)

        # signals
        self.btnLoadCols.clicked.connect(self.load_columns_from_df)
        self.btnLine.clicked.connect(self.plot_line)
        self.btnScatter.clicked.connect(self.plot_scatter)
        self.btnClear.clicked.connect(self.clear_plot)
        self.btnExport.clicked.connect(self.export_png)

    def _init_menu(self):
        m = self.menuBar()
        fileMenu = m.addMenu("&ไฟล์")
        actOpen = fileMenu.addAction("เปิดข้อมูล (CSV/XLSX/NC/CDF)...")
        actOpen.triggered.connect(self.open_file)
        fileMenu.addSeparator()
        actExport = fileMenu.addAction("บันทึกรูปภาพ (PNG)...")
        actExport.triggered.connect(self.export_png)
        fileMenu.addSeparator()
        actExit = fileMenu.addAction("ออกจากโปรแกรม")
        actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&มุมมอง")
        actReset = viewMenu.addAction("รีเซ็ตมุมมองกราฟ")
        actReset.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True),
                                            self.canvas.ax.set_ylim(auto=True),
                                            self.canvas.draw()])

        helpMenu = m.addMenu("&ช่วยเหลือ")
        actAbout = helpMenu.addAction("เกี่ยวกับโปรแกรม")
        actAbout.triggered.connect(self.show_about)

    # ---------- Open / Load ----------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "เลือกไฟล์ข้อมูล", "",
            "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf);;All Files (*.*)"
        )
        if not path:
            return
        self.load_data(path)

    def load_columns_from_df(self):
        if self._df is None:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์หรือเลือกตัวแปรก่อน จากนั้นค่อยกด 'โหลดคอลัมน์'")
            return
        cols = [str(c) for c in self._df.columns]
        self.cbX.clear()
        self.cbY.clear()
        self.cbX.addItems(cols)
        self.cbY.addItems(cols)
        self.statusBar().showMessage("โหลดคอลัมน์เรียบร้อย • เลือก X/Y แล้วพล็อตได้")

    def load_data(self, path: str):
        try:
            ext = os.path.splitext(path)[1].lower()

            # ตารางทั่วไป
            if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
                df, enc_note = self._load_tabular(path, ext)
                if df is None or df.empty:
                    raise ValueError("อ่านไฟล์ตารางไม่สำเร็จหรือไฟล์ว่าง")
                self._df = df
                self._current_path = path
                self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (ตาราง) • {enc_note}")
                self.statusBar().showMessage("โหลดข้อมูลสำเร็จ (ตาราง) • กด 'โหลดคอลัมน์'")
                return

            # CDF/NetCDF แบบ On‑Demand (ถามเฉพาะตัวแปรที่จะใช้)
            if ext in [".nc", ".cdf"]:
                df = self._load_cdf_nc_on_demand(path)
                if df is None or df.empty:
                    raise ValueError("อ่านไฟล์ CDF/NetCDF ไม่สำเร็จ หรือไม่มีตัวแปรที่ใช้พล็อตได้")
                self._df = df
                self._current_path = path
                self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (CDF/NetCDF)")
                self.statusBar().showMessage("โหลดข้อมูลสำเร็จ (On‑Demand) • กด 'โหลดคอลัมน์'")
                return

            raise ValueError("นามสกุลไฟล์ไม่รองรับ")

        except Exception as e:
            QMessageBox.critical(self, "เปิดไฟล์ไม่สำเร็จ", f"สาเหตุ: {e}")
            self.statusBar().showMessage("เกิดข้อผิดพลาดในการเปิดไฟล์")

    # ---------- Readers ----------
    def _load_tabular(self, path, ext):
        enc_used = ""
        if ext == ".xlsx":
            df = pd.read_excel(path)
            enc_used = "binary/xlsx"
            return df, enc_used

        if ext == ".tsv":
            df = pd.read_csv(path, sep="\t")
            enc_used = "utf-8 (tsv)"
            return df, enc_used

        # เดา encoding/delimiter ยอดฮิต
        def read_text_with_guess(p):
            candidates = [
                ("utf-8", None),
                ("utf-8-sig", None),
                ("cp874", None),
                ("tis-620", None),
            ]
            last_err = None
            for enc, sep in candidates:
                try:
                    if sep is None:
                        try:
                            df = pd.read_csv(p, encoding=enc)
                        except Exception:
                            try:
                                df = pd.read_csv(p, encoding=enc, sep=";")
                            except Exception:
                                df = pd.read_csv(p, encoding=enc, sep="\t")
                    else:
                        df = pd.read_csv(p, encoding=enc, sep=sep)
                    return df, enc
                except Exception as e:
                    last_err = e
            raise last_err if last_err else ValueError("อ่านไฟล์ไม่สำเร็จ")

        df, used_enc = read_text_with_guess(path)
        return df, used_enc

    def _load_cdf_nc_on_demand(self, path):
        """
        เปิด .cdf/.nc แบบ On‑Demand:
        - ให้เลือก Y ก่อน
        - X พยายามใช้ Epoch/time อัตโนมัติ (ถ้าไม่มีจะให้เลือก)
        - ถ้า Y เป็นหลายมิติ ค่อยถาม slice เฉพาะตัวแปรนั้น
        """
        # ---- 1) ลอง NetCDF ผ่าน xarray (บาง .cdf จริง ๆ เป็น NetCDF) ----
        if xr is not None:
            try:
                ds = xr.open_dataset(path)  # ให้ xarray เดา engine เอง
                var_names = list(ds.variables)

                # สร้าง pool
                x_pool = [v for v in var_names if v.lower().startswith("epoch") or v.lower().startswith("time")]
                y_pool = [v for v in var_names if v not in x_pool]
                if not y_pool:
                    ds.close()
                    raise ValueError("ไม่พบตัวแปรสำหรับ Y ในไฟล์ NetCDF")

                # เลือก Y
                y_name, ok = QInputDialog.getItem(self, "เลือกตัวแปร Y (NetCDF)", "ตัวแปร Y:", y_pool, 0, False)
                if not ok:
                    ds.close()
                    return None

                # เลือก X
                if x_pool:
                    x_name = x_pool[0]
                else:
                    x_name, ok = QInputDialog.getItem(self, "เลือกตัวแปร X (NetCDF)", "ตัวแปร X:", var_names, 0, False)
                    if not ok:
                        ds.close()
                        return None

                # ดึงค่า X/Y
                x_vals = ds[x_name].values
                da_y = ds[y_name]
                if da_y.ndim == 1:
                    y_vals = da_y.values
                else:
                    dims = list(da_y.dims)
                    shape = da_y.shape
                    dlg = MultiDimSliceDialog(self, y_name, dims, shape)
                    if dlg.exec() != QDialog.Accepted:
                        ds.close()
                        return None
                    
                    # ใช้มิติหลักและ indices เพื่อสร้าง slice ที่ถูกต้อง
                    primary_dim = dlg.get_primary_dim()
                    idxs = dlg.get_indices()
                    
                    # สร้าง slice tuple: มิติหลักใช้ : (ทั้งหมด) มิติอื่นใช้ index ที่เลือก
                    slice_list = []
                    for dim in dims:
                        if dim == primary_dim:
                            slice_list.append(slice(None))  # ใช้ทั้งหมด
                        else:
                            slice_list.append(idxs.get(dim, 0))
                    
                    y_vals = da_y.values[tuple(slice_list)]
                    if np.ndim(y_vals) != 1:
                        ds.close()
                        raise ValueError("ยังไม่ได้ slice ให้เป็น 1 มิติ")

                n = min(len(x_vals), len(y_vals))
                df = pd.DataFrame({str(x_name): x_vals[:n], str(y_name): y_vals[:n]})
                ds.close()
                return df
            except Exception:
                pass  # ไปลอง cdflib ต่อ

        # ---- 2) CDF ผ่าน cdflib ----
        if cdflib is None:
            raise RuntimeError("ยังไม่ได้ติดตั้ง cdflib")

        cdf = cdflib.CDF(path)
        names = self._cdf_var_names(cdf)
        if not names:
            raise ValueError("ไม่พบตัวแปรในไฟล์ CDF")

        # หา X ที่เป็นเวลา
        x_pool = [v for v in names if v.lower().startswith("epoch") or v.lower().startswith("time")]
        y_pool = [v for v in names if v not in x_pool]
        if not y_pool:
            raise ValueError("ไม่พบตัวแปรสำหรับ Y ในไฟล์ CDF")

        # เลือก Y ก่อน
        y_name, ok = QInputDialog.getItem(self, "เลือกตัวแปร Y (CDF)", "ตัวแปร Y:", y_pool, 0, False)
        if not ok:
            return None

        # เลือก X
        if x_pool:
            x_name = x_pool[0]
        else:
            x_name, ok = QInputDialog.getItem(self, "เลือกตัวแปร X (CDF)", "ตัวแปร X:", names, 0, False)
            if not ok:
                return None

        # อ่าน X
        x_vals = np.array(cdf.varget(x_name))
        x_vals = self._cdf_to_datetime(x_vals)

        # อ่าน Y (+ จัดการหลายมิติ)
        y_vals = np.array(cdf.varget(y_name))
        if y_vals.ndim == 1:
            pass
        elif y_vals.ndim == 2 and y_vals.shape[-1] in (3,):
            comp, ok = QInputDialog.getItem(self, f"เลือกแกนของ {y_name}", "องค์ประกอบเวกเตอร์:", ["X(0)", "Y(1)", "Z(2)"], 2, False)
            if not ok:
                return None
            idx = int(comp[-2])
            y_vals = y_vals[:, idx]
            y_name = f"{y_name}[{idx}]"
        elif y_vals.ndim > 1:
            dims = list(range(y_vals.ndim))
            shape = y_vals.shape
            dlg = MultiDimSliceDialog(self, y_name, dims, shape)
            if dlg.exec() != QDialog.Accepted:
                return None
            
            # ใช้มิติหลักและ indices เพื่อสร้าง slice ที่ถูกต้อง
            primary_dim = dlg.get_primary_dim()
            idxs = dlg.get_indices()
            
            # สร้าง slice tuple: มิติหลักใช้ : (ทั้งหมด) มิติอื่นใช้ index ที่เลือก
            slice_list = []
            for dim in dims:
                if dim == primary_dim:
                    slice_list.append(slice(None))  # ใช้ทั้งหมด
                else:
                    slice_list.append(idxs.get(dim, 0))
            
            y_vals = y_vals[tuple(slice_list)]
            if np.ndim(y_vals) != 1:
                raise ValueError("ยังไม่ได้ slice ให้เป็น 1 มิติ")

        n = min(len(x_vals), len(y_vals))
        df = pd.DataFrame({str(x_name): x_vals[:n], str(y_name): y_vals[:n]})
        return df

    # ---------- Plot ----------
    def _get_xy(self):
        if self._df is None:
            QMessageBox.warning(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'")
            return None, None
        if self.cbX.count() == 0 or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่ได้โหลดคอลัมน์", "โปรดกดปุ่ม 'โหลดคอลัมน์จากข้อมูล' แล้วเลือก X/Y")
            return None, None

        x_col = self.cbX.currentText()
        y_col = self.cbY.currentText()
        if x_col not in self._df.columns or y_col not in self._df.columns:
            QMessageBox.warning(self, "คอลัมน์ไม่ถูกต้อง", "โปรดเลือกคอลัมน์ X/Y ใหม่")
            return None, None

        x = self._df[x_col].values
        y = self._df[y_col].values

        # พยายามแปลงเป็นตัวเลข (ยกเว้น datetime)
        if not np.issubdtype(type(x[0]), np.datetime64):
            try:
                x = pd.to_numeric(x, errors="coerce")
            except Exception:
                pass
        try:
            y = pd.to_numeric(y, errors="coerce")
        except Exception:
            pass

        mask = ~(pd.isna(x) | pd.isna(y))
        x = x[mask]
        y = y[mask]
        return x, y

    def plot_line(self):
        x, y = self._get_xy()
        if x is None:
            return
        lw = self.spLineWidth.value()
        marker = "o" if self.chkMarker.isChecked() else None
        self.canvas.ax.plot(x, y, linewidth=lw, marker=marker, label=f"{self.cbY.currentText()} vs {self.cbX.currentText()}")
        self.canvas.ax.set_xlabel(self.cbX.currentText())
        self.canvas.ax.set_ylabel(self.cbY.currentText())
        self.canvas.ax.legend(loc="best")
        self.canvas.fig.tight_layout()
        self.canvas.draw()
        self.statusBar().showMessage("พล็อตกราฟเส้นสำเร็จ")

    def plot_scatter(self):
        x, y = self._get_xy()
        if x is None:
            return
        size = self.spLineWidth.value() * 5
        self.canvas.ax.scatter(x, y, s=size, label=f"{self.cbY.currentText()} vs {self.cbX.currentText()}")
        self.canvas.ax.set_xlabel(self.cbX.currentText())
        self.canvas.ax.set_ylabel(self.cbY.currentText())
        self.canvas.ax.legend(loc="best")
        self.canvas.fig.tight_layout()
        self.canvas.draw()
        self.statusBar().showMessage("พล็อตกราฟจุดสำเร็จ")

    def clear_plot(self):
        self.canvas.clear()
        self.statusBar().showMessage("ล้างกราฟแล้ว")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "บันทึกรูปภาพเป็น", "plot.png", "PNG Image (*.png)")
        if not path:
            return
        try:
            self.canvas.fig.savefig(path, dpi=300, bbox_inches="tight")
            self.statusBar().showMessage(f"บันทึกรูปภาพแล้ว: {path}")
        except Exception as e:
            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def show_about(self):
        QMessageBox.information(
            self, "เกี่ยวกับโปรแกรม",
            "SciPlotter (On‑Demand)\n"
            "เปิดไฟล์ → เลือกตัวแปรแบบ On‑Demand → กด 'โหลดคอลัมน์' → พล็อต\n"
            "รองรับ CSV/TSV/TXT/XLSX/NetCDF(.nc)/CDF(.cdf)"
        )

    # Drag & Drop
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self.load_data(path)
                break

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
