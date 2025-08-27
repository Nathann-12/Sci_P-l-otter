# main.py
import os, sys
import numpy as np
import pandas as pd
import logging
import locale

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# บังคับให้ Python ใช้ locale ภาษาอังกฤษเพื่อแสดงเลขอารบิก
try:
    locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    logger.info("Locale set to English (en_US.UTF-8)")
except Exception as e:
    try:
        # Fallback สำหรับ Windows
        locale.setlocale(locale.LC_ALL, "English_United States.1252")
        logger.info("Locale set to English (English_United States.1252)")
    except Exception as e2:
        logger.warning(f"Could not set English locale: {e2}")

from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QDockWidget, QMessageBox, QSpinBox, QCheckBox, QDialog,
    QListWidget, QListWidgetItem, QToolBar, QInputDialog, QSplitter, QTabWidget, QSizePolicy,
    QFrame, QGroupBox, QStyle
)
from PySide6.QtGui import QAction, QIcon

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.dates as mdates  # CHANGE: handle datetime axes formatting
from matplotlib.figure import Figure
from matplotlib.widgets import Cursor, RectangleSelector
import matplotlib
import matplotlib.pyplot as plt

# บังคับให้ Matplotlib ไม่ใช้ locale และแสดงเลขอารบิก
matplotlib.rcParams["axes.formatter.use_locale"] = False
matplotlib.rcParams["axes.formatter.use_mathtext"] = False
matplotlib.rcParams["axes.unicode_minus"] = False

# Load custom dark style if available
try:
    style_path = os.path.join(os.path.dirname(__file__), "styles", "mpl_style_dark_pro.mplstyle")
    if os.path.exists(style_path):
        plt.style.use(style_path)
except Exception:
    pass  # Fallback to default style if loading fails

# Font settings - use fonts that are commonly available on Windows
matplotlib.rcParams["font.sans-serif"] = [
    "Segoe UI", "Microsoft YaHei", "Tahoma", "Arial", 
    "DejaVu Sans", "Liberation Sans", "Helvetica"
]

# Set default font to one that is available
try:
    import matplotlib.font_manager as fm
    # Use fonts that are commonly available on Windows
    available_fonts = ["Segoe UI", "Microsoft YaHei", "Tahoma", "Arial"]
    for font_name in available_fonts:
        try:
            font_path = fm.findfont(fm.FontProperties(family=font_name))
            if font_path and "DejaVuSans" not in font_path:  # Avoid fallback
                matplotlib.rcParams["font.family"] = font_name
                break
        except Exception:
            continue
except Exception:
    matplotlib.rcParams["font.family"] = "Segoe UI"  # Fallback

matplotlib.rcParams["axes.unicode_minus"] = False

from loaders import load_tabular, load_cdf_nc_on_demand
from dialogs import MultiDimSliceDialog, ColumnTypeDialog
from dialogs import AggregateDialog  # UI-REFINE: Aggregate dialog
from dialogs import FitDialog  # UI-FIT: Curve Fit dialog
from processors import add_time_bangkok, add_magnitude, add_moving_average, apply_column_types, compute_fft
from processors import _to_seconds_from_start, fit_poly_datetime, beautify_axes  # CHANGE: datetime fit helpers + plot beautification
from styles.theme import apply_theme, apply_theme_from_config, apply_mpl_from_config, refresh_matplotlib_canvases  # UI-REFINE: ใช้ธีมอ่านง่าย
from settings import settings_manager
from dialogs_settings import SettingsDialog

APP_TITLE = "SciPlotter (Modular + Features)"

class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig); self.setParent(parent)
        self.fig.tight_layout()
    
    def clear(self):
        """Clear the canvas and recreate axes with error handling"""
        try:
            # Store current theme colors
            import matplotlib
            current_facecolor = matplotlib.rcParams.get("figure.facecolor", "#1e1e1e")
            current_axes_facecolor = matplotlib.rcParams.get("axes.facecolor", "#1e1e1e")
            
            self.fig.clf()
            self.ax = self.fig.add_subplot(111)
            
            # Apply theme colors to new figure
            self.fig.patch.set_facecolor(current_facecolor)
            self.ax.set_facecolor(current_axes_facecolor)
            
            self.fig.tight_layout()
            # Use safer draw method
            try:
                self.draw()
            except Exception:
                # Fallback to figure canvas draw
                self.fig.canvas.draw()
        except Exception as e:
            print(f"Canvas clear error: {e}")
            # Emergency fallback - recreate figure completely
            try:
                self.fig = Figure(figsize=(6, 4), dpi=100)
                self.ax = self.fig.add_subplot(111)
                
                # Apply theme colors to new figure
                import matplotlib
                current_facecolor = matplotlib.rcParams.get("figure.facecolor", "#1e1e1e")
                current_axes_facecolor = matplotlib.rcParams.get("axes.facecolor", "#1e1e1e")
                self.fig.patch.set_facecolor(current_facecolor)
                self.ax.set_facecolor(current_axes_facecolor)
                
                self.fig.tight_layout()
                self.draw()
            except Exception:
                print(f"Emergency canvas recreation failed: {e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE); self.resize(1180, 760)
        self._df = None; self._current_path = None
        self._datasets = {}   # dict: key = ชื่อที่โชว์ในลิสต์, value = {"df": DataFrame, "path": str}
        self._cursor = None
        self._cid_motion = None   # id ของ event handler mouse move
        self._rs = None           # RectangleSelector (ใช้ใน Box Zoom)
        self._fft_df = None       # เก็บผล FFT ล่าสุด
        self._fft_meta = {}       # meta: fs, x_col, y_col, window, detrend
        self.current_aggregated_df = None  # UI-REFINE: เก็บผล aggregate ล่าสุดสำหรับ export

        # UI-REFINE: โครงสร้างหลักด้วย QSplitter (ซ้าย/กลาง/ขวา)
        central = QWidget(); self.setCentralWidget(central)
        v = QVBoxLayout(central)
        # CHANGE: ครอบด้วย QFrame + margins/spacing เพื่อพื้นที่หายใจ
        outer = QFrame(self)
        outer.setFrameShape(QFrame.NoFrame)
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(12, 12, 12, 12)  # CHANGE: margins 12
        ov.setSpacing(10)  # CHANGE: spacing readable
        # UI-REFINE: ใช้ QSplitter แนวนอน
        self.splitter = QSplitter(Qt.Horizontal, self)
        ov.addWidget(self.splitter)
        v.addWidget(outer)

        # กลาง = แคนวาส Matplotlib + toolbar
        mid = QWidget(self)
        mid_layout = QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)  # CHANGE: tight inner
        mid_layout.setSpacing(8)
        self.canvas = PlotCanvas(self); self.toolbar = NavigationToolbar(self.canvas, self)
        mid_layout.addWidget(self.canvas)
        try:
            self.toolbar.setVisible(False)  # CHANGE: hide Matplotlib toolbar to free plot space
        except Exception:
            pass
        # UI-REFINE: plot_canvas ขยายเต็มที่
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.addWidget(mid)

        # ซ้าย = File/Staging
        self._panel_left = QWidget(self)
        self._left_layout = QVBoxLayout(self._panel_left)
        self._left_layout.setContentsMargins(8, 8, 8, 8)  # CHANGE: panel margins
        self._left_layout.setSpacing(8)
        self._build_left_panel()  # UI-REFINE
        # UI-REFINE: sidebar ซ้ายมีความกว้างขั้นต่ำ
        self._panel_left.setMinimumWidth(180)
        self.splitter.insertWidget(0, self._panel_left)

        # ขวา = Inspector Tabs (Plot/Processing/Export)
        self._panel_right = QWidget(self)
        self._right_layout = QVBoxLayout(self._panel_right)
        self._right_layout.setContentsMargins(8, 8, 8, 8)  # CHANGE: panel margins
        self._right_layout.setSpacing(8)
        self._build_inspector_tabs()  # UI-REFINE
        # UI-REFINE: inspector ขวามีความกว้างขั้นต่ำ
        self._panel_right.setMinimumWidth(220)
        self.splitter.addWidget(self._panel_right)

        # UI-REFINE: ขนาดสัดส่วนเริ่มต้น (ซ้าย=200, กลาง=600, ขวา=200)
        self.splitter.setSizes([200, 600, 200])
        self.splitter.setHandleWidth(8)  # CHANGE: wider handle for usability
        # UI-REFINE: กลางต้องขยายเมื่อหน้าต่างกว้างขึ้น
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        # UI-REFINE: ทูลบาร์จัดกลุ่ม File / View / Process / Export (ต้องสร้างก่อนเมนู)
        self.tb = QToolBar("Toolbar", self); self.addToolBar(self.tb)
        self.actOpen = QAction("Open", self); self.actResetView = QAction("Reset View", self)
        self.actClearView = QAction("Clear Plot", self)  # UI-REFINE
        # UI-REFINE: ปุ่มซ่อน/แสดง Inspector
        self.actToggleInspector = QAction("Inspector", self); self.actToggleInspector.setCheckable(True)
        self.actFFT = QAction("FFT", self); self.actExportFFT = QAction("Export FFT", self)
        # Settings action
        self.actSettings = QAction("Settings", self)
        # CHANGE: ตั้งไอคอนด้วยไฟล์หรือ fallback มาตรฐาน
        try:
            self.actOpen.setIcon(self._icon("open", QStyle.StandardPixmap.SP_DialogOpenButton))
            self.actSettings.setIcon(self._icon("settings", QStyle.StandardPixmap.SP_FileDialogDetailedView))
            self.actResetView.setIcon(self._icon("reset", QStyle.StandardPixmap.SP_BrowserReload))
            self.actClearView.setIcon(self._icon("clear", QStyle.StandardPixmap.SP_DialogResetButton))
            self.actToggleInspector.setIcon(self._icon("inspector", QStyle.StandardPixmap.SP_FileDialogDetailedView))
            self.actFFT.setIcon(self._icon("fft", QStyle.StandardPixmap.SP_ComputerIcon))
            self.actExportFFT.setIcon(self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        self.actOpen.triggered.connect(self.open_file)
        self.actResetView.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True), self.canvas.ax.set_ylim(auto=True), self.canvas.draw()])
        self.actClearView.triggered.connect(self.clear_plot)
        self.actToggleInspector.toggled.connect(self.toggle_inspector)
        self.actFFT.triggered.connect(self.run_fft_dialog)
        self.actExportFFT.triggered.connect(self.export_fft_dialog)
        self.actSettings.triggered.connect(self.show_settings)
        self.tb.addAction(self.actOpen); self.tb.addSeparator()
        self.tb.addAction(self.actResetView); self.tb.addAction(self.actClearView); self.tb.addAction(self.actToggleInspector); self.tb.addSeparator()
        self.tb.addAction(self.actFFT); self.tb.addSeparator()
        self.tb.addAction(self.actExportFFT); self.tb.addSeparator()
        self.tb.addAction(self.actSettings)

        self._init_menu()
        self._connect_signals()  # UI-REFINE: เชื่อมสัญญาณหลังจากวิดเจ็ตถูกสร้างครบ
        
        # UI-REFINE: สถานะถาวรใน StatusBar
        self._sb_rows = QLabel("rows: -")
        self._sb_fs = QLabel("fs: -")
        self._sb_cursor = QLabel("x=-, y=-")
        self.statusBar().addPermanentWidget(self._sb_rows)
        self.statusBar().addPermanentWidget(self._sb_fs)
        self.statusBar().addPermanentWidget(self._sb_cursor)
        self.statusBar().showMessage("พร้อมใช้งาน • เปิดไฟล์ → โหลดคอลัมน์")
        self.setAcceptDrops(True)

        # UI-REFINE: ซ่อน Inspector ตอนเริ่ม และ sync ปุ่ม
        self._panel_right.setVisible(False)
        try: self.actToggleInspector.setChecked(False)
        except Exception: pass

    # UI-REFINE: แยกสร้างแผงซ้าย (Staging) และแท็บ Inspector ขวา
    def _build_left_panel(self):
        l = self._left_layout
        self.lblFile = QLabel("ยังไม่ได้เปิดไฟล์"); self.lblFile.setWordWrap(True); l.addWidget(self.lblFile)

        # CHANGE: กล่อง "ไฟล์ที่เตรียมไว้"
        gb_files = QGroupBox("ไฟล์ที่เตรียมไว้")
        gbf = QVBoxLayout(gb_files); gbf.setContentsMargins(8, 8, 8, 8); gbf.setSpacing(8)
        self.lstFiles = QListWidget(); self.lstFiles.setSelectionMode(QListWidget.SingleSelection); gbf.addWidget(self.lstFiles)
        rowStage = QHBoxLayout()
        self.btnAddStage = QPushButton("เพิ่มไฟล์…"); self.btnUseStage = QPushButton("ใช้ไฟล์นี้"); self.btnDelStage = QPushButton("ลบออก")
        rowStage.addWidget(self.btnAddStage); rowStage.addWidget(self.btnUseStage); rowStage.addWidget(self.btnDelStage); gbf.addLayout(rowStage)
        l.addWidget(gb_files)

        # CHANGE: กล่อง "แสดง Crosshair"
        gb_cross = QGroupBox("แสดง Crosshair")
        gbc = QVBoxLayout(gb_cross); gbc.setContentsMargins(8, 8, 8, 8); gbc.setSpacing(8)
        self.chkCross = QCheckBox("แสดง Crosshair")
        gbc.addWidget(self.chkCross)
        l.addWidget(gb_cross)

        # CHANGE: กล่อง "มุมมอง/เมาส์"
        gb_view = QGroupBox("มุมมอง/เมาส์")
        gbv = QVBoxLayout(gb_view); gbv.setContentsMargins(8, 8, 8, 8); gbv.setSpacing(8)
        self.btnBoxZoom = QPushButton("เลือกช่วง (ลากเพื่อซูม)")
        gbv.addWidget(self.btnBoxZoom)
        l.addWidget(gb_view)

        l.addStretch(1)
        # UI-REFINE: การเชื่อมสัญญาณย้ายไป _connect_signals()

    def _build_inspector_tabs(self):
        r = self._right_layout
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)  # CHANGE: modern tabs look
        # Tab: Plot
        tab_plot = QWidget(); tp = QVBoxLayout(tab_plot)
        self.btnLoadCols = QPushButton("โหลดคอลัมน์จากข้อมูล")
        tp.addWidget(self.btnLoadCols)
        tp.addWidget(QLabel("เลือกคอลัมน์แกน X")); self.cbX = QComboBox(); tp.addWidget(self.cbX)
        tp.addWidget(QLabel("เลือกคอลัมน์แกน Y")); self.cbY = QComboBox(); tp.addWidget(self.cbY)
        styleRow = QHBoxLayout(); styleRow.addWidget(QLabel("ความหนาเส้น")); self.spLineWidth = QSpinBox(); self.spLineWidth.setRange(1,10); self.spLineWidth.setValue(2); styleRow.addWidget(self.spLineWidth); tp.addLayout(styleRow)
        markerRow = QHBoxLayout(); self.chkMarker = QCheckBox("แสดงจุดข้อมูล"); self.chkMarker.setChecked(False); markerRow.addWidget(self.chkMarker); markerRow.addStretch(1); tp.addLayout(markerRow)
        btnRow = QHBoxLayout(); self.btnLine = QPushButton("แสดงกราฟเส้น"); self.btnScatter = QPushButton("แสดงกราฟจุด (Scatter)"); btnRow.addWidget(self.btnLine); btnRow.addWidget(self.btnScatter); tp.addLayout(btnRow)
        # UI-REFINE: ปุ่มล้างกราฟ (Clear Plot)
        rowClear = QHBoxLayout(); self.btnClear = QPushButton("ล้างกราฟ"); rowClear.addWidget(self.btnClear); rowClear.addStretch(1); tp.addLayout(rowClear)
        # UI-FIT: ปุ่ม Curve Fit
        self.btnCurveFit = QPushButton("Curve Fit…"); tp.addWidget(self.btnCurveFit)
        # UI-REFINE: Histogram controls
        tp.addWidget(QLabel("Histogram"))
        rowH1 = QHBoxLayout(); tp.addLayout(rowH1)
        rowH1.addWidget(QLabel("คอลัมน์")); self.cbHist = QComboBox(); rowH1.addWidget(self.cbHist)
        rowH1.addWidget(QLabel("bins")); self.spHistBins = QSpinBox(); self.spHistBins.setRange(5, 200); self.spHistBins.setValue(20); rowH1.addWidget(self.spHistBins)
        rowH2 = QHBoxLayout(); self.chkHistFit = QCheckBox("Fit Normal curve"); self.btnHist = QPushButton("Plot Histogram"); rowH2.addWidget(self.chkHistFit); rowH2.addStretch(1); rowH2.addWidget(self.btnHist); tp.addLayout(rowH2)
        tabs.addTab(tab_plot, "Plot")
        # Tab: Processing
        tab_proc = QWidget(); pr = QVBoxLayout(tab_proc)
        # CHANGE: กล่อง "ฟีเจอร์เสริม"
        gb_feat = QGroupBox("ฟีเจอร์เสริม"); gbl = QVBoxLayout(gb_feat); gbl.setContentsMargins(8,8,8,8); gbl.setSpacing(8)
        row1 = QHBoxLayout(); self.btnTZ = QPushButton("เพิ่มคอลัมน์เวลา +7h (Bangkok)"); self.btnMag = QPushButton("เพิ่มคอลัมน์ |B| จาก 3 แกน"); row1.addWidget(self.btnTZ); row1.addWidget(self.btnMag); gbl.addLayout(row1)
        row2 = QHBoxLayout(); self.btnMA = QPushButton("เพิ่มคอลัมน์ Moving Average (จาก Y)"); row2.addWidget(self.btnMA); gbl.addLayout(row2)
        rowAgg = QHBoxLayout(); self.btnAgg = QPushButton("Aggregate…"); rowAgg.addWidget(self.btnAgg); gbl.addLayout(rowAgg)
        pr.addWidget(gb_feat)
        # CHANGE: กล่อง "การจัดรูปแบบข้อมูล"
        gb_fmt = QGroupBox("การจัดรูปแบบข้อมูล"); gbf = QVBoxLayout(gb_fmt); gbf.setContentsMargins(8,8,8,8); gbf.setSpacing(8)
        row3 = QHBoxLayout(); self.btnTypes = QPushButton("กำหนดชนิดคอลัมน์"); row3.addWidget(self.btnTypes); gbf.addLayout(row3)
        pr.addWidget(gb_fmt)
        tabs.addTab(tab_proc, "Processing")
        # Tab: Export
        tab_exp = QWidget(); ex = QVBoxLayout(tab_exp)
        self.btnExport = QPushButton("บันทึกรูปภาพ (PNG)"); ex.addWidget(self.btnExport)
        self.btnExportRange = QPushButton("ส่งออกช่วงที่เห็น (CSV)"); ex.addWidget(self.btnExportRange)
        # UI-REFINE: ปุ่ม Export ผล Aggregate เป็น CSV
        self.btnExportAgg = QPushButton("Export Aggregated CSV")
        ex.addWidget(self.btnExportAgg)
        tabs.addTab(tab_exp, "Export")
        # CHANGE: ตั้งไอคอนแท็บ
        try:
            tabs.setTabIcon(0, self._icon("plot", QStyle.StandardPixmap.SP_FileDialogContentsView))
            tabs.setTabIcon(1, self._icon("settings", QStyle.StandardPixmap.SP_FileDialogDetailedView))
            tabs.setTabIcon(2, self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        r.addWidget(tabs)

    # UI-REFINE: รวมการเชื่อมสัญญาณไว้ที่เดียว เพื่อให้แน่ใจว่าวิดเจ็ตถูกสร้างครบก่อน
    def _connect_signals(self):
        # Plot/Processing/Export (ฝั่งขวา)
        try:
            self.btnLoadCols.clicked.connect(self.load_columns_from_df)
            self.btnLine.clicked.connect(self.plot_line); self.btnScatter.clicked.connect(self.plot_scatter)
            self.btnCurveFit.clicked.connect(self._open_fit_dialog)  # UI-FIT
            self.btnHist.clicked.connect(self.plot_histogram)  # UI-REFINE
            self.btnExport.clicked.connect(self.export_png)
            self.btnExportRange.clicked.connect(self.export_visible_range_csv)
            self.btnTZ.clicked.connect(self.feature_add_bkk_time)
            self.btnMag.clicked.connect(self.feature_add_magnitude)
            self.btnMA.clicked.connect(self.feature_add_moving_average)
            self.btnTypes.clicked.connect(self.feature_set_column_types)
            self.btnAgg.clicked.connect(self.run_aggregate_dialog)  # UI-REFINE
            self.btnExportAgg.clicked.connect(self.export_aggregated_csv)  # UI-REFINE
        except Exception:
            pass
        # Staging/View (ฝั่งซ้าย)
        self.chkCross.toggled.connect(self.toggle_crosshair)
        self.btnBoxZoom.clicked.connect(self.start_box_zoom)
        self.btnAddStage.clicked.connect(self.stage_add_files)
        self.btnUseStage.clicked.connect(self.stage_use_selected)
        self.btnDelStage.clicked.connect(self.stage_remove_selected)
        self.lstFiles.itemDoubleClicked.connect(lambda it: self.stage_use_selected())

    def _init_menu(self):
        m = self.menuBar()
        fileMenu = m.addMenu("&ไฟล์")  # UI-REFINE: File
        actOpen = fileMenu.addAction("เปิดข้อมูล (CSV/TSV/TXT/XLSX/NC/CDF)..."); actOpen.triggered.connect(self.open_file)
        fileMenu.addSeparator()
        actExport = fileMenu.addAction("บันทึกรูปภาพ (PNG)..."); actExport.triggered.connect(self.export_png)
        fileMenu.addSeparator()
        actExit = fileMenu.addAction("ออกจากโปรแกรม"); actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&มุมมอง")  # UI-REFINE: View
        actReset = viewMenu.addAction("รีเซ็ตมุมมองกราฟ")
        actReset.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True), self.canvas.ax.set_ylim(auto=True), self.canvas.draw()])
        viewMenu.addAction(self.actToggleInspector)
        
        # Plot Style submenu
        plotStyleMenu = viewMenu.addMenu("Plot Style")
        self.actDarkStyle = plotStyleMenu.addAction("Dark")
        self.actDefaultStyle = plotStyleMenu.addAction("Default")
        self.actDarkStyle.setCheckable(True)
        self.actDefaultStyle.setCheckable(True)
        self.actDarkStyle.triggered.connect(lambda: self.change_plot_style("dark"))
        self.actDefaultStyle.triggered.connect(lambda: self.change_plot_style("default"))

        procMenu = m.addMenu("&Process")  # UI-REFINE: Process
        procMenu.addAction("FFT").triggered.connect(self.run_fft_dialog)
        procMenu.addAction("Moving Average").triggered.connect(self.feature_add_moving_average)
        procMenu.addAction("Add |B|").triggered.connect(self.feature_add_magnitude)
        procMenu.addAction("Add Bangkok Time").triggered.connect(self.feature_add_bkk_time)
        procMenu.addAction("Aggregate…").triggered.connect(self.run_aggregate_dialog)  # UI-REFINE

        exportMenu = m.addMenu("&Export")  # UI-REFINE: Export
        exportMenu.addAction("Export Visible CSV").triggered.connect(self.export_visible_range_csv)
        exportMenu.addAction("Export PNG").triggered.connect(self.export_png)

        toolsMenu = m.addMenu("&Tools")  # UI-REFINE: Tools
        toolsMenu.addAction(self.actSettings)

        helpMenu = m.addMenu("&ช่วยเหลือ")  # UI-REFINE: Help → Shortcuts
        actAbout = helpMenu.addAction("เกี่ยวกับโปรแกรม"); actAbout.triggered.connect(self.show_about)
        helpMenu.addAction("Shortcuts").triggered.connect(lambda: QMessageBox.information(self, "Shortcuts",
            "CTRL+O: Open\nCTRL+R: Reset View\nCTRL+E: Export PNG\nF: FFT\nI: Toggle Inspector"
        ))
        
        # Add keyboard shortcuts
        self.actOpen.setShortcut("Ctrl+O")
        self.actSettings.setShortcut("Ctrl+,")
        
        # Load saved plot style preference
        self._load_plot_style_config()
        
        # Load and apply settings from config
        self._load_and_apply_settings()

    # ---------- Plot Style Configuration ----------
    def _get_config_path(self):
        """Get path to configuration file"""
        import json
        import os
        # Try project root first, then user home
        project_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(project_root, ".sciplotter_config.json")
        if not os.path.exists(config_path):
            config_path = os.path.join(os.path.expanduser("~"), ".sciplotter_config.json")
        return config_path
    
    def _load_plot_style_config(self):
        """Load plot style preference from config file"""
        try:
            config_path = self._get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    style = config.get('plot_style', 'dark')
                    self.change_plot_style(style, save_config=False)
            else:
                # No config file, default to dark style
                self.change_plot_style('dark', save_config=False)
        except Exception:
            # Use default if loading fails
            self.change_plot_style('dark', save_config=False)
    
    def _save_plot_style_config(self, style):
        """Save plot style preference to config file"""
        try:
            import json
            config_path = self._get_config_path()
            config = {'plot_style': style}
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass  # Ignore save errors
    
    def _load_and_apply_settings(self):
        """Load and apply settings from configuration"""
        try:
            # Apply Qt theme from config
            from styles.theme import apply_theme_from_config
            app_config = settings_manager.get_appearance()
            apply_theme_from_config(QApplication.instance(), app_config)
            
            # Apply matplotlib settings from config
            from styles.theme import apply_mpl_from_config
            mpl_config = settings_manager.get_matplotlib()
            apply_mpl_from_config(mpl_config)
            
            logger.info("Settings loaded and applied successfully")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    
    def show_settings(self):
        """Show settings dialog"""
        try:
            dialog = SettingsDialog(settings_manager, self)
            dialog.settingsApplied.connect(self._on_settings_applied)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open settings: {str(e)}")
    
    def _on_settings_applied(self):
        """Handle settings applied signal"""
        try:
            # Refresh all canvases to apply new settings
            self.refresh_all_canvases()
            logger.info("Settings applied and canvases refreshed")
        except Exception as e:
            logger.error(f"Error applying settings: {e}")
    
    def refresh_all_canvases(self):
        """Refresh all matplotlib canvases to apply new settings"""
        try:
            # Refresh main canvas
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.draw()
            
            # Refresh any other canvases that might exist
            from styles.theme import refresh_matplotlib_canvases
            refresh_matplotlib_canvases()
            
            logger.info("All canvases refreshed")
        except Exception as e:
            logger.error(f"Error refreshing canvases: {e}")
    
    def change_plot_style(self, style, save_config=True):
        """Change plot style and optionally save preference"""
        try:
            import matplotlib
            
            if style == "dark":
                # Try to load dark style file first
                style_path = os.path.join(os.path.dirname(__file__), "styles", "mpl_style_dark_pro.mplstyle")
                if os.path.exists(style_path):
                    plt.style.use(style_path)
                    logger.info("Dark style file loaded successfully")
                else:
                    # Apply fallback dark theme using rcParams
                    matplotlib.rcParams["figure.facecolor"] = "#1e1e1e"
                    matplotlib.rcParams["axes.facecolor"] = "#1e1e1e"
                    matplotlib.rcParams["axes.edgecolor"] = "#404040"
                    matplotlib.rcParams["axes.labelcolor"] = "#ffffff"
                    matplotlib.rcParams["xtick.color"] = "#ffffff"
                    matplotlib.rcParams["ytick.color"] = "#ffffff"
                    matplotlib.rcParams["text.color"] = "#ffffff"
                    matplotlib.rcParams["grid.color"] = "#404040"
                    matplotlib.rcParams["grid.alpha"] = 0.3
                    logger.info("Fallback dark theme applied")
                
                # Update menu check state
                if hasattr(self, 'actDarkStyle'):
                    self.actDarkStyle.setChecked(True)
                    self.actDefaultStyle.setChecked(False)
            
            elif style == "default":
                plt.style.use('default')
                # Reset to default colors
                matplotlib.rcParams["figure.facecolor"] = "white"
                matplotlib.rcParams["axes.facecolor"] = "white"
                matplotlib.rcParams["axes.edgecolor"] = "black"
                matplotlib.rcParams["axes.labelcolor"] = "black"
                matplotlib.rcParams["xtick.color"] = "black"
                matplotlib.rcParams["ytick.color"] = "black"
                matplotlib.rcParams["text.color"] = "black"
                matplotlib.rcParams["grid.color"] = "black"
                matplotlib.rcParams["grid.alpha"] = 0.3
                logger.info("Default theme applied")
                
                # Update menu check state
                if hasattr(self, 'actDarkStyle'):
                    self.actDarkStyle.setChecked(False)
                    self.actDefaultStyle.setChecked(True)
            
            # Force canvas redraw to apply new style
            if hasattr(self, 'canvas') and self.canvas:
                try:
                    # Clear and redraw canvas to apply new style
                    self.canvas.clear()
                    self.canvas.draw()
                    logger.info("Canvas redrawn with new style")
                except Exception as e:
                    logger.error(f"Canvas redraw error: {e}")
            
            # Save preference if requested
            if save_config:
                self._save_plot_style_config(style)
                
            self.statusBar().showMessage(f"Plot style changed to: {style.title()}")
            
        except Exception as e:
            QMessageBox.critical(self, "Style Change Failed", f"Failed to change plot style: {str(e)}")
            logger.error(f"Style change error: {e}")

    # ---------- File ----------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์ข้อมูล", "",
                    "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf);;All Files (*.*)")
        if not path: return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
                df, enc_note = load_tabular(path, ext)
                if df is None or df.empty:
                    raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
                name = f"{os.path.basename(path)} [ตาราง]"
                self._stage_insert(name, df, path)
            elif ext in [".nc", ".cdf"]:
                try:
                    df = load_cdf_nc_on_demand(self, path)
                    if df is None or df.empty:
                        raise ValueError("ไฟล์ CDF/NetCDF ไม่มีข้อมูลที่ใช้พล็อตได้")
                    name = f"{os.path.basename(path)} [CDF/NC]"
                    self._stage_insert(name, df, path)
                except Exception as e:
                    error_msg = f"ไม่สามารถอ่านไฟล์ CDF/NetCDF ได้:\n{str(e)}"
                    QMessageBox.critical(self, "ข้อผิดพลาด", error_msg)
                    return
            else:
                raise ValueError("นามสกุลไฟล์ไม่รองรับ")

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
                try:
                    df = load_cdf_nc_on_demand(self, path)
                    if df is None or df.empty: 
                        raise ValueError("อ่านไฟล์ CDF/NetCDF ไม่สำเร็จ หรือไม่มีข้อมูล")
                    self._df, self._current_path = df, path
                    self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (CDF/NetCDF)")
                    self.statusBar().showMessage("โหลดข้อมูลสำเร็จ (On‑Demand) • กด 'โหลดคอลัมน์'")
                    return
                except Exception as e:
                    error_msg = f"ไม่สามารถอ่านไฟล์ CDF/NetCDF ได้:\n{str(e)}"
                    QMessageBox.critical(self, "ข้อผิดพลาด", error_msg)
                    self.statusBar().showMessage("เกิดข้อผิดพลาดในการเปิดไฟล์ CDF/NetCDF")
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
        # UI-REFINE: sync คอลัมน์ของ Histogram ด้วย
        try:
            self.cbHist.clear(); self.cbHist.addItems(cols)
        except Exception:
            pass
        self.statusBar().showMessage("โหลดคอลัมน์เรียบร้อย • เลือก X/Y แล้วพล็อตได้")
        # UI-REFINE: อัปเดตจำนวนแถว
        try: self._sb_rows.setText(f"rows: {len(self._df)}")
        except Exception: pass

    # ---------- Plot ----------
    def _get_xy(self):
        if self._df is None:
            QMessageBox.warning(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'"); return None, None
        if self.cbX.count() == 0 or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่ได้โหลดคอลัมน์", "กดปุ่ม 'โหลดคอลัมน์จากข้อมูล' ก่อน"); return None, None

        x_col = self.cbX.currentText(); y_col = self.cbY.currentText()
        if x_col not in self._df.columns or y_col not in self._df.columns:
            QMessageBox.warning(self, "คอลัมน์ไม่ถูกต้อง", "โปรดเลือกคอลัมน์ X/Y ใหม่"); return None, None

        try:
            x = self._df[x_col].values; y = self._df[y_col].values
            
            # Convert Y to numeric with error handling
            try: 
                y = pd.to_numeric(y, errors="coerce")
            except Exception as e:
                print(f"Y column conversion error: {e}")
                y = pd.to_numeric(y, errors="coerce")  # Try again
            
            # Handle datetime X axis
            if np.issubdtype(type(x[0]), np.datetime64):
                mask = ~(pd.isna(y))
                x = x[mask]; y = y[mask]
            else:
                # Convert X to numeric with error handling
                try: 
                    x = pd.to_numeric(x, errors="coerce")
                except Exception as e:
                    print(f"X column conversion error: {e}")
                    x = pd.to_numeric(x, errors="coerce")  # Try again
                
                # Remove NaN values from both X and Y
                mask = ~(pd.isna(x) | pd.isna(y))
                x = x[mask]; y = y[mask]
            
            # Validate final data
            if len(x) == 0 or len(y) == 0:
                QMessageBox.warning(self, "ไม่มีข้อมูลที่ใช้ได้", "คอลัมน์ที่เลือกไม่มีข้อมูลตัวเลขที่ใช้พล็อตได้")
                return None, None
            
            if len(x) != len(y):
                QMessageBox.warning(self, "ข้อมูลไม่ตรงกัน", f"จำนวนข้อมูล X ({len(x)}) และ Y ({len(y)}) ไม่เท่ากัน")
                return None, None
            
            return x, y
            
        except Exception as e:
            QMessageBox.critical(self, "เกิดข้อผิดพลาดในการประมวลผลข้อมูล", f"สาเหตุ: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    def _is_datetime_column(self, col_name):
        """Check if a column contains datetime data"""
        if self._df is None or col_name not in self._df.columns:
            return False
        try:
            # Check if the column is already datetime type
            if pd.api.types.is_datetime64_any_dtype(self._df[col_name]):
                return True
            # Try to convert a sample to see if it's datetime
            sample = self._df[col_name].dropna().iloc[:5] if not self._df[col_name].empty else pd.Series()
            if not sample.empty:
                pd.to_datetime(sample, errors="coerce")
                return True
        except Exception:
            pass
        return False

    def plot_line(self):
        x, y = self._get_xy()
        if x is None: return
        
        try:
            lw = self.spLineWidth.value(); marker = "o" if self.chkMarker.isChecked() else None
            self.canvas.ax.plot(x, y, linewidth=lw, marker=marker, label=f"{self.cbY.currentText()} vs {self.cbX.currentText()}")
            self.canvas.ax.set_xlabel(self.cbX.currentText()); self.canvas.ax.set_ylabel(self.cbY.currentText())
            
            # Apply beautification with error handling
            try:
                beautify_axes(self.canvas.ax, x_is_datetime=self._is_datetime_column(self.cbX.currentText()))
            except Exception as beautify_error:
                print(f"Line plot beautify error: {beautify_error}")
            
            # Force canvas redraw
            try:
                self.canvas.draw()
                self.statusBar().showMessage("พล็อตกราฟเส้นสำเร็จ")
            except Exception as draw_error:
                print(f"Line plot draw error: {draw_error}")
                self.statusBar().showMessage("พล็อตกราฟเส้นสำเร็จ (การแสดงผลอาจมีปัญหา)")
                
        except Exception as e:
            QMessageBox.critical(self, "พล็อตกราฟเส้นไม่สำเร็จ", f"สาเหตุ: {e}")
            import traceback
            traceback.print_exc()

    def plot_scatter(self):
        x, y = self._get_xy()
        if x is None: return
        
        try:
            size = self.spLineWidth.value() * 5
            self.canvas.ax.scatter(x, y, s=size, label=f"{self.cbY.currentText()} vs {self.cbX.currentText()}")
            self.canvas.ax.set_xlabel(self.cbX.currentText()); self.canvas.ax.set_ylabel(self.cbY.currentText())
            
            # Apply beautification with error handling
            try:
                beautify_axes(self.canvas.ax, x_is_datetime=self._is_datetime_column(self.cbX.currentText()))
            except Exception as beautify_error:
                print(f"Scatter plot beautify error: {beautify_error}")
            
            # Force canvas redraw
            try:
                self.canvas.draw()
                self.statusBar().showMessage("พล็อตกราฟจุดสำเร็จ")
            except Exception as draw_error:
                print(f"Scatter plot draw error: {draw_error}")
                self.statusBar().showMessage("พล็อตกราฟจุดสำเร็จ (การแสดงผลอาจมีปัญหา)")
                
        except Exception as e:
            QMessageBox.critical(self, "พล็อตกราฟจุดไม่สำเร็จ", f"สาเหตุ: {e}")
            import traceback
            traceback.print_exc()

    # UI-REFINE: Plot Histogram
    def plot_histogram(self):
        if self._df is None or self._df.empty:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน"); return
        col = self.cbHist.currentText()
        if not col or col not in self._df.columns:
            QMessageBox.information(self, "เลือกคอลัมน์", "โปรดเลือกคอลัมน์ข้อมูลสำหรับฮิสโตแกรม"); return
        
        try:
            # Validate data
            vals = pd.to_numeric(self._df[col], errors="coerce").dropna().values
            if vals.size == 0:
                QMessageBox.information(self, "ไม่มีข้อมูล", "คอลัมน์ที่เลือกไม่มีค่าตัวเลข"); return
            
            bins = int(self.spHistBins.value())
            if bins <= 0:
                bins = 20  # Default fallback
            
            # Clear canvas and create histogram
            self.canvas.clear()
            
            # Create histogram with error handling
            try:
                n, b, _ = self.canvas.ax.hist(vals, bins=bins, alpha=0.7, color="#6aa0f8", edgecolor="#2d3a5a")
                # Use English labels to avoid font issues
                self.canvas.ax.set_xlabel(col)
                self.canvas.ax.set_ylabel("Count")
                self.canvas.ax.set_title(f"Histogram of {col} (bins={bins})")
            except Exception as hist_error:
                QMessageBox.critical(self, "สร้างฮิสโตแกรมไม่สำเร็จ", f"สาเหตุ: {hist_error}")
                return

            # ออปชัน: ฟิต Gaussian
            if self.chkHistFit.isChecked():
                try:
                    import numpy as _np
                    from math import sqrt, pi, exp
                    # ไม่เพิ่ม dependency ใหม่: ใช้ค่าเฉลี่ย/ส่วนเบี่ยงเบนมาตรฐานจาก numpy และวาด pdf เอง
                    mu = float(_np.mean(vals))
                    sigma = float(_np.std(vals, ddof=0)) if vals.size > 0 else 0.0
                    if sigma > 0:
                        xs = _np.linspace(b[0], b[-1], 400)
                        # สเกล pdf ให้เข้ากับสเกล histogram: pdf * N * bin_width
                        bin_w = (b[-1] - b[0]) / bins if bins > 0 else 1.0
                        pdf = (1.0/(sigma*sqrt(2*pi))) * _np.exp(-0.5*((xs-mu)/sigma)**2)
                        pdf_scaled = pdf * vals.size * bin_w
                        # Use English labels to avoid font issues
                        self.canvas.ax.plot(xs, pdf_scaled, color="#e36a6a", linewidth=2, label=f"Normal fit mu={mu:.2f}, sigma={sigma:.2f}")
                        self.canvas.ax.legend(loc="best")
                except Exception as fit_error:
                    print(f"Gaussian fit error: {fit_error}")  # Debug info

            # Apply beautification with error handling
            try:
                beautify_axes(self.canvas.ax)
            except Exception as beautify_error:
                print(f"Beautify error: {beautify_error}")  # Debug info
            
            # Force canvas redraw with error handling
            try:
                self.canvas.draw()
                self.statusBar().showMessage("พล็อต Histogram สำเร็จ")
            except Exception as draw_error:
                print(f"Canvas draw error: {draw_error}")  # Debug info
                # Try alternative redraw method
                try:
                    self.canvas.figure.canvas.draw()
                    self.statusBar().showMessage("พล็อต Histogram สำเร็จ (ใช้วิธีสำรอง)")
                except Exception:
                    QMessageBox.warning(self, "การวาดกราฟ", "กราฟถูกสร้างแล้วแต่การแสดงผลอาจมีปัญหา")
                    self.statusBar().showMessage("พล็อต Histogram สำเร็จ (การแสดงผลอาจมีปัญหา)")
                
        except Exception as e:
            QMessageBox.critical(self, "พล็อตไม่สำเร็จ", f"สาเหตุ: {e}")
            import traceback
            traceback.print_exc()  # Debug info

    # UI-REFINE: วาดกราฟแท่งแบบง่าย
    def plot_bar(self, x, y, *, xlabel: str = "", ylabel: str = "", title: str = ""):
        self.canvas.clear()
        self.canvas.ax.bar(range(len(x)), y)
        self.canvas.ax.set_xticks(range(len(x)))
        try:
            self.canvas.ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
        except Exception:
            pass
        if xlabel: self.canvas.ax.set_xlabel(xlabel)
        if ylabel: self.canvas.ax.set_ylabel(ylabel)
        if title: self.canvas.ax.set_title(title)
        beautify_axes(self.canvas.ax, title=title)

    # UI-REFINE: wrapper สำหรับ Aggregate ไม่แตะ logic core
    def _aggregate_and_plot(self, df: pd.DataFrame, id_col: str, value_cols: list[str], agg: str, stacked: bool = False):
        import pandas as pd
        if not id_col or not value_cols:
            return
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

        # Plot: if multiple columns selected
        self.canvas.clear()
        x = out[id_col]
        if len(value_cols) == 1 or not stacked:
            # Use first column for bar chart
            y = out[value_cols[0]]
            self.plot_bar(x=x, y=y, xlabel=id_col, ylabel=f"{agg}({value_cols[0]})", title=f"{agg} by {id_col}")
        else:
            import numpy as _np
            ind = _np.arange(len(x))
            bottom = _np.zeros(len(x))
            for col in value_cols:
                vals = out[col].values
                self.canvas.ax.bar(ind, vals, bottom=bottom, label=col)
                bottom = bottom + vals
            self.canvas.ax.set_xticks(ind)
            self.canvas.ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
            self.canvas.ax.set_xlabel(id_col)
            self.canvas.ax.set_ylabel(f"{agg}(values)")
            # Use English title to avoid font issues
            self.canvas.ax.set_title(f"{agg} by {id_col} (stacked)")
            beautify_axes(self.canvas.ax, title=f"{agg} by {id_col} (stacked)")

        # Store result for Export
        self.current_aggregated_df = out
        self.statusBar().showMessage("Aggregate successful • Use Export tab to save results")

    # UI-REFINE: เปิด dialog Aggregate และเรียกใช้งาน
    def run_aggregate_dialog(self):
        if self._df is None or self._df.empty:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์ก่อน"); return
        cols = [str(c) for c in self._df.columns]
        dlg = AggregateDialog(self, self._df, cols)
        if dlg.exec() != QDialog.Accepted:
            return
        params = dlg.get_params()
        id_col = params.get("id_col"); value_cols = params.get("value_cols", []); agg = params.get("agg", "sum"); stacked = bool(params.get("stacked", False))
        try:
            self._aggregate_and_plot(self._df, id_col=id_col, value_cols=value_cols, agg=agg, stacked=stacked)
        except Exception as e:
            QMessageBox.critical(self, "Aggregate failed", f"Reason: {e}")

    # UI-REFINE: ส่งออกผล Aggregate เป็น CSV
    def export_aggregated_csv(self):
        if getattr(self, "current_aggregated_df", None) is None:
            QMessageBox.information(self, "No Aggregate result", "Please run Aggregate first"); return
        path, _ = QFileDialog.getSaveFileName(self, "Save Aggregate result as CSV", "aggregate.csv", "CSV (*.csv)")
        if not path: return
        try:
            self.current_aggregated_df.to_csv(path, index=False)
            self.statusBar().showMessage(f"Aggregate CSV saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", f"Reason: {e}")

    # UI-FIT: เปิด FitDialog และเตรียมข้อมูลซีรีส์ปัจจุบัน
    def _open_fit_dialog(self):
            # สร้าง mapping label → (x,y) จากสิ่งที่พล็อตอยู่ในแกน
            axes = self.canvas.ax
            series_data = {}
            series_is_seconds: dict[str, bool] = {}  # UI-FIT: ระบุว่า x ถูกแปลงเป็นวินาทีจากต้นทาง
            labels = []
            try:
                for line in axes.get_lines():
                    lbl = line.get_label() or "series"
                    if lbl.startswith("_"):  # เส้นพิเศษของ Matplotlib
                        continue
                    # UI-FIT: พยายามใช้ข้อมูลดิบจาก DataFrame ตาม label "Y vs X"
                    x = line.get_xdata(); y = line.get_ydata()
                    x_arr = np.asarray(x); y_arr = np.asarray(y)
                    used_seconds = False
                    try:
                        if self._df is not None and " vs " in lbl:
                            y_name, x_name = [s.strip() for s in lbl.split(" vs ", 1)]
                            if x_name in self._df.columns and y_name in self._df.columns:
                                x_ser = self._df[x_name]
                                y_ser = self._df[y_name]
                                # แปลง X เป็นวินาทีหากเป็นเวลา
                                try:
                                    xs_dt = pd.to_datetime(x_ser, errors="coerce")
                                    if xs_dt.notna().sum() >= 2:
                                        delta = (xs_dt - xs_dt.iloc[0]).dt.total_seconds()
                                        x_arr = delta.values
                                        y_arr = pd.to_numeric(y_ser, errors="coerce").values
                                        used_seconds = True
                                    else:
                                        # ไม่ใช่ datetime → ใช้ตัวเลขเดิม
                                        x_arr = pd.to_numeric(x_ser, errors="coerce").values
                                        y_arr = pd.to_numeric(y_ser, errors="coerce").values
                                except Exception:
                                    x_arr = pd.to_numeric(x_ser, errors="coerce").values
                                    y_arr = pd.to_numeric(y_ser, errors="coerce").values
                    except Exception:
                        pass
                    labels.append(lbl)
                    series_data[lbl] = (x_arr, y_arr)
                    series_is_seconds[lbl] = used_seconds
            except Exception:
                pass
            if not labels:
                QMessageBox.information(self, "No series", "No lines/points on graph to fit"); return
            dlg = FitDialog(self, labels, series_data)
            if dlg.exec() != QDialog.Accepted:
                return
            params = dlg.get_params()
            lbl = params.get("series_label"); model = params.get("model"); deg = params.get("degree")
            show_eq = bool(params.get("show_eq", True)); show_resid = bool(params.get("show_resid", False))
            x, y = series_data.get(lbl, (None, None))
            if x is None or y is None:
                return
            try:
                used_seconds = bool(series_is_seconds.get(lbl, False))
                model_l = (model or "linear").lower()
                if used_seconds and model_l in ("linear", "polynomial"):
                    # CHANGE: ฟิตโดยแปลง X เป็นวินาทีจากต้นทาง แล้วแปลงกลับ datetime สำหรับพล็อต
                    x_name = None; y_name = None
                    try:
                        if " vs " in lbl:
                            y_name, x_name = [s.strip() for s in lbl.split(" vs ", 1)]
                    except Exception:
                        pass
                    
                    if x_name and y_name and (x_name in self._df.columns) and (y_name in self._df.columns):
                        order = 1 if model_l == "linear" else max(2, int(deg or 2))
                        x_fit_dt, y_fit, meta = fit_poly_datetime(self._df[x_name], self._df[y_name], order=order)
                        # คำนวณ metrics บนสเกลเดียวกับตอนฟิต
                        t_sec, _t0 = _to_seconds_from_start(self._df[x_name])
                        scale = float(max(np.max(t_sec) - np.min(t_sec), 1.0))
                        t_scaled = (t_sec - float(np.mean(t_sec))) / scale
                        p = np.poly1d(meta.get("coeffs"))
                        y_arr = np.asarray(self._df[y_name], dtype=float)
                        y_pred = p(t_scaled)
                        resid = y_arr - y_pred
                        rmse = float(np.sqrt(np.mean(resid**2)))
                        ss_res = float(np.sum(resid**2))
                        ss_tot = float(np.sum((y_arr - float(np.mean(y_arr)))**2))
                        r2 = (1.0 - ss_res/ss_tot) if ss_tot > 0 else float("nan")
                        metrics = {"r2": r2, "rmse": rmse}
                        # วาดเส้นบนแกนเวลาเดิม
                        self._plot_fit_overlay(lbl, x_fit_dt, y_fit, meta, metrics, show_eq=show_eq, show_resid=show_resid, x_seconds=False)
                        try:
                            self.canvas.ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
                            self.canvas.fig.autofmt_xdate()
                            self.canvas.draw()
                        except Exception:
                            pass
                        # เก็บผล
                        self.current_fit_result = {
                            "series": lbl,
                            "model": model,
                            "params": meta,
                            "metrics": metrics,
                            "xfit": x_fit_dt,
                            "yfit": y_fit,
                        }
                    else:
                        # fallback: ใช้เส้นทางเดิม
                        xfit, yfit, fit_params, metrics = self._do_curve_fit(np.asarray(x), np.asarray(y), model=model, degree=deg)
                        self._plot_fit_overlay(lbl, xfit, yfit, fit_params, metrics, show_eq=show_eq, show_resid=show_resid, x_seconds=used_seconds)
                        self.current_fit_result = {"series": lbl, "model": model, "params": fit_params, "metrics": metrics, "xfit": xfit, "yfit": yfit}
                else:
                    # เดิม: ฟิตบน x ที่เป็นตัวเลขอยู่แล้ว
                    xfit, yfit, fit_params, metrics = self._do_curve_fit(np.asarray(x), np.asarray(y), model=model, degree=deg)
                    self._plot_fit_overlay(lbl, xfit, yfit, fit_params, metrics, show_eq=show_eq, show_resid=show_resid, x_seconds=used_seconds)
                    # เก็บผลเพื่อ export
                    self.current_fit_result = {
                        "series": lbl,
                        "model": model,
                        "params": fit_params,
                        "metrics": metrics,
                        "xfit": xfit,
                        "yfit": yfit,
                    }
            except Exception as e:
                QMessageBox.critical(self, "Fit failed", f"Reason: {e}")

    # UI-FIT: ทำการฟิต (SciPy ถ้ามี; fallback ด้วย NumPy)
    def _do_curve_fit(self, x: np.ndarray, y: np.ndarray, *, model: str, degree: int | None = None):
        import numpy as _np
        # clean
        mask = _np.isfinite(x) & _np.isfinite(y)
        x = _np.asarray(x)[mask]; y = _np.asarray(y)[mask]
        if x.size < 3:  # แก้ไข: ลดจาก 5 เป็น 3 เพื่อให้ยืดหยุ่นมากขึ้น
            raise ValueError("ข้อมูลน้อยเกินไปสำหรับการฟิต (ต้องการอย่างน้อย 3 จุด)")

        # สร้างจุดสำหรับวาดเส้นฟิต
        xs = _np.linspace(_np.nanmin(x), _np.nanmax(x), 400)

        def metrics(y_true, y_pred):
            resid = y_true - y_pred
            ss_res = float(_np.sum(resid**2))
            ss_tot = float(_np.sum((y_true - _np.mean(y_true))**2)) + 1e-12
            r2 = 1.0 - ss_res/ss_tot
            rmse = float(_np.sqrt(ss_res/max(1, y_true.size)))
            return {"r2": r2, "rmse": rmse}

        # พยายามใช้ SciPy ก่อน
        try:
            import scipy.optimize as opt  # type: ignore
            import scipy.stats as stats  # type: ignore
        except Exception:
            opt = None; stats = None

        model = (model or "linear").lower()

        if model == "linear":
            c = _np.polyfit(x, y, 1); p = _np.poly1d(c)
            yhat = p(xs); yfit = p(xs)  # แก้ไข: ใช้ xs แทน x สำหรับ yhat
            return xs, yfit, {"coeff": c.tolist()}, metrics(y, yhat)

        if model == "polynomial":
            d = max(2, int(degree or 2))
            c = _np.polyfit(x, y, d); p = _np.poly1d(c)
            yhat = p(xs); yfit = p(xs)  # แก้ไข: ใช้ xs แทน x สำหรับ yhat
            return xs, yfit, {"coeff": c.tolist(), "degree": d}, metrics(y, yhat)

        if model == "exponential":
            # y ~ a*exp(bx) + c
            def f(xv, a, b, c0):
                return a * _np.exp(b*xv) + c0
            if opt is not None:
                p0 = [max(1e-6, float(_np.nanmax(y))), 0.0, float(_np.nanmin(y))]
                popt, _ = opt.curve_fit(f, x, y, p0=p0, maxfev=10000)
                yhat = f(xs, *popt); yfit = f(xs, *popt)  # แก้ไข: ใช้ xs แทน x สำหรับ yhat
                return xs, yfit, {"a": float(popt[0]), "b": float(popt[1]), "c": float(popt[2])}, metrics(y, yhat)
            # fallback: log-linear ด้วย c0≈min
            c0 = float(_np.nanmin(y))
            y1 = _np.clip(y - c0, 1e-9, _np.inf)
            b, a0 = _np.polyfit(x, _np.log(y1), 1)
            a = float(_np.exp(a0))
            yhat = a*_np.exp(b*x)+c0; yfit = a*_np.exp(b*xs)+c0
            return xs, yfit, {"a": a, "b": float(b), "c": c0}, metrics(y, yhat)

        if model == "power":
            # y ~ a*x^b (x>0,y>0)
            m = (x>0) & (y>0)
            if m.sum() < 2:
                raise ValueError("Power-law ต้องการ x,y > 0 อย่างน้อย 2 จุด")
            if opt is not None:
                def f(xv, a, b):
                    return a * (xv**b)
                p0 = [float(_np.nanmax(y)), 1.0]
                popt, _ = opt.curve_fit(f, x[m], y[m], p0=p0, maxfev=10000)
                yhat = f(xs, *popt); yfit = f(xs, *popt)  # แก้ไข: ใช้ xs แทน x[m] สำหรับ yhat
                return xs, yfit, {"a": float(popt[0]), "b": float(popt[1])}, metrics(y, yhat)
            b, a0 = _np.polyfit(_np.log(x[m]), _np.log(y[m]), 1)
            a = float(_np.exp(a0))
            yhat = a*(x**b); yfit = a*(xs**b)
            return xs, yfit, {"a": a, "b": float(b)}, metrics(y, yhat)

        if model == "gaussian":
            # y ~ A*exp(-(x-μ)^2/(2σ^2)) + C
            def g(xv, A, mu, sig, C0):
                return A * _np.exp(-0.5*((xv-mu)/sig)**2) + C0
            if opt is not None:
                mu0 = float(x[_np.argmax(y)])
                sig0 = float(max(1e-6, ( _np.percentile(x,95) - _np.percentile(x,5) )/4.0))
                p0 = [float(_np.nanmax(y)), mu0, sig0, float(_np.nanmin(y))]
                popt, _ = opt.curve_fit(g, x, y, p0=p0, maxfev=20000)
                yhat = g(xs, *popt); yfit = g(xs, *popt)  # แก้ไข: ใช้ xs แทน x สำหรับ yhat
                return xs, yfit, {"A": float(popt[0]), "mu": float(popt[1]), "sigma": float(popt[2]), "C": float(popt[3])}, metrics(y, yhat)
            # fallback: LS เชิงเส้นสำหรับ A,C หลังตั้ง mu,sigma คร่าว ๆ
            mu = float(x[_np.argmax(y)])
            sig = float(max(1e-6, ( _np.percentile(x,95) - _np.percentile(x,5) )/4.0))
            G = _np.exp(-0.5*((x-mu)/sig)**2)
            X = _np.vstack([G, _np.ones_like(G)]).T
            sol, *_ = _np.linalg.lstsq(X, y, rcond=None)
            A, C0 = float(sol[0]), float(sol[1])
            yhat = A*_np.exp(-0.5*((x-mu)/sig)**2)+C0
            yfit = A*_np.exp(-0.5*((xs-mu)/sig)**2)+C0
            return xs, yfit, {"A": A, "mu": mu, "sigma": sig, "C": C0}, metrics(y, yhat)

        # sine
        # y ~ A*sin(2π f x + φ) + C → หา f จาก FFT, แล้ว LS หาค่าอื่น
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
        w = 2*_np.pi*f0
        S = _np.sin(w*x); Cc = _np.cos(w*x)
        A_mat = _np.vstack([S, Cc, _np.ones_like(S)]).T
        beta, *_ = _np.linalg.lstsq(A_mat, y, rcond=None)
        s, c, c0 = beta
        A = float(_np.sqrt(s**2 + c**2)); phi = float(_np.arctan2(c, s)); C0 = float(c0)
        yhat = A*_np.sin(w*x + phi) + C0
        yfit = A*_np.sin(w*xs + phi) + C0
        return xs, yfit, {"A": A, "f": f0, "phi": phi, "C": C0}, metrics(y, yhat)

    # UI-FIT: วาดเส้นฟิตทับ พร้อม annotation/metrics และ residuals
    def _plot_fit_overlay(self, series_label: str, xfit: np.ndarray, yfit: np.ndarray, params: dict, metrics: dict, *, show_eq: bool, show_resid: bool, x_seconds: bool = False):
        ax = self.canvas.ax
        ax.plot(xfit, yfit, "-", linewidth=2, color="#E67E22", label=f"fit: {series_label}")
        beautify_axes(ax, x_is_datetime=x_seconds)
        # annotation สมการอย่างย่อ
        if show_eq:
            try:
                text = ", ".join([f"{k}={float(v):.3g}" for k,v in params.items() if isinstance(v,(int,float))])
                text += f" | R²={metrics.get('r2', float('nan')):.3f}, RMSE={metrics.get('rmse', float('nan')):.3g}"
                if x_seconds:
                    text += " | x (seconds from start)"
                ax.text(0.01, 0.99, text, transform=ax.transAxes, va="top", ha="left", fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.2", fc="#222", ec="#666", alpha=0.8))
            except Exception:
                pass
        self.statusBar().showMessage(f"Fit สำเร็จ • R²={metrics.get('r2', float('nan')):.3f}  RMSE={metrics.get('rmse', float('nan')):.3g}")

    # ---------- Features ----------
    def feature_add_bkk_time(self):
        if self._df is None or self.cbX.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        x_col = self.cbX.currentText()
        try:
            new_col = add_time_bangkok(self._df, x_col)
            self.cbX.addItem(new_col)
            self.statusBar().showMessage(f"เพิ่มคอลัมน์เวลา (Bangkok) แล้ว: {new_col}")
        except Exception as e:
            QMessageBox.critical(self, "ทำไม่สำเร็จ", f"สาเหตุ: {e}")

    def feature_add_magnitude(self):
        if self._df is None or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน"); return
        cols = [str(c) for c in self._df.columns]
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
        mapping = dlg.get_mapping()
        try:
            apply_column_types(self._df, mapping)
            self.load_columns_from_df()
            self.statusBar().showMessage("แปลงชนิดข้อมูลคอลัมน์เรียบร้อย")
        except Exception as e:
            QMessageBox.critical(self, "แปลงไม่สำเร็จ", f"สาเหตุ: {e}")

    def run_fft_dialog(self):
        if self._df is None or self.cbX.count() == 0 or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์และกด 'โหลดคอลัมน์จากข้อมูล' ก่อน")
            return

        cols = [str(c) for c in self._df.columns]
        y_default = max(0, self.cbY.currentIndex())
        y_col, ok = QInputDialog.getItem(self, "เลือกคอลัมน์ Y สำหรับ FFT", "Y:", cols, y_default, False)
        if not ok: return

        window, ok = QInputDialog.getItem(self, "หน้าต่าง (window)", "ชนิด:", ["hanning", "hamming", "none"], 0, False)
        if not ok: return
        detrend_choice, ok = QInputDialog.getItem(self, "ลบค่าเฉลี่ยก่อนคำนวณ?", "detrend:", ["True", "False"], 0, False)
        if not ok: return
        detrend = (detrend_choice == "True")

        x_col = self.cbX.currentText()

        try:
            df_fft, fs = compute_fft(self._df, x_col=x_col, y_col=y_col, detrend=detrend, window=window)
            self._fft_df = df_fft
            self._fft_meta = {"fs": fs, "x_col": x_col, "y_col": y_col, "window": window, "detrend": detrend}

            self.canvas.clear()
            self.canvas.ax.plot(df_fft["freq_Hz"].values, df_fft["amplitude"].values, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("Amplitude")
            beautify_axes(self.canvas.ax, title=f"FFT of {y_col} (fs≈{fs:.3f} Hz, window={window}, detrend={detrend})")
            self.statusBar().showMessage("คำนวณ FFT เสร็จแล้ว • ใช้ Export FFT เพื่อบันทึกผลได้")

        except Exception as e:
            QMessageBox.critical(self, "FFT ไม่สำเร็จ", f"สาเหตุ: {e}")

    def export_fft_dialog(self):
        if self._fft_df is None or self._fft_df.empty:
            QMessageBox.information(self, "ยังไม่มีผล FFT", "โปรดคำนวณ FFT ก่อน (ปุ่ม FFT)")
            return

        kind, ok = QInputDialog.getItem(
            self, "เลือกชนิดไฟล์", "บันทึกเป็น:",
            ["CSV (.csv)", "Excel (.xlsx)", "NetCDF (.nc)"], 0, False
        )
        if not ok: return

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
                    meta = pd.DataFrame([self._fft_meta])
                    meta.to_excel(w, sheet_name="meta", index=False)
                self.statusBar().showMessage(f"บันทึก Excel แล้ว: {path}")
            except Exception as e:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

        else:  # NetCDF
            path, _ = QFileDialog.getSaveFileName(self, "บันทึกผล FFT เป็น NetCDF", "fft_result.nc", "NetCDF (*.nc)")
            if not path: return
            try:
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

        self._cursor = Cursor(self.canvas.ax, useblit=True, horizOn=True, vertOn=True)
        def _on_move(event):
            if event.inaxes != self.canvas.ax: return
            x, y = event.xdata, event.ydata
            try:
                if x is None or y is None: return
                # UI-REFINE: แสดงตำแหน่งเคอร์เซอร์ที่ StatusBar ถาวร
                self._sb_cursor.setText(f"x={x:.3g}, y={y:.3g}")
            except Exception:
                pass
        self._cid_motion = self.canvas.mpl_connect("motion_notify_event", _on_move)
        self.statusBar().showMessage("เปิด Crosshair แล้ว")
        self.canvas.draw()

    # UI-REFINE: toggle แสดง/ซ่อน Inspector (ขวา)
    def toggle_inspector(self, checked: bool):
        try:
            self._panel_right.setVisible(bool(checked))
        except Exception:
            pass

    def start_box_zoom(self):
        if self._rs is not None:
            try: self._rs.set_active(False)
            except Exception: pass
            self._rs = None

        ax = self.canvas.ax
        self.statusBar().showMessage("โหมดเลือกช่วง: ลากเมาส์คลุมพื้นที่ที่ต้องการซูม (คลิกซ้ายค้างแล้วลาก)")

        def _on_select(eclick, erelease):
            try:
                x1, y1 = eclick.xdata, eclick.ydata
                x2, y2 = erelease.xdata, erelease.ydata
                if None in (x1, y1, x2, y2): return
                xmin, xmax = sorted([x1, x2]); ymin, ymax = sorted([y1, y2])
                ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
                self.canvas.draw()
                self.statusBar().showMessage(f"ซูมช่วง X=({xmin}, {xmax})  Y=({ymin}, {ymax})")
            finally:
                if self._rs is not None:
                    try: self._rs.set_active(False)
                    except Exception: pass
                    self._rs = None

        self._rs = RectangleSelector(
            ax, _on_select, useblit=True, button=[1],
            interactive=False, minspanx=0, minspany=0, spancoords='data'
        )

    def export_visible_range_csv(self):
        if self._df is None or self.cbX.count() == 0:
            QMessageBox.information(self, "ยังไม่มีข้อมูล", "เปิดไฟล์และกด 'โหลดคอลัมน์' ก่อน")
            return

        ax = self.canvas.ax
        xmin, xmax = ax.get_xlim()

        xcol = self.cbX.currentText()
        xser = self._df[xcol]

        df_view = None
        try:
            # datetime
            if np.issubdtype(np.array(xser)[0].__class__, np.datetime64) or np.issubdtype(xser.dtype, np.datetime64):
                import matplotlib.dates as mdates
                xmin_dt = mdates.num2date(xmin); xmax_dt = mdates.num2date(xmax)
                mask = (pd.to_datetime(xser) >= xmin_dt) & (pd.to_datetime(xser) <= xmax_dt)
                df_view = self._df.loc[mask].copy()
            else:
                xnum = pd.to_numeric(xser, errors="coerce")
                mask = (xnum >= xmin) & (xnum <= xmax)
                df_view = self._df.loc[mask].copy()
        except Exception:
            xnum = pd.to_numeric(xser, errors="coerce")
            mask = (xnum >= xmin) & (xnum <= xmax)
            df_view = self._df.loc[mask].copy()

        if df_view is None or df_view.empty:
            QMessageBox.information(self, "ไม่มีข้อมูลในช่วงนี้", "ช่วงที่แสดงอยู่ไม่มีข้อมูลให้ส่งออก")
            return

        path, _ = QFileDialog.getSaveFileName(self, "บันทึกช่วงที่เห็นเป็น CSV", "view_range.csv", "CSV (*.csv)")
        if not path: return
        try:
            df_view.to_csv(path, index=False)
            self.statusBar().showMessage(f"บันทึก CSV ช่วงที่เห็นแล้ว: {path}")
        except Exception as e:
            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def _stage_insert(self, name: str, df: pd.DataFrame, path: str):
        base = name; i = 2
        while name in self._datasets:
            name = f"{base} ({i})"; i += 1
        self._datasets[name] = {"df": df, "path": path}
        self.lstFiles.addItem(QListWidgetItem(name))
        self.statusBar().showMessage(f"เตรียมไฟล์: {name}")

    def stage_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "เลือกไฟล์เพื่อเตรียมไว้",
            "", "Data Files (*.csv *.tsv *.txt *.xlsx *.nc *.cdf);;All Files (*.*)"
        )
        if not paths: return

        for path in paths:
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext in [".csv", ".txt", ".tsv", ".xlsx"]:
                    df, enc_note = load_tabular(path, ext)
                    if df is None or df.empty: raise ValueError("ไฟล์ตารางว่างหรืออ่านไม่สำเร็จ")
                    name = f"{os.path.basename(path)} [ตาราง]"
                    self._stage_insert(name, df, path)
                elif ext in [".nc", ".cdf"]:
                    try:
                        df = load_cdf_nc_on_demand(self, path)
                        if df is None or df.empty: 
                            raise ValueError("ไฟล์ CDF/NetCDF ไม่มีข้อมูลที่ใช้พล็อตได้")
                        name = f"{os.path.basename(path)} [CDF/NC]"
                        self._stage_insert(name, df, path)
                    except Exception as e:
                        error_msg = f"ไม่สามารถอ่านไฟล์ CDF/NetCDF ได้:\n{str(e)}"
                        QMessageBox.critical(self, "ข้อผิดพลาด", error_msg)
                        continue
                else:
                    QMessageBox.information(self, "ข้ามไฟล์", f"นามสกุลไม่รองรับ: {path}")
            except Exception as e:
                QMessageBox.warning(self, "เพิ่มไฟล์ไม่สำเร็จ", f"{os.path.basename(path)}\nสาเหตุ: {e}")

    def stage_use_selected(self):
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

    def stage_remove_selected(self):
        row = self.lstFiles.currentRow()
        if row < 0:
            QMessageBox.information(self, "ยังไม่ได้เลือก", "โปรดเลือกไฟล์จากรายการก่อน")
            return
        item = self.lstFiles.item(row)
        name = item.text()
        if self._current_path and name in self._datasets and self._datasets[name]["path"] == self._current_path:
            ans = QMessageBox.question(self, "กำลังใช้งานไฟล์นี้อยู่", "ไฟล์นี้กำลังถูกใช้งานอยู่ ต้องการลบออกจากรายการหรือไม่?")
            if ans != QMessageBox.Yes:
                return
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

    # CHANGE: helper โหลดไอคอนจากโฟลเดอร์ logo หรือ fallback เป็น QStyle
    def _icon(self, name: str, fallback_sp: QStyle.StandardPixmap) -> QIcon:
        try:
            base = os.path.dirname(__file__)
            # ลองหาไอคอนในโฟลเดอร์ logo ก่อน (PNG format)
            logo_path = os.path.join(base, "logo", f"{name}.png")
            if os.path.isfile(logo_path):
                return QIcon(logo_path)
            
            # ถ้าไม่มีใน logo ลองหาใน assets/icons (SVG format)
            assets_path = os.path.join(base, "assets", "icons", f"{name}.svg")
            if os.path.isfile(assets_path):
                return QIcon(assets_path)
        except Exception:
            pass
        try:
            return self.style().standardIcon(fallback_sp)
        except Exception:
            return QIcon()

    def show_about(self):
        QMessageBox.information(self, "เกี่ยวกับโปรแกรม",
            "SciPlotter (Modular + Features)\n"
            "ไฟล์แยกเป็น main/dialogs/loaders/processors\n"
            "ฟีเจอร์: เวลา+7h, |B|, Moving Average, FFT/Export\n"
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
    
    # Load and apply settings from configuration
    try:
        from styles.theme import apply_theme_from_config, apply_mpl_from_config
        app_config = settings_manager.get_appearance()
        mpl_config = settings_manager.get_matplotlib()
        
        # Apply Qt theme
        apply_theme_from_config(app, app_config)
        
        # Apply matplotlib settings
        apply_mpl_from_config(mpl_config)
        
        logger.info("Settings applied from configuration")
    except Exception as e:
        logger.error(f"Error applying settings from config: {e}")
        # Fallback to default theme
        apply_theme(app)
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
