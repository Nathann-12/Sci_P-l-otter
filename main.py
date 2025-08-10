# main.py
import os, sys
import numpy as np
import pandas as pd

from PySide6 import QtGui
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QDockWidget, QMessageBox, QSpinBox, QCheckBox, QDialog,
    QListWidget, QListWidgetItem, QToolBar, QInputDialog
)
from PySide6.QtGui import QAction

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor, RectangleSelector
import matplotlib
matplotlib.rcParams["font.sans-serif"] = ["Tahoma", "Noto Sans Thai", "Arial", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from loaders import load_tabular, load_cdf_nc_on_demand
from dialogs import MultiDimSliceDialog, ColumnTypeDialog
from processors import add_time_bangkok, add_magnitude, add_moving_average, apply_column_types, compute_fft

APP_TITLE = "SciPlotter (Modular + Features)"

class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig); self.setParent(parent)
        self.fig.tight_layout()
    def clear(self):
        self.fig.clf(); self.ax = self.fig.add_subplot(111); self.fig.tight_layout(); self.draw()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE); self.resize(1180, 760)
        self._df = None; self._current_path = None
        self._datasets = {}   # dict: key = ชื่อที่โชว์ในลิสต์, value = {"df": DataFrame, "path": str}
        self._cursor = None
        self._cid_motion = None   # id ของ event handler mouse move
        self._rs = None           # RectangleSelector (ใช้ใน Box Zoom)
        self._fft_df = None   # เก็บผล FFT ล่าสุด
        self._fft_meta = {}   # meta: fs, x_col, y_col, window, detrend

        central = QWidget(); self.setCentralWidget(central)
        v = QVBoxLayout(central)
        self.canvas = PlotCanvas(self); self.toolbar = NavigationToolbar(self.canvas, self)
        v.addWidget(self.toolbar); v.addWidget(self.canvas)

        self._init_controls(); self._init_menu()
        
        # สร้างทูลบาร์ด้านบน (ข้าง ๆ ปุ่มมุมมอง)
        self.tb = QToolBar("ฟีเจอร์", self)
        self.addToolBar(self.tb)

        # ปุ่ม FFT
        self.actFFT = QAction("FFT", self)
        self.actFFT.setToolTip("คำนวณฟูเรียร์ทรานส์ฟอร์มของคอลัมน์ Y กับแกน X ปัจจุบัน")
        self.tb.addAction(self.actFFT)

        # ปุ่มส่งออกผล FFT
        self.actExportFFT = QAction("Export FFT", self)
        self.actExportFFT.setToolTip("ส่งออกผล FFT เป็นไฟล์ (CSV/Excel/NetCDF)")
        self.tb.addAction(self.actExportFFT)

        # เชื่อมสัญญาณ
        self.actFFT.triggered.connect(self.run_fft_dialog)
        self.actExportFFT.triggered.connect(self.export_fft_dialog)
        
        self.statusBar().showMessage("พร้อมใช้งาน • เปิดไฟล์ → (ถ้า .cdf/.nc จะให้เลือกตัวแปรแบบ On‑Demand) • กด 'โหลดคอลัมน์'")

        self.setAcceptDrops(True)

    def _init_controls(self):
        dock = QDockWidget("แผงควบคุม", self)
        dock.setAllowedAreas(QtGui.Qt.LeftDockWidgetArea | QtGui.Qt.RightDockWidgetArea)
        panel = QWidget(); dock.setWidget(panel); self.addDockWidget(QtGui.Qt.LeftDockWidgetArea, dock)
        layout = QVBoxLayout(panel)

        self.lblFile = QLabel("ยังไม่ได้เปิดไฟล์"); self.lblFile.setWordWrap(True); layout.addWidget(self.lblFile)

        # ปุ่มโหลดคอลัมน์
        self.btnLoadCols = QPushButton("โหลดคอลัมน์จากข้อมูล"); layout.addWidget(self.btnLoadCols)

        layout.addWidget(QLabel("เลือกคอลัมน์แกน X")); self.cbX = QComboBox(); layout.addWidget(self.cbX)
        layout.addWidget(QLabel("เลือกคอลัมน์แกน Y")); self.cbY = QComboBox(); layout.addWidget(self.cbY)

        styleRow = QHBoxLayout()
        styleRow.addWidget(QLabel("ความหนาเส้น"))
        self.spLineWidth = QSpinBox(); self.spLineWidth.setRange(1,10); self.spLineWidth.setValue(2)
        styleRow.addWidget(self.spLineWidth); layout.addLayout(styleRow)

        markerRow = QHBoxLayout()
        self.chkMarker = QCheckBox("แสดงจุดข้อมูล"); self.chkMarker.setChecked(False)
        markerRow.addWidget(self.chkMarker); markerRow.addStretch(1); layout.addLayout(markerRow)

        btnRow = QHBoxLayout()
        self.btnLine = QPushButton("แสดงกราฟเส้น"); self.btnScatter = QPushButton("แสดงกราฟจุด (Scatter)")
        btnRow.addWidget(self.btnLine); btnRow.addWidget(self.btnScatter); layout.addLayout(btnRow)

        # ---- ฟีเจอร์ใหม่ ----
        layout.addWidget(QLabel("ฟีเจอร์เสริม"))
        featRow1 = QHBoxLayout()
        self.btnTZ = QPushButton("เพิ่มคอลัมน์เวลา +7h (Bangkok)")
        self.btnMag = QPushButton("เพิ่มคอลัมน์ |B| จาก 3 แกน")
        featRow1.addWidget(self.btnTZ); featRow1.addWidget(self.btnMag)
        layout.addLayout(featRow1)

        featRow2 = QHBoxLayout()
        self.btnMA = QPushButton("เพิ่มคอลัมน์ Moving Average (จาก Y)")
        featRow2.addWidget(self.btnMA); layout.addLayout(featRow2)

        # ใต้ส่วนที่สร้างปุ่มฟีเจอร์เสริม
        layout.addWidget(QLabel("การจัดรูปแบบข้อมูล"))
        featRow3 = QHBoxLayout()
        self.btnTypes = QPushButton("กำหนดชนิดคอลัมน์")
        featRow3.addWidget(self.btnTypes)
        layout.addLayout(featRow3)

        otherRow = QHBoxLayout()
        self.btnClear = QPushButton("ล้างกราฟ"); self.btnExport = QPushButton("บันทึกรูปภาพ (PNG)")
        otherRow.addWidget(self.btnClear); otherRow.addWidget(self.btnExport); layout.addLayout(otherRow)

        exportRow2 = QHBoxLayout()
        self.btnExportRange = QPushButton("ส่งออกช่วงที่เห็น (CSV)")
        exportRow2.addWidget(self.btnExportRange)
        layout.addLayout(exportRow2)

        # ----- จัดการหลายไฟล์ (Staging) -----
        layout.addWidget(QLabel("ไฟล์ที่เตรียมไว้"))

        # รายการไฟล์
        self.lstFiles = QListWidget()
        self.lstFiles.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.lstFiles)

        # ปุ่มจัดการไฟล์
        rowStage = QHBoxLayout()
        self.btnAddStage = QPushButton("เพิ่มไฟล์…")
        self.btnUseStage = QPushButton("ใช้ไฟล์นี้")
        self.btnDelStage = QPushButton("ลบออก")
        rowStage.addWidget(self.btnAddStage)
        rowStage.addWidget(self.btnUseStage)
        rowStage.addWidget(self.btnDelStage)
        layout.addLayout(rowStage)

        # ----- ฟีเจอร์มุมมอง -----
        layout.addWidget(QLabel("มุมมอง/เมาส์"))
        viewRow = QHBoxLayout()
        self.chkCross = QCheckBox("แสดง Crosshair")
        self.btnBoxZoom = QPushButton("เลือกช่วง (ลากเพื่อซูม)")
        viewRow.addWidget(self.chkCross)
        viewRow.addWidget(self.btnBoxZoom)
        layout.addLayout(viewRow)

        layout.addStretch(1)

        # signals
        self.btnLoadCols.clicked.connect(self.load_columns_from_df)
        self.btnLine.clicked.connect(self.plot_line); self.btnScatter.clicked.connect(self.plot_scatter)
        self.btnClear.clicked.connect(self.clear_plot); self.btnExport.clicked.connect(self.export_png)
        self.btnExportRange.clicked.connect(self.export_visible_range_csv)
        self.btnTZ.clicked.connect(self.feature_add_bkk_time)
        self.btnMag.clicked.connect(self.feature_add_magnitude)
        self.btnMA.clicked.connect(self.feature_add_moving_average)
        self.btnTypes.clicked.connect(self.feature_set_column_types)
        self.chkCross.toggled.connect(self.toggle_crosshair)
        self.btnBoxZoom.clicked.connect(self.start_box_zoom)
        self.btnAddStage.clicked.connect(self.stage_add_files)
        self.btnUseStage.clicked.connect(self.stage_use_selected)
        self.btnDelStage.clicked.connect(self.stage_remove_selected)

        # ดับเบิลคลิกชื่อไฟล์เพื่อใช้ทันที
        self.lstFiles.itemDoubleClicked.connect(lambda it: self.stage_use_selected())

    def _init_menu(self):
        m = self.menuBar()
        fileMenu = m.addMenu("&ไฟล์")
        actOpen = fileMenu.addAction("เปิดข้อมูล (CSV/TSV/TXT/XLSX/NC/CDF)..."); actOpen.triggered.connect(self.open_file)
        fileMenu.addSeparator()
        actExport = fileMenu.addAction("บันทึกรูปภาพ (PNG)..."); actExport.triggered.connect(self.export_png)
        fileMenu.addSeparator()
        actExit = fileMenu.addAction("ออกจากโปรแกรม"); actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&มุมมอง")
        actReset = viewMenu.addAction("รีเซ็ตมุมมองกราฟ")
        actReset.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True), self.canvas.ax.set_ylim(auto=True), self.canvas.draw()])

        helpMenu = m.addMenu("&ช่วยเหลือ")
        actAbout = helpMenu.addAction("เกี่ยวกับโปรแกรม"); actAbout.triggered.connect(self.show_about)

    # ---------- File ----------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์ข้อมูล", "",
                    "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf);;All Files (*.*)")
        if not path: return
        # ใช้เส้นทางเดียวกับ stage_add_files แต่ทีละไฟล์
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
                df, enc_note = load_tabular(path, ext)
                if df is None or df.empty:
                    raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
                name = f"{os.path.basename(path)} [ตาราง]"
                self._stage_insert(name, df, path)
            elif ext in [".nc", ".cdf"]:
                df = load_cdf_nc_on_demand(self, path)
                if df is None or df.empty:
                    raise ValueError("ไฟล์ CDF/NetCDF ไม่มีข้อมูลที่ใช้พล็อตได้")
                name = f"{os.path.basename(path)} [CDF/NC]"
                self._stage_insert(name, df, path)
            else:
                raise ValueError("นามสกุลไฟล์ไม่รองรับ")

            # ตั้งให้รายการที่เพิ่งเพิ่มเป็น current แต่ยังไม่บังคับใช้
            self.lstFiles.setCurrentRow(self.lstFiles.count() - 1)
            self.statusBar().showMessage("เพิ่มไฟล์เข้าสู่รายการแล้ว • เลือกแล้วกด 'ใช้ไฟล์นี้' หรือดับเบิลคลิกชื่อไฟล์")

        except Exception as e:
            QMessageBox.critical(self, "เปิดไฟล์ไม่สำเร็จ", f"สาเหตุ: {e}")

    def load_data(self, path: str):
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
                df, enc_note = load_tabular(path, ext)
                if df is None or df.empty: raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
                self._df, self._current_path = df, path
                self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (ตาราง) • {enc_note}")
                self.statusBar().showMessage("โหลดข้อมูลสำเร็จ (ตาราง) • กด 'โหลดคอลัมน์'")
                return
            if ext in [".nc", ".cdf"]:
                df = load_cdf_nc_on_demand(self, path)
                if df is None or df.empty: raise ValueError("อ่านไฟล์ CDF/NetCDF ไม่สำเร็จ หรือไม่มีข้อมูล")
                self._df, self._current_path = df, path
                self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (CDF/NetCDF)")
                self.statusBar().showMessage("โหลดข้อมูลสำเร็จ (On‑Demand) • กด 'โหลดคอลัมน์'")
                return
            raise ValueError("นามสกุลไฟล์ไม่รองรับ")
        except Exception as e:
            QMessageBox.critical(self, "เปิดไฟล์ไม่สำเร็จ", f"สาเหตุ: {e}")
            self.statusBar().showMessage("เกิดข้อผิดพลาดในการเปิดไฟล์")

    def load_columns_from_df(self):
        if self._df is None:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน"); return
        cols = [str(c) for c in self._df.columns]
        self.cbX.clear(); self.cbY.clear()
        self.cbX.addItems(cols); self.cbY.addItems(cols)
        self.statusBar().showMessage("โหลดคอลัมน์เรียบร้อย • เลือก X/Y แล้วพล็อตได้")

    # ---------- Plot ----------
    def _get_xy(self):
        if self._df is None:
            QMessageBox.warning(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'"); return None, None
        if self.cbX.count() == 0 or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่ได้โหลดคอลัมน์", "กดปุ่ม 'โหลดคอลัมน์จากข้อมูล' ก่อน"); return None, None

        x_col = self.cbX.currentText(); y_col = self.cbY.currentText()
        if x_col not in self._df.columns or y_col not in self._df.columns:
            QMessageBox.warning(self, "คอลัมน์ไม่ถูกต้อง", "โปรดเลือกคอลัมน์ X/Y ใหม่"); return None, None

        x = self._df[x_col].values; y = self._df[y_col].values
        # แปลงตัวเลข (ไม่ไปยุ่ง datetime)
        try: y = pd.to_numeric(y, errors="coerce")
        except Exception: pass
        mask = ~(pd.isna(y))
        if np.issubdtype(type(x[0]), np.datetime64):
            x = x[mask]; y = y[mask]
        else:
            try: x = pd.to_numeric(x, errors="coerce")
            except Exception: pass
            mask = ~(pd.isna(x) | pd.isna(y))
            x = x[mask]; y = y[mask]
        return x, y

    def plot_line(self):
        x, y = self._get_xy()
        if x is None: return
        lw = self.spLineWidth.value(); marker = "o" if self.chkMarker.isChecked() else None
        self.canvas.ax.plot(x, y, linewidth=lw, marker=marker, label=f"{self.cbY.currentText()} vs {self.cbX.currentText()}")
        self.canvas.ax.set_xlabel(self.cbX.currentText()); self.canvas.ax.set_ylabel(self.cbY.currentText())
        self.canvas.ax.legend(loc="best"); self.canvas.fig.tight_layout(); self.canvas.draw()
        self.statusBar().showMessage("พล็อตกราฟเส้นสำเร็จ")

    def plot_scatter(self):
        x, y = self._get_xy()
        if x is None: return
        size = self.spLineWidth.value() * 5
        self.canvas.ax.scatter(x, y, s=size, label=f"{self.cbY.currentText()} vs {self.cbX.currentText()}")
        self.canvas.ax.set_xlabel(self.cbX.currentText()); self.canvas.ax.set_ylabel(self.cbY.currentText())
        self.canvas.ax.legend(loc="best"); self.canvas.fig.tight_layout(); self.canvas.draw()
        self.statusBar().showMessage("พล็อตกราฟจุดสำเร็จ")

    # ---------- Features ----------
    def feature_add_bkk_time(self):
        if self._df is None or self.cbX.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        x_col = self.cbX.currentText()
        try:
            new_col = add_time_bangkok(self._df, x_col)
            self.cbX.addItem(new_col)  # ให้เลือกเป็นแกน X ได้ทันที
            self.statusBar().showMessage(f"เพิ่มคอลัมน์เวลา (Bangkok) แล้ว: {new_col}")
        except Exception as e:
            QMessageBox.critical(self, "ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_add_magnitude(self):
        if self._df is None or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        # ให้ผู้ใช้เลือก 3 คอลัมน์ที่จะคำนวณ |B|
        cols = [str(c) for c in self._df.columns]
        from PySide6.QtWidgets import QInputDialog
        bx, ok = QInputDialog.getItem(self, "เลือกคอลัมน์ Bx", "Bx:", cols, 0, False)
        if not ok: return
        by, ok = QInputDialog.getItem(self, "เลือกคอลัมน์ By", "By:", cols, 0, False)
        if not ok: return
        bz, ok = QInputDialog.getItem(self, "เลือกคอลัมน์ Bz", "Bz:", cols, 0, False)
        if not ok: return
        try:
            new_col = add_magnitude(self._df, bx, by, bz, new_col="B_mag")
            self.cbY.addItem(new_col)
            self.statusBar().showMessage(f"เพิ่มคอลัมน์ |B| แล้ว: {new_col}")
        except Exception as e:
            QMessageBox.critical(self, "ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_add_moving_average(self):
        if self._df is None or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        y_col = self.cbY.currentText()
        try:
            new_col = add_moving_average(self._df, y_col, window=25)
            self.cbY.addItem(new_col)
            self.statusBar().showMessage(f"เพิ่มคอลัมน์ Moving Average แล้ว: {new_col}")
        except Exception as e:
            QMessageBox.critical(self, "ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_set_column_types(self):
        if self._df is None or len(self._df.columns) == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน"); return

        dlg = ColumnTypeDialog(self, self._df.columns)
        if dlg.exec() != QDialog.Accepted:
            return

        mapping = dlg.get_mapping()   # {column: "Auto/String/Integer/Float/Datetime"}
        try:
            apply_column_types(self._df, mapping)
            # รีเฟรช combobox ให้แน่ใจว่า UI เห็นคอลัมน์ที่อาจแปลงแล้ว
            self.load_columns_from_df()
            self.statusBar().showMessage("แปลงชนิดข้อมูลคอลัมน์เรียบร้อย")
        except Exception as e:
            QMessageBox.critical(self, "แปลงไม่สำเร็จ", f"สาเหตุ: {e}")

    def run_fft_dialog(self):
        if self._df is None or self.cbX.count() == 0 or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์และกด 'โหลดคอลัมน์จากข้อมูล' ก่อน")
            return

        # เลือกคอลัมน์ Y ที่จะทำ FFT (default = Y ปัจจุบัน)
        cols = [str(c) for c in self._df.columns]
        y_default = max(0, self.cbY.currentIndex())
        y_col, ok = QInputDialog.getItem(self, "เลือกคอลัมน์ Y สำหรับ FFT", "Y:", cols, y_default, False)
        if not ok:
            return

        # เลือก window และ detrend
        window, ok = QInputDialog.getItem(self, "หน้าต่าง (window)", "ชนิด:", ["hanning", "hamming", "none"], 0, False)
        if not ok:
            return
        detrend_choice, ok = QInputDialog.getItem(self, "ลบค่าเฉลี่ยก่อนคำนวณ?", "detrend:", ["True", "False"], 0, False)
        if not ok:
            return
        detrend = (detrend_choice == "True")

        x_col = self.cbX.currentText()

        try:
            df_fft, fs = compute_fft(self._df, x_col=x_col, y_col=y_col, detrend=detrend, window=window)
            self._fft_df = df_fft
            self._fft_meta = {"fs": fs, "x_col": x_col, "y_col": y_col, "window": window, "detrend": detrend}

            # พล็อตผล FFT (freq vs amplitude) แทนกราฟเดิม
            self.canvas.clear()
            self.canvas.ax.plot(df_fft["freq_Hz"].values, df_fft["amplitude"].values, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("Amplitude")
            self.canvas.ax.set_title(f"FFT of {y_col} (fs≈{fs:.3f} Hz, window={window}, detrend={detrend})")
            self.canvas.ax.grid(True)
            self.canvas.fig.tight_layout()
            self.canvas.draw()
            self.statusBar().showMessage("คำนวณ FFT เสร็จแล้ว • ใช้ Export FFT เพื่อบันทึกผลได้")

        except Exception as e:
            QMessageBox.critical(self, "FFT ไม่สำเร็จ", f"สาเหตุ: {e}")

    def export_fft_dialog(self):
        if self._fft_df is None or self._fft_df.empty:
            QMessageBox.information(self, "ยังไม่มีผล FFT", "โปรดคำนวณ FFT ก่อน (ปุ่ม FFT)")
            return

        # ให้เลือกชนิดไฟล์ปลายทาง
        kind, ok = QInputDialog.getItem(
            self, "เลือกชนิดไฟล์", "บันทึกเป็น:",
            ["CSV (.csv)", "Excel (.xlsx)", "NetCDF (.nc)"], 0, False
        )
        if not ok:
            return

        # เลือก path
        if kind.startswith("CSV"):
            path, _ = QFileDialog.getSaveFileName(self, "บันทึกผล FFT เป็น CSV", "fft_result.csv", "CSV (*.csv)")
            if not path: return
            try:
                self._fft_df.to_csv(path, index=False)
                self.statusBar().showMessage(f"บันทึก CSV แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

        elif kind.startswith("Excel"):
            path, _ = QFileDialog.getSaveFileName(self, "บันทึกผล FFT เป็น Excel", "fft_result.xlsx", "Excel (*.xlsx)")
            if not path: return
            try:
                with pd.ExcelWriter(path) as w:
                    self._fft_df.to_excel(w, sheet_name="FFT", index=False)
                    # แนบเมตา
                    meta = pd.DataFrame([self._fft_meta])
                    meta.to_excel(w, sheet_name="meta", index=False)
                self.statusBar().showMessage(f"บันทึก Excel แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

        else:  # NetCDF
            path, _ = QFileDialog.getSaveFileName(self, "บันทึกผล FFT เป็น NetCDF", "fft_result.nc", "NetCDF (*.nc)")
            if not path: return
            try:
                # ใช้ xarray สร้าง Dataset อย่างง่าย
                import xarray as xr
                ds = xr.Dataset(
                    data_vars=dict(
                        amplitude=("freq_Hz", self._fft_df["amplitude"].values),
                        power=("freq_Hz", self._fft_df["power"].values),
                    ),
                    coords=dict(
                        freq_Hz=("freq_Hz", self._fft_df["freq_Hz"].values),
                    ),
                    attrs=dict(**self._fft_meta)
                )
                ds.to_netcdf(path)
                self.statusBar().showMessage(f"บันทึก NetCDF แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def toggle_crosshair(self, checked: bool):
        # เคลียร์ของเก่าถ้ามี
        if self._cursor is not None:
            self._cursor = None
        if self._cid_motion is not None:
            try:
                self.canvas.mpl_disconnect(self._cid_motion)
            except Exception:
                pass
            self._cid_motion = None

        if not checked:
            self.statusBar().showMessage("ปิด Crosshair แล้ว")
            self.canvas.draw()
            return

        # สร้าง Crosshair
        self._cursor = Cursor(self.canvas.ax, useblit=True, horizOn=True, vertOn=True)
        # อัปเดตสถานะ X,Y ใต้เมาส์
        def _on_move(event):
            if event.inaxes != self.canvas.ax:
                return
            x, y = event.xdata, event.ydata
            try:
                if x is None or y is None:
                    return
                self.statusBar().showMessage(f"X={x} | Y={y}")
            except Exception:
                pass
        self._cid_motion = self.canvas.mpl_connect("motion_notify_event", _on_move)
        self.statusBar().showMessage("เปิด Crosshair แล้ว")
        self.canvas.draw()

    def start_box_zoom(self):
        # ปิดตัวเดิมถ้ามี
        if self._rs is not None:
            try:
                self._rs.set_active(False)
            except Exception:
                pass
            self._rs = None

        ax = self.canvas.ax
        self.statusBar().showMessage("โหมดเลือกช่วง: ลากเมาส์คลุมพื้นที่ที่ต้องการซูม (คลิกซ้ายค้างแล้วลาก)")

        def _on_select(eclick, erelease):
            try:
                x1, y1 = eclick.xdata, eclick.ydata
                x2, y2 = erelease.xdata, erelease.ydata
                if None in (x1, y1, x2, y2):
                    return
                xmin, xmax = sorted([x1, x2])
                ymin, ymax = sorted([y1, y2])
                ax.set_xlim(xmin, xmax)
                ax.set_ylim(ymin, ymax)
                self.canvas.draw()
                self.statusBar().showMessage(f"ซูมช่วง X=({xmin}, {xmax})  Y=({ymin}, {ymax})")
            finally:
                # one-shot: ปิด selector หลังซูม
                if self._rs is not None:
                    try:
                        self._rs.set_active(False)
                    except Exception:
                        pass
                    self._rs = None

        self._rs = RectangleSelector(
            ax, _on_select,
            useblit=True,
            button=[1],             # ปุ่มซ้าย
            interactive=False,
            minspanx=0, minspany=0,
            spancoords='data'
        )

    def export_visible_range_csv(self):
        if self._df is None or self.cbX.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน")
            return

        # ช่วงที่กำลังเห็นบนกราฟ
        ax = self.canvas.ax
        xmin, xmax = ax.get_xlim()

        # คอลัมน์ X ปัจจุบัน
        xcol = self.cbX.currentText()
        xser = self._df[xcol]

        # กรองตามชนิดข้อมูลของ X
        df_view = None
        try:
            # ถ้าเป็น datetime
            if np.issubdtype(np.array(xser)[0].__class__, np.datetime64) or np.issubdtype(xser.dtype, np.datetime64):
                # matplotlib แสดง datetime เป็นเลขภายใน ดังนั้นแปลงใหม่จากแกนเป็น datetime
                import matplotlib.dates as mdates
                xmin_dt = mdates.num2date(xmin)
                xmax_dt = mdates.num2date(xmax)
                mask = (pd.to_datetime(xser) >= xmin_dt) & (pd.to_datetime(xser) <= xmax_dt)
                df_view = self._df.loc[mask].copy()
            else:
                # numeric
                xnum = pd.to_numeric(xser, errors="coerce")
                mask = (xnum >= xmin) & (xnum <= xmax)
                df_view = self._df.loc[mask].copy()
        except Exception:
            # fallback แบบครอบจักรวาล: พยายามบังคับ numeric
            xnum = pd.to_numeric(xser, errors="coerce")
            mask = (xnum >= xmin) & (xnum <= xmax)
            df_view = self._df.loc[mask].copy()

        if df_view is None or df_view.empty:
            QMessageBox.information(self, "ไม่มีข้อมูลในช่วงนี้", "ช่วงที่แสดงอยู่ไม่มีข้อมูลให้ส่งออก")
            return

        # เลือกที่บันทึก
        path, _ = QFileDialog.getSaveFileName(self, "บันทึกช่วงที่เห็นเป็น CSV", "view_range.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            df_view.to_csv(path, index=False)
            self.statusBar().showMessage(f"บันทึก CSV ช่วงที่เห็นแล้ว: {path}")
        except Exception as e:
            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def _stage_insert(self, name: str, df: pd.DataFrame, path: str):
        """ใส่ DataFrame เข้า staging และเติมลง QListWidget (ถ้าชื่อซ้ำจะเติม (2), (3), ...)"""
        base = name
        i = 2
        while name in self._datasets:
            name = f"{base} ({i})"
            i += 1
        self._datasets[name] = {"df": df, "path": path}
        self.lstFiles.addItem(QListWidgetItem(name))
        self.statusBar().showMessage(f"เตรียมไฟล์: {name}")

    def stage_add_files(self):
        """กดปุ่ม 'เพิ่มไฟล์…' → เลือกไฟล์ แล้วโหลดแบบเดียวกับ load_data แต่ไม่สลับ self._df ทันที"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "เลือกไฟล์เพื่อเตรียมไว้",
            "", "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf);;All Files (*.*)"
        )
        if not paths:
            return

        for path in paths:
            try:
                ext = os.path.splitext(path)[1].lower()
                # ตาราง
                if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
                    df, enc_note = load_tabular(path, ext)
                    if df is None or df.empty:
                        raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
                    name = f"{os.path.basename(path)} [ตาราง]"
                    self._stage_insert(name, df, path)

                # CDF/NetCDF On‑Demand (จะถามเลือก Y/ slice สำหรับไฟล์นี้ครั้งเดียวตอนเตรียม)
                elif ext in [".nc", ".cdf"]:
                    df = load_cdf_nc_on_demand(self, path)
                    if df is None or df.empty:
                        raise ValueError("ไฟล์ CDF/NetCDF ไม่มีข้อมูลที่ใช้พล็อตได้")
                    name = f"{os.path.basename(path)} [CDF/NC]"
                    self._stage_insert(name, df, path)

                else:
                    QMessageBox.information(self, "ข้ามไฟล์", f"นามสกุลไม่รองรับ: {path}")

            except Exception as e:
                QMessageBox.warning(self, "เพิ่มไฟล์ไม่สำเร็จ", f"{os.path.basename(path)}\nสาเหตุ: {e}")

    def stage_use_selected(self):
        """กดปุ่ม 'ใช้ไฟล์นี้' → สลับ self._df ให้เป็นไฟล์ที่เลือก แล้วให้ผู้ใช้กดโหลดคอลัมน์"""
        item = self.lstFiles.currentItem()
        if not item:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "โปรดเลือกไฟล์จากรายการก่อน")
            return
        name = item.text()
        data = self._datasets.get(name)
        if not data:
            QMessageBox.warning(self, "ไม่พบข้อมูล", "รายการนี้ไม่มีข้อมูลแล้ว")
            return
        self._df = data["df"].copy()
        self._current_path = data["path"]
        self.lblFile.setText(f"ใช้งานไฟล์: {name}")
        self.statusBar().showMessage("สลับไฟล์แล้ว • กด 'โหลดคอลัมน์จากข้อมูล' เพื่อเลือก X/Y")
        # ไม่บังคับโหลดคอลัมน์ทันที ให้ผู้ใช้กดเองตาม flow เดิม

    def stage_remove_selected(self):
        """กดปุ่ม 'ลบออก' → เอาออกจาก staging (ไม่ลบไฟล์จริง)"""
        row = self.lstFiles.currentRow()
        if row < 0:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "โปรดเลือกไฟล์จากรายการก่อน")
            return
        item = self.lstFiles.item(row)
        name = item.text()
        # ถ้ากำลังใช้งานอยู่ ให้ถามเพื่อกันพลาด
        if self._current_path and name in self._datasets and self._datasets[name]["path"] == self._current_path:
            ans = QMessageBox.question(self, "กำลังใช้งานไฟล์นี้อยู่", "ไฟล์นี้กำลังถูกใช้งานอยู่ ต้องการลบออกจากรายการหรือไม่?")
            if ans != QMessageBox.Yes:
                return
        # ลบออกจาก dict และ list
        self._datasets.pop(name, None)
        self.lstFiles.takeItem(row)
        self.statusBar().showMessage(f"นำออกจากรายการแล้ว: {name}")

    def clear_plot(self):
        self.canvas.clear(); self.statusBar().showMessage("ล้างกราฟแล้ว")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "บันทึกรูปภาพเป็น", "plot.png", "PNG Image (*.png)")
        if not path: return
        try:
            self.canvas.fig.savefig(path, dpi=300, bbox_inches="tight")
            self.statusBar().showMessage(f"บันทึกรูปภาพแล้ว: {path}")
        except Exception as e:
            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def show_about(self):
        QMessageBox.information(self, "เกี่ยวกับโปรแกรม",
            "SciPlotter (Modular + Features)\n"
            "ไฟล์แยกเป็น main/dialogs/loaders/processors\n"
            "ฟีเจอร์: เวลา+7h, |B|, Moving Average\n"
            "เปิดไฟล์ → (CDF/NC เลือกตัวแปรแบบ On‑Demand) → โหลดคอลัมน์ → พล็อต")

    # DnD
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path): self.load_data(path); break

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
