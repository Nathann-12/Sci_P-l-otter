# main.py
import os, sys
import numpy as np
import pandas as pd
import logging
import locale
import json

# Set up logging (will be overridden by setup_logging() in main())
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ปิด matplotlib debug messages
import matplotlib
matplotlib.set_loglevel("WARNING")

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

# IMPORTANT: Set matplotlib backend BEFORE importing PySide6
import matplotlib
matplotlib.use('Qt5Agg')  # Force Qt5Agg backend
print(f"Debug: Matplotlib backend set to: {matplotlib.get_backend()}")

from PySide6 import QtGui
from PySide6.QtCore import Qt, QSize
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
from dialogs import DerivedColumnDialog  # UI-DERIVED: Derived Column dialog
from dialogs_spectrogram import SpectrogramDialog  # UI-SPECTROGRAM: Spectrogram dialog
from dialogs_units import UnitsDialog  # UI-UNITS: Units and calibration dialog
from core.units import UNIT_REGISTRY  # UI-UNITS: Unit registry for conversions
from processors import add_time_bangkok, add_magnitude, add_moving_average, apply_column_types, compute_fft
from processors import _to_seconds_from_start, fit_poly_datetime, beautify_axes  # CHANGE: datetime fit helpers + plot beautification
from processors_spectrogram import compute_spectrogram, compute_cwt, export_spectrogram_data  # UI-SPECTROGRAM: spectrogram functions
from styles.theme import apply_theme, apply_theme_from_config, apply_mpl_from_config, refresh_matplotlib_canvases  # UI-REFINE: ใช้ธีมอ่านง่าย
from settings import settings_manager
from dialogs_settings import SettingsDialog
from report_generator import export_report
from dialogs_report import ExportReportDialog
from dialogs_tabs import SelectTabsDialog
from core.logging_setup import setup_logging
from UI.widgets.error_panel import ErrorPanel
from annotations import AnnotationManager, AnnotationStyleDock, AnnotationListDialog
from crosscorr import CrossCorrManager, CrossCorrDock
from peaks import PeakDetectorManager, PeakDetectionDock

APP_TITLE = "SciPlotter (Modular + Features)"

class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig); self.setParent(parent)
        self.fig.tight_layout()
    
    def draw(self):
        """Draw the canvas with error handling"""
        try:
            print(f"Debug: PlotCanvas.draw() called")
            super().draw()
            print(f"Debug: PlotCanvas.draw() completed successfully")
        except Exception as e:
            print(f"Debug: PlotCanvas.draw() failed: {e}")
            try:
                self.fig.canvas.draw()
                print(f"Debug: Fallback fig.canvas.draw() completed successfully")
            except Exception as e2:
                print(f"Debug: Fallback fig.canvas.draw() failed: {e2}")
                try:
                    self.fig.canvas.draw_idle()
                    print(f"Debug: Fallback fig.canvas.draw_idle() completed successfully")
                except Exception as e3:
                    print(f"Debug: All draw methods failed: {e3}")
                    import traceback
                    traceback.print_exc()
    
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


class GraphTab(QWidget):
    """
    Individual graph tab containing a matplotlib canvas and toolbar.
    """
    def __init__(self, tab_id, name="Graph", parent=None):
        super().__init__(parent)
        self.tab_id = tab_id
        self.name = name
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create canvas
        self.canvas = PlotCanvas(self)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        # Add widgets to layout
        layout.addWidget(self.canvas)
        layout.addWidget(self.toolbar)
        
        # Hide toolbar by default (consistent with original)
        try:
            self.toolbar.setVisible(False)
        except Exception:
            pass
        
        # Set size policy
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Annotation manager per tab
        self.annotation_manager = AnnotationManager(self.canvas.fig, self.canvas.ax, self)

        # Context menu for analysis toggles
        try:
            self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
            self.canvas.customContextMenuRequested.connect(self._on_canvas_menu)
        except Exception:
            pass

    def _on_canvas_menu(self, pos):
        try:
            menu = QMenu(self)
            menu.addAction("Enable Multi-Cursor", lambda: self.parent().actCCEnable.toggle()).setCheckable(False)
            menu.addAction("Enable Peak Detection", lambda: self.parent().actPkEnable.toggle()).setCheckable(False)
            menu.addSeparator()
            menu.addAction("Annotate Peaks", lambda: self.parent().actPkAnnotate.toggle()).setCheckable(False)
            menu.exec(self.canvas.mapToGlobal(pos))
        except Exception:
            pass
        
    def clear(self):
        """Clear the canvas"""
        self.canvas.clear()
        
    def get_axes(self):
        """Get the matplotlib axes"""
        return self.canvas.ax
        
    def get_figure(self):
        """Get the matplotlib figure"""
        return self.canvas.fig
        
    def draw(self):
        """Draw the canvas with error handling"""
        try:
            print(f"Debug: GraphTab.draw() called for tab {self.tab_id}")
            self.canvas.draw()
            print(f"Debug: GraphTab.draw() completed successfully")
        except Exception as e:
            print(f"Debug: GraphTab.draw() failed: {e}")
            try:
                self.canvas.fig.canvas.draw()
                print(f"Debug: Fallback canvas.draw() completed successfully")
            except Exception as e2:
                print(f"Debug: Fallback canvas.draw() failed: {e2}")
                import traceback
                traceback.print_exc()


class TabManager(QTabWidget):
    """
    Manages multiple graph tabs with browser-like functionality.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab_counter = 0
        self.tabs = {}  # tab_id -> GraphTab
        
        # Set up tab widget properties
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setAcceptDrops(False)
        
        # Responsive tab bar for small window sizes
        try:
            from PySide6.QtCore import Qt
            self.setUsesScrollButtons(True)
            self.setDocumentMode(True)
            tb = self.tabBar()
            tb.setElideMode(Qt.ElideRight)
            tb.setExpanding(False)
        except Exception:
            pass
        
        # Connect signals
        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabBar().tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        
        # Create context menu for right-click rename
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        # Create initial tab
        self.add_tab("Graph 1")
        
    def add_tab(self, name=None):
        """Add a new graph tab"""
        self.tab_counter += 1
        if name is None:
            name = f"Graph {self.tab_counter}"
            
        tab_id = f"tab_{self.tab_counter}"
        graph_tab = GraphTab(tab_id, name, self)
        
        # Add to tab widget
        index = self.addTab(graph_tab, name)
        self.setCurrentIndex(index)
        
        # Store reference
        self.tabs[tab_id] = graph_tab
        
        return tab_id
        
    def _on_tab_close_requested(self, index):
        """Handle tab close request"""
        if self.count() <= 1:
            # Don't allow closing the last tab
            return
            
        # Remove tab
        tab_widget = self.widget(index)
        tab_id = None
        
        # Find tab_id for this widget
        for tid, tab in self.tabs.items():
            if tab == tab_widget:
                tab_id = tid
                break
                
        if tab_id:
            del self.tabs[tab_id]
            
        self.removeTab(index)
        
    def _on_tab_double_clicked(self, index):
        """Handle tab double-click for rename"""
        self._rename_tab(index)
        
    def _on_context_menu(self, position):
        """Handle right-click context menu"""
        tab_bar = self.tabBar()
        index = tab_bar.tabAt(position)
        
        if index >= 0:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self._rename_tab(index))
            
            menu.exec(self.mapToGlobal(position))
            
    def _rename_tab(self, index):
        """Rename a tab"""
        current_name = self.tabText(index)
        from PySide6.QtWidgets import QInputDialog
        
        new_name, ok = QInputDialog.getText(
            self, "Rename Tab", "Enter new tab name:", 
            text=current_name
        )
        
        if ok and new_name.strip():
            self.setTabText(index, new_name.strip())
            # Update the GraphTab name as well
            tab_widget = self.widget(index)
            if hasattr(tab_widget, 'name'):
                tab_widget.name = new_name.strip()
                
    def get_current_tab_id(self):
        """Get the current tab ID"""
        current_widget = self.currentWidget()
        for tab_id, tab in self.tabs.items():
            if tab == current_widget:
                return tab_id
        return None
        
    def get_open_tabs(self):
        """Get list of (tab_id, tab_name) tuples for open tabs"""
        result = []
        for i in range(self.count()):
            tab_widget = self.widget(i)
            tab_name = self.tabText(i)
            
            # Find tab_id for this widget
            for tab_id, tab in self.tabs.items():
                if tab == tab_widget:
                    result.append((tab_id, tab_name))
                    break
        return result
        
    def plot_to_tabs(self, tab_ids, x, y, label="", style="line", **kwargs):
        """
        Plot data to specified tabs.
        
        Args:
            tab_ids: List of tab IDs to plot to
            x: X data
            y: Y data  
            label: Plot label
            style: Plot style ('line', 'scatter', etc.)
            **kwargs: Additional plot parameters
        """
        print(f"Debug: plot_to_tabs called with {len(tab_ids)} tabs, style={style}, data length: x={len(x)}, y={len(y)}")
        
        for tab_id in tab_ids:
            if tab_id in self.tabs:
                tab = self.tabs[tab_id]
                ax = tab.get_axes()
                
                print(f"Debug: Plotting to tab {tab_id}, axes: {ax}")
                
                try:
                    # Clear existing plots first
                    ax.clear()
                    print(f"Debug: Cleared existing plots for tab {tab_id}")
                    
                    if style == "line":
                        line = ax.plot(x, y, label=label, **kwargs)
                        print(f"Debug: Line plot created: {line}")
                    elif style == "scatter":
                        scatter = ax.scatter(x, y, label=label, **kwargs)
                        print(f"Debug: Scatter plot created: {scatter}")
                    elif style == "bar":
                        bars = ax.bar(range(len(x)), y, label=label, **kwargs)
                        print(f"Debug: Bar plot created: {bars}")
                        # Set x-axis labels for bar plots
                        ax.set_xticks(range(len(x)))
                        try:
                            ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
                        except Exception:
                            pass
                    elif style == "histogram":
                        hist = ax.hist(y, label=label, **kwargs)
                        print(f"Debug: Histogram created: {hist}")
                    else:
                        # Default to line plot
                        line = ax.plot(x, y, label=label, **kwargs)
                        print(f"Debug: Default line plot created: {line}")
                    
                    # Force update the plot
                    ax.relim()
                    ax.autoscale_view()
                    print(f"Debug: Applied relim() and autoscale_view() for tab {tab_id}")
                    
                    # Set basic formatting
                    ax.grid(True, alpha=0.3)
                    if label:
                        ax.legend()
                    print(f"Debug: Applied grid and legend for tab {tab_id}")
                    
                    # Force figure update
                    tab.canvas.fig.tight_layout()
                    print(f"Debug: Applied tight_layout for tab {tab_id}")
                    
                    # Draw the canvas with multiple methods
                    try:
                        tab.draw()
                        print(f"Debug: Tab draw() called successfully")
                    except Exception as e:
                        print(f"Debug: Tab draw() failed: {e}")
                        try:
                            tab.canvas.draw()
                            print(f"Debug: Canvas draw() called successfully")
                        except Exception as e2:
                            print(f"Debug: Canvas draw() failed: {e2}")
                            try:
                                tab.canvas.fig.canvas.draw()
                                print(f"Debug: Figure canvas draw() called successfully")
                            except Exception as e3:
                                print(f"Debug: Figure canvas draw() failed: {e3}")
                                try:
                                    tab.canvas.fig.canvas.draw_idle()
                                    print(f"Debug: Figure canvas draw_idle() called successfully")
                                except Exception as e4:
                                    print(f"Debug: All draw methods failed: {e4}")
                    
                    # Force refresh with multiple methods
                    try:
                        tab.canvas.flush_events()
                        print(f"Debug: Canvas flush_events() called")
                    except Exception:
                        pass
                    
                    try:
                        tab.canvas.fig.canvas.flush_events()
                        print(f"Debug: Figure canvas flush_events() called")
                    except Exception:
                        pass
                    
                    # Force Qt update
                    try:
                        tab.canvas.update()
                        print(f"Debug: Canvas update() called")
                    except Exception:
                        pass
                    
                    # Force repaint
                    try:
                        tab.canvas.repaint()
                        print(f"Debug: Canvas repaint() called")
                    except Exception:
                        pass
                        
                except Exception as e:
                    print(f"Debug: Error plotting to tab {tab_id}: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"Warning: Tab ID {tab_id} not found in tabs dictionary")


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

        # กลาง = TabManager สำหรับกราฟหลายแท็บ
        mid = QWidget(self)
        mid_layout = QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)  # CHANGE: tight inner
        mid_layout.setSpacing(8)
        
        # สร้าง TabManager แทน canvas เดี่ยว
        self.tabs = TabManager(self)
        mid_layout.addWidget(self.tabs)
        
        # UI-REFINE: tabs ขยายเต็มที่
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.addWidget(mid)
        
        # Keep reference to current canvas for backward compatibility
        self.canvas = None  # Will be set by _update_canvas_reference
        self._update_canvas_reference()
        
        # Error Panel (hidden by default)
        self.error_panel = ErrorPanel(self)
        self.error_panel.hide()  # ซ่อนไว้ก่อน

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

        # Build toolbar with organized groups first (to create actions)
        self.build_toolbar()
        
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
        
        # Connect tab change signal to update canvas reference
        self.tabs.currentChanged.connect(self._update_canvas_reference)

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
        # UI-SPECTROGRAM: ปุ่ม Spectrogram
        self.btnSpectrogram = QPushButton("Spectrogram…"); tp.addWidget(self.btnSpectrogram)
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
        
        # เพิ่มเส้นแบ่ง
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        ex.addWidget(separator)
        
        # ปุ่ม Export Report เป็น PDF
        self.btnExportReport = QPushButton("Export Report (PDF)")
        ex.addWidget(self.btnExportReport)
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
            self.btnSpectrogram.clicked.connect(self.open_spectrogram_dialog)  # UI-SPECTROGRAM
            self.btnHist.clicked.connect(self.plot_histogram)  # UI-REFINE
            self.btnExport.clicked.connect(self.export_png)
            self.btnExportRange.clicked.connect(self.export_visible_range_csv)
            self.btnTZ.clicked.connect(self.feature_add_bkk_time)
            self.btnMag.clicked.connect(self.feature_add_magnitude)
            self.btnMA.clicked.connect(self.feature_add_moving_average)
            self.btnTypes.clicked.connect(self.feature_set_column_types)
            self.btnAgg.clicked.connect(self.run_aggregate_dialog)  # UI-REFINE
            self.btnExportAgg.clicked.connect(self.export_aggregated_csv)  # UI-REFINE
            self.btnExportReport.clicked.connect(self.on_export_report)  # Export Report PDF
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
        self.actOpen = fileMenu.addAction("เปิดข้อมูล (CSV/TSV/TXT/XLSX/NC/CDF)..."); self.actOpen.triggered.connect(self.open_file)
        fileMenu.addSeparator()
        actExport = fileMenu.addAction("บันทึกรูปภาพ (PNG)..."); actExport.triggered.connect(self.export_png)
        fileMenu.addSeparator()
        actExit = fileMenu.addAction("ออกจากโปรแกรม"); actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&มุมมอง")  # UI-REFINE: View
        actReset = viewMenu.addAction("รีเซ็ตมุมมองกราฟ")
        actReset.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True), self.canvas.ax.set_ylim(auto=True), self.canvas.draw()])
        
        viewMenu.addAction(self.actToggleInspector)
        
        # Test Error menu
        test_action = viewMenu.addAction("Raise Test Error")
        def _raise_test_error():
            try:
                raise RuntimeError("นี่คือเออเรอร์ทดสอบจากเมนู")
            except Exception:
                logging.getLogger("Demo").exception("เกิดข้อผิดพลาดทดสอบ")
        test_action.triggered.connect(_raise_test_error)
        
        # Plot Style submenu
        plotStyleMenu = viewMenu.addMenu("Plot Style")
        self.actDarkStyle = plotStyleMenu.addAction("Dark")
        self.actDefaultStyle = plotStyleMenu.addAction("Default")
        self.actDarkStyle.setCheckable(True)
        self.actDefaultStyle.setCheckable(True)
        self.actDarkStyle.triggered.connect(lambda: self.change_plot_style("dark"))
        self.actDefaultStyle.triggered.connect(lambda: self.change_plot_style("default"))

        dataMenu = m.addMenu("&Data")  # UI-UNITS: Data menu for units and calibration
        dataMenu.addAction("หน่วยและการสอบเทียบ…").triggered.connect(self.open_units_dialog)
        
        procMenu = m.addMenu("&Process")  # UI-REFINE: Process
        procMenu.addAction("FFT").triggered.connect(self.run_fft_dialog)
        procMenu.addAction("Spectrogram…").triggered.connect(self.open_spectrogram_dialog)  # UI-SPECTROGRAM
        procMenu.addAction("Moving Average").triggered.connect(self.feature_add_moving_average)
        procMenu.addAction("Add |B|").triggered.connect(self.feature_add_magnitude)
        procMenu.addAction("Add Bangkok Time").triggered.connect(self.feature_add_bkk_time)
        procMenu.addAction("Aggregate…").triggered.connect(self.run_aggregate_dialog)  # UI-REFINE

        exportMenu = m.addMenu("&Export")  # UI-REFINE: Export
        exportMenu.addAction("Export Visible CSV").triggered.connect(self.export_visible_range_csv)
        exportMenu.addAction("Export PNG").triggered.connect(self.export_png)
        exportMenu.addSeparator()
        exportMenu.addAction("Export Report (PDF)...").triggered.connect(self.on_export_report)

        toolsMenu = m.addMenu("&Tools")  # UI-REFINE: Tools
        toolsMenu.addAction(self.actSettings)

        helpMenu = m.addMenu("&ช่วยเหลือ")  # UI-REFINE: Help → Shortcuts
        actAbout = helpMenu.addAction("เกี่ยวกับโปรแกรม"); actAbout.triggered.connect(self.show_about)
        # อัปเดตช็อตคัตให้ครอบคลุมฟีเจอร์ใหม่ (Annotation/Analysis)
        help_shortcuts = (
            "CTRL+O: Open\n"
            "CTRL+R: Reset View\n"
            "CTRL+E: Export PNG (ภาพกราฟ)\n"
            "CTRL+, : Settings\n"
            "\n[Annotation]\n"
            "T/W/L/R/E/C: Add Text/Arrow/Line/Rect/Ellipse/Callout\n"
            "Double-Click Text: Edit content\n"
            "CTRL+Z / CTRL+Y: Undo / Redo\n"
            "\n[Analysis]\n"
            "CTRL+Shift+X: Toggle Multi-Cursor\n"
            "CTRL+Shift+P: Toggle Peak Detection\n"
            "CTRL+D: Detect Peaks in Range\n"
            "CTRL+E: Export Peak Table (CSV/Excel)\n"
            "\n[Other]\n"
            "F: FFT Dialog\n"
            "I: Toggle Inspector"
        )
        helpMenu.addAction("Shortcuts").triggered.connect(lambda: QMessageBox.information(self, "Shortcuts", help_shortcuts))

        # === Analysis Menu ===
        analysisMenu = m.addMenu("&Analysis")

        # Cross-Correlation submenu
        ccMenu = analysisMenu.addMenu("Cross-Correlation")
        self.actCCEnable = ccMenu.addAction("Enable Multi-Cursor Mode"); self.actCCEnable.setCheckable(True); self.actCCEnable.setShortcut("Ctrl+Shift+X")
        self.actCCWindow = ccMenu.addAction("Window…")
        self.actCCLink = ccMenu.addAction("Link Axes by X-Time"); self.actCCLink.setCheckable(True)
        self.actCCCompute = ccMenu.addAction("Compute in Range")
        self.actCCClear = ccMenu.addAction("Clear Results")

        # Peak Detection submenu
        pkMenu = analysisMenu.addMenu("Peak Detection")
        self.actPkEnable = pkMenu.addAction("Enable Peak Detection"); self.actPkEnable.setCheckable(True); self.actPkEnable.setShortcut("Ctrl+Shift+P")
        self.actPkSettings = pkMenu.addAction("Settings…")
        self.actPkDetect = pkMenu.addAction("Detect in Range"); self.actPkDetect.setShortcut("Ctrl+D")
        self.actPkAnnotate = pkMenu.addAction("Annotate Peaks"); self.actPkAnnotate.setCheckable(True)
        self.actPkExport = pkMenu.addAction("Export Peak Table (CSV/Excel)"); self.actPkExport.setShortcut("Ctrl+E")
        self.actPkClear = pkMenu.addAction("Clear Peaks")

        # Docks + managers
        self.ccDock = CrossCorrDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.ccDock); self.ccDock.hide()
        self.crosscorr = CrossCorrManager(self)
        self.pkDock = PeakDetectionDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.pkDock); self.pkDock.hide()
        self.peaks = PeakDetectorManager(self)

        def populate_cols_into_docks():
            try:
                import pandas as pd
                df = getattr(self, '_df', None)
                cols = list(df.columns) if df is not None else []
            except Exception:
                cols = []
            self.ccDock.populate_columns(cols)
            self.pkDock.populate_columns(cols)

        populate_cols_into_docks()

        # Wire actions
        self.actCCEnable.toggled.connect(lambda on: self.crosscorr.set_enabled(on))
        self.actCCLink.toggled.connect(lambda on: self.crosscorr.set_link_axes(on))
        self.actCCWindow.triggered.connect(lambda: (populate_cols_into_docks(), self.ccDock.show()))
        self.ccDock.request_compute.connect(self._on_cc_compute)
        self.actCCCompute.triggered.connect(lambda: self.ccDock._emit_compute())
        self.actCCClear.triggered.connect(lambda: self.crosscorr._clear_vlines())

        self.actPkEnable.toggled.connect(lambda on: self.peaks.set_enabled(on))
        self.actPkSettings.triggered.connect(lambda: (populate_cols_into_docks(), self.pkDock.show()))
        self.pkDock.request_detect.connect(self._on_pk_detect)
        self.pkDock.request_annotate.connect(lambda _: self._on_pk_annotate(True))
        self.pkDock.request_clear.connect(lambda: (self.peaks.clear(), self.pkDock.table.setRowCount(0)))
        self.pkDock.request_export.connect(self._on_pk_export)
        self.actPkDetect.triggered.connect(lambda: self._on_pk_detect(self._collect_pk_params_from_menu()))
        self.actPkAnnotate.toggled.connect(lambda on: self._on_pk_annotate(on))
        self.actPkExport.triggered.connect(self._on_pk_export)
        self.actPkClear.triggered.connect(lambda: (self.peaks.clear(), self.pkDock.table.setRowCount(0)))

        # === Annotation Menu ===
        self.annMenu = m.addMenu("&Annotation")
        self.actAnnEnable = self.annMenu.addAction("Enable Annotation Mode")
        self.actAnnEnable.setCheckable(True)
        self.actAnnText = self.annMenu.addAction("Add Text (T)")
        self.actAnnArrow = self.annMenu.addAction("Add Arrow (W)")
        self.actAnnLine = self.annMenu.addAction("Add Line (L)")
        self.actAnnRect = self.annMenu.addAction("Add Rectangle (R)")
        self.actAnnEllipse = self.annMenu.addAction("Add Ellipse (E)")
        self.actAnnCallout = self.annMenu.addAction("Add Callout (C)")
        self.annMenu.addSeparator()
        self.actAnnStyleDock = self.annMenu.addAction("Style Dock…")
        self.actAnnManage = self.annMenu.addAction("Manage Annotations")

        # Shortcuts
        self.actAnnText.setShortcut("T")
        self.actAnnArrow.setShortcut("W")
        self.actAnnLine.setShortcut("L")
        self.actAnnRect.setShortcut("R")
        self.actAnnEllipse.setShortcut("E")
        self.actAnnCallout.setShortcut("C")

        self.actUndo = self.annMenu.addAction("Undo")
        self.actRedo = self.annMenu.addAction("Redo")
        self.actUndo.setShortcut("Ctrl+Z"); self.actRedo.setShortcut("Ctrl+Y")

        # Style dock
        self.annStyleDock = AnnotationStyleDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.annStyleDock)
        self.annStyleDock.hide()

        # Wire actions at runtime to current tab's manager
        def _mgr():
            tab = self.tabs.currentWidget()
            return getattr(tab, 'annotation_manager', None)

        self.actAnnEnable.toggled.connect(lambda on: (_mgr() and _mgr().set_enabled(on)))
        self.actAnnText.triggered.connect(lambda: (_mgr() and _mgr().set_mode('text')))
        self.actAnnArrow.triggered.connect(lambda: (_mgr() and _mgr().set_mode('arrow')))
        self.actAnnLine.triggered.connect(lambda: (_mgr() and _mgr().set_mode('line')))
        self.actAnnRect.triggered.connect(lambda: (_mgr() and _mgr().set_mode('rect')))
        self.actAnnEllipse.triggered.connect(lambda: (_mgr() and _mgr().set_mode('ellipse')))
        self.actAnnCallout.triggered.connect(lambda: (_mgr() and _mgr().set_mode('callout')))
        self.actAnnStyleDock.triggered.connect(lambda: self.annStyleDock.show())
        self.actAnnManage.triggered.connect(lambda: (_mgr() and AnnotationListDialog(_mgr(), self).exec()))
        self.actUndo.triggered.connect(lambda: (_mgr() and _mgr().undo()))
        self.actRedo.triggered.connect(lambda: (_mgr() and _mgr().redo()))

        self.annStyleDock.style_applied.connect(lambda st: (_mgr() and _mgr().set_style(st)))
        
        # Add keyboard shortcuts
        self.actOpen.setShortcut("Ctrl+O")
        self.actSettings.setShortcut("Ctrl+,")
        
        # UI-DERIVED: เพิ่มคีย์ลัดสำหรับ Create Derived Column
        derived_action = dataMenu.addAction("สร้างคอลัมน์ใหม่…")
        derived_action.setShortcut("Ctrl+D")
        derived_action.triggered.connect(self.open_derived_column_dialog)
        
        # Load saved plot style preference
        self._load_plot_style_config()
        
        # Load and apply settings from config
        self._load_and_apply_settings()

    def build_toolbar(self):
        """Build the main toolbar with organized groups"""
        self.tb = QToolBar("Main Toolbar", self)
        self.tb.setIconSize(QSize(24, 24))
        # Show icon + text on toolbar buttons for clarity
        try:
            from PySide6.QtCore import Qt
            self.tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        except Exception:
            pass
        self.addToolBar(self.tb)
        
        # Create toolbar actions
        self._create_toolbar_actions()
        
        # Apply styling
        self._apply_toolbar_styling()
    
    def _create_toolbar_actions(self):
        """Create all toolbar actions with proper grouping"""
        # สร้าง actions ที่จำเป็นถ้ายังไม่มี
        if not hasattr(self, 'actToggleInspector'):
            self.actToggleInspector = QAction("Inspector", self)
            self.actToggleInspector.setCheckable(True)
            self.actToggleInspector.triggered.connect(self.toggle_inspector)
            try:
                self.actToggleInspector.setIcon(self._icon("inspector", QStyle.StandardPixmap.SP_FileDialogInfoView))
            except Exception:
                pass
        
        if not hasattr(self, 'actOpen'):
            self.actOpen = QAction("Open", self)
            self.actOpen.triggered.connect(self.open_file)
            try:
                self.actOpen.setIcon(self._icon("open", QStyle.StandardPixmap.SP_DialogOpenButton))
            except Exception:
                pass
        
        if not hasattr(self, 'actSettings'):
            self.actSettings = QAction("Settings", self)
            self.actSettings.triggered.connect(self.show_settings)
        
        # === กลุ่มที่ 1: ไฟล์และข้อมูล ===
        self.tb.addAction(self.actOpen)
        # Place Inspector as the second button after Open
        self.tb.addAction(self.actToggleInspector)
        act_reload = self.tb.addAction("Reload", self.on_action_reload)
        try:
            act_reload.setIcon(self._icon("reload", QStyle.StandardPixmap.SP_BrowserReload))
        except Exception:
            pass
        self.tb.addSeparator()
        
        # === กลุ่มที่ 2: การสร้างกราฟ ===
        act_plot = self.tb.addAction("Plot", self.on_action_plot)
        act_spec = self.tb.addAction("Spectrogram", self.on_action_spectrogram)
        try:
            act_plot.setIcon(self._icon("plot", QStyle.StandardPixmap.SP_FileDialogContentsView))
            act_spec.setIcon(self._icon("fft", QStyle.StandardPixmap.SP_MediaPlay))
        except Exception:
            pass
        self.tb.addSeparator()
        
        # === กลุ่มที่ 3: การจัดการแท็บ ===
        act_add_tab = self.tb.addAction("Add Tab", self.on_action_add_tab)
        try:
            act_add_tab.setIcon(self._icon("add", QStyle.StandardPixmap.SP_FileDialogNewFolder))
        except Exception:
            pass
        self.tb.addSeparator()
        
        # === กลุ่มที่ 4: การประมวลผลข้อมูล ===
        act_processors = self.tb.addAction("Processors", self.on_action_open_processors)
        try:
            act_processors.setIcon(self._icon("settings", QStyle.StandardPixmap.SP_FileDialogDetailedView))
        except Exception:
            pass
        self.tb.addSeparator()
        
        # === กลุ่มที่ 5: การส่งออกข้อมูล ===
        act_export_fig = self.tb.addAction("Export Figure", self.on_action_export_figure)
        act_export_data = self.tb.addAction("Export Data", self.on_action_export_data)
        try:
            act_export_fig.setIcon(self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
            act_export_data.setIcon(self._icon("export", QStyle.StandardPixmap.SP_DialogSaveButton))
        except Exception:
            pass
        self.tb.addSeparator()
        
        # === กลุ่มที่ 6: การแสดงผลและเครื่องมือ ===
        # Inspector already added near the Open button for better access
        
        # Error Panel toggle
        self.actErrorPanel = self.tb.addAction("Error Panel")
        self.actErrorPanel.setCheckable(True)
        self.actErrorPanel.triggered.connect(self.toggle_error_panel)
        try:
            self.actErrorPanel.setIcon(self._icon("clear", QStyle.StandardPixmap.SP_MessageBoxWarning))
        except Exception:
            pass
        self.tb.addSeparator()
        
        # === กลุ่มที่ 7: การตั้งค่า (ขวาสุด) ===
        # Spacer เพื่อผลักปุ่ม Settings ไปขวาสุด
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tb.addWidget(spacer)
        
        self.tb.addAction(self.actSettings)
    
    def _apply_toolbar_styling(self):
        """Apply QSS styling to toolbar"""
        try:
            # Try to load from styles/toolbar.qss
            qss_path = os.path.join("styles", "toolbar.qss")
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    self.tb.setStyleSheet(f.read())
            else:
                # Enhanced toolbar styling
                self.tb.setStyleSheet("""
                    QToolBar {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #3a3a3a, stop:1 #2b2b2b);
                        border: none;
                        border-bottom: 1px solid #404040;
                        spacing: 6px;
                        padding: 4px 8px;
                        font-size: 11px;
                        font-weight: 500;
                    }
                    
                    QToolBar::separator {
                        background-color: #555555;
                        width: 1px;
                        margin: 6px 4px;
                        border-radius: 1px;
                    }
                    
                    QToolButton {
                        background-color: transparent;
                        border: 1px solid transparent;
                        border-radius: 6px;
                        padding: 6px 10px;
                        margin: 1px;
                        color: #e0e0e0;
                        font-size: 11px;
                        font-weight: 500;
                        min-width: 60px;
                        text-align: center;
                    }
                    
                    QToolButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #4a4a4a, stop:1 #3a3a3a);
                        border: 1px solid #666666;
                        color: #ffffff;
                    }
                    
                    QToolButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #0078d4, stop:1 #106ebe);
                        border: 1px solid #106ebe;
                        color: #ffffff;
                    }
                    
                    QToolButton:checked {
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #0078d4, stop:1 #106ebe);
                        border: 1px solid #106ebe;
                        color: #ffffff;
                    }
                    
                    /* Special styling for different groups */
                    QToolButton[text="Open"] {
                        background-color: #28a745;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Open"]:hover {
                        background-color: #218838;
                    }
                    
                    QToolButton[text="Plot"] {
                        background-color: #007bff;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Plot"]:hover {
                        background-color: #0056b3;
                    }
                    
                    QToolButton[text="Export Figure"],
                    QToolButton[text="Export Data"] {
                        background-color: #17a2b8;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Export Figure"]:hover,
                    QToolButton[text="Export Data"]:hover {
                        background-color: #138496;
                    }
                    
                    QToolButton[text="Settings"] {
                        background-color: #6c757d;
                        color: #ffffff;
                        font-weight: bold;
                    }
                    QToolButton[text="Settings"]:hover {
                        background-color: #545b62;
                    }
                """)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to apply toolbar styling: {e}")

    # --- Responsive UI helpers ---
    def _update_compact_ui(self):
        """Switch toolbar density/icon mode based on window width.
        Keep icons-only when narrow to avoid ugly elided labels."""
        try:
            from PySide6.QtCore import Qt
            w = self.width()
            # Wide: text beside icon; Medium: text under icon; Narrow: icon only
            if w < 900:
                self.tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
            elif w < 1200:
                self.tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            else:
                self.tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        except Exception:
            pass

    def resizeEvent(self, event):
        try:
            self._update_compact_ui()
        except Exception:
            pass
        return super().resizeEvent(event)

    # ===== Analysis handlers =====
    def _on_cc_compute(self, opts: dict):
        try:
            df = getattr(self, '_df', None)
            if df is None: return
            x_raw = df[opts['x']].to_numpy()
            y1 = df[opts['y1']].to_numpy(); y2 = df[opts['y2']].to_numpy()
            # Handle datetime x by converting to POSIX seconds and convert view limits likewise
            def _to_posix_seconds(arr):
                import numpy as _np
                import pandas as _pd
                if _np.issubdtype(arr.dtype, _np.datetime64):
                    return arr.astype('datetime64[ns]').astype('int64') / 1e9
                # object -> try pandas to_datetime
                if arr.dtype == object:
                    a = _pd.to_datetime(arr, errors='coerce').astype('datetime64[ns]').to_numpy()
                    return a.astype('int64') / 1e9
                return arr.astype(float)

            is_dt = np.issubdtype(x_raw.dtype, np.datetime64) or x_raw.dtype == object
            if is_dt:
                x_num = _to_posix_seconds(x_raw)
                import matplotlib.dates as _mdates
                ax = self.tabs.currentWidget().get_axes(); lim0, lim1 = ax.get_xlim()
                v0 = _mdates.num2date(lim0).timestamp(); v1 = _mdates.num2date(lim1).timestamp()
                lo, hi = (min(v0, v1), max(v0, v1))
                m1 = (x_num >= lo) & (x_num <= hi)
                xr = x_num[m1]
            else:
                ax = self.tabs.currentWidget().get_axes(); lim0, lim1 = ax.get_xlim()
                lo, hi = (min(lim0, lim1), max(lim0, lim1))
                m1 = (x_raw >= lo) & (x_raw <= hi)
                xr = x_raw[m1].astype(float)

            y1r = y1[m1]
            y2r = y2[m1]
            res = self.crosscorr.compute_crosscorr(xr, y1r, xr, y2r,
                                                   max_lag=float(opts['max_lag']), step=float(opts['dt']),
                                                   detrend=opts['detrend'], normalize=opts['normalize'])
            self.ccDock.show_result(res)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Cross-corr failed: {e}")

    def _collect_pk_params_from_menu(self) -> dict:
        # fallback gather from dock; if hidden, try default columns
        try:
            return {
                'x': self.pkDock.cbX.currentText(),
                'y': self.pkDock.cbY.currentText(),
                'polarity': self.pkDock.cbPolarity.currentText(),
                'prominence': float(self.pkDock.spinProm.value()),
                'height': float(self.pkDock.spinHeight.value()),
                'min_distance': int(self.pkDock.spinMinDist.value()),
                'min_width': int(self.pkDock.spinMinWidth.value()),
                'smooth_window': int(self.pkDock.spinSmooth.value()),
                'annotate': bool(self.pkDock.chkAnnotate.isChecked()),
            }
        except Exception:
            return {'x':'','y':'','polarity':'peaks','prominence':0.0,'height':0.0,'min_distance':5,'min_width':1,'smooth_window':0,'annotate':True}

    def _on_pk_detect(self, opts: dict):
        try:
            df = getattr(self, '_df', None)
            if df is None: return
            x_raw = df[opts['x']].to_numpy() if opts['x'] in df.columns else np.arange(len(df))
            y = df[opts['y']].to_numpy()
            ax = self.tabs.currentWidget().get_axes(); lim0, lim1 = ax.get_xlim()
            lo, hi = (min(lim0, lim1), max(lim0, lim1))
            # Convert datetime x to Matplotlib date numbers for consistent comparison
            try:
                import numpy as _np, pandas as _pd, matplotlib.dates as _mdates
                if _np.issubdtype(x_raw.dtype, _np.datetime64) or x_raw.dtype == object:
                    x_num = _mdates.date2num(_pd.to_datetime(x_raw, errors='coerce').to_pydatetime())
                else:
                    x_num = _np.asarray(x_raw, float)
            except Exception:
                x_num = np.asarray(x_raw, float)
            m = (x_num >= lo) & (x_num <= hi)
            from peaks import PeakParams
            p = PeakParams(polarity=opts['polarity'], prominence=opts['prominence'], height=opts['height'],
                           min_distance=opts['min_distance'], min_width=opts['min_width'], smooth_window=opts['smooth_window'],
                           annotate=opts.get('annotate', True))
            res = self.peaks.detect(x_num[m], y[m], p)
            self.pkDock.show_results(res)
            if opts.get('annotate', True):
                self.peaks.annotate(x_num[m], y[m], res)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Peak detect failed: {e}")

    def _on_pk_annotate(self, on: bool):
        try:
            if not on: self.peaks.clear(); return
            if self.pkDock.table.rowCount() == 0: return
            # reconstruct results from table
            xs = []; ys = []; idx = []
            for r in range(self.pkDock.table.rowCount()):
                xs.append(float(self.pkDock.table.item(r,0).text()))
                ys.append(float(self.pkDock.table.item(r,1).text()))
                idx.append(int(self.pkDock.table.item(r,2).text()))
            res = {'x_peak': xs, 'y_peak': ys, 'index': idx}
            df = getattr(self, '_df', None)
            xcol = self.pkDock.cbX.currentText()
            ycol = self.pkDock.cbY.currentText()
            x = df[xcol].to_numpy() if xcol in df.columns else np.arange(len(df))
            y = df[ycol].to_numpy()
            self.peaks.annotate(x, y, res)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Annotate failed: {e}")

    def _on_pk_export(self):
        try:
            import pandas as pd
        except Exception:
            pd = None
        try:
            from PySide6.QtWidgets import QFileDialog
            fn, _ = QFileDialog.getSaveFileName(self, "Export Peaks", "peaks.csv", "CSV (*.csv);;Excel (*.xlsx)")
            if not fn: return
            # collect table
            xs = []; ys = []; idx = []
            for r in range(self.pkDock.table.rowCount()):
                xs.append(self.pkDock.table.item(r,0).text())
                ys.append(self.pkDock.table.item(r,1).text())
                idx.append(self.pkDock.table.item(r,2).text())
            if pd is not None and fn.lower().endswith('.xlsx'):
                df = pd.DataFrame({'x_peak': xs, 'y_peak': ys, 'index': idx})
                df.to_excel(fn, index=False)
            else:
                import csv
                with open(fn, 'w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f); w.writerow(['x_peak','y_peak','index']); w.writerows(zip(xs,ys,idx))
            QMessageBox.information(self, "Export", f"Saved: {fn}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Export failed: {e}")
    
    def toggle_error_panel(self, checked: bool):
        """Toggle error panel visibility"""
        if checked:
            self.error_panel.setFloating(True)
            self.error_panel.show()
            self.error_panel.raise_()
            self.error_panel.activateWindow()
        else:
            self.error_panel.hide()
    
    # Action handlers
    def on_action_reload(self):
        """Reload current file"""
        if hasattr(self, 'current_file_path') and self.current_file_path:
            self.open_file(self.current_file_path)
        else:
            QMessageBox.information(self, "Reload", "No file loaded to reload.")
    
    def on_action_plot(self):
        """Plot action handler - opens plot dialog"""
        self.plot_line()
    
    def on_action_spectrogram(self):
        """Spectrogram action handler"""
        self.open_spectrogram_dialog()
    
    def on_action_add_tab(self):
        """Add new tab action handler"""
        self.tabs.add_tab()
    
    def on_action_open_processors(self):
        """Open processors action handler"""
        # Simple FFT dialog for now
        self.run_fft_dialog()
    
    def on_action_export_figure(self):
        """Export figure action handler"""
        self.export_png()
    
    def on_action_export_data(self):
        """Export data action handler"""
        self.export_visible_range_csv()

    # ---------- Plot Style Configuration ----------
    def _get_config_path(self):
        """Get path to configuration file"""
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
                
                # แสดงข้อมูลขนาดไฟล์และจำนวนแถว
                file_size_mb = os.path.getsize(path) / (1024*1024)
                rows_count = len(df)
                self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (ตาราง) • {enc_note} • {rows_count:,} แถว")
                self.statusBar().showMessage(f"โหลดข้อมูลสำเร็จ (ตาราง) • {rows_count:,} แถว • กด 'โหลดคอลัมน์'")
                return
            if ext in [".nc", ".cdf"]:
                try:
                    df = load_cdf_nc_on_demand(self, path)
                    if df is None or df.empty: 
                        raise ValueError("อ่านไฟล์ CDF/NetCDF ไม่สำเร็จ หรือไม่มีข้อมูล")
                    self._df, self._current_path = df, path
                    
                    # แสดงข้อมูลจำนวนแถว
                    rows_count = len(df)
                    self.lblFile.setText(f"ไฟล์: {os.path.basename(path)} (CDF/NetCDF) • {rows_count:,} แถว")
                    self.statusBar().showMessage(f"โหลดข้อมูลสำเร็จ (On‑Demand) • {rows_count:,} แถว • กด 'โหลดคอลัมน์'")
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
        
        # แสดงข้อมูลขนาดข้อมูล
        rows_count = len(self._df)
        cols_count = len(self._df.columns)
        
        cols = [str(c) for c in self._df.columns]
        self.cbX.clear(); self.cbY.clear()
        self.cbX.addItems(cols); self.cbY.addItems(cols)
        
        # UI-REFINE: sync คอลัมน์ของ Histogram ด้วย
        try:
            self.cbHist.clear(); self.cbHist.addItems(cols)
        except Exception:
            pass
        
        self.statusBar().showMessage(f"โหลดคอลัมน์เรียบร้อย • {rows_count:,} แถว, {cols_count} คอลัมน์ • เลือก X/Y แล้วพล็อตได้")
        
        # UI-REFINE: อัปเดตจำนวนแถว
        try: 
            self._sb_rows.setText(f"rows: {rows_count:,}")
        except Exception: 
            pass

    # ---------- Plot ----------
    def _convert_to_datetime_if_possible(self, col_name):
        """ลองแปลงคอลัมน์เป็น datetime ถ้าเป็นไปได้"""
        if col_name not in self._df.columns:
            return False, None
        
        col_data = self._df[col_name]
        
        # ถ้าเป็น datetime อยู่แล้ว
        if pd.api.types.is_datetime64_any_dtype(col_data):
            return True, col_data
        
        # ลองแปลงเป็น datetime
        try:
            datetime_data = pd.to_datetime(col_data, errors="coerce")
            valid_count = datetime_data.notna().sum()
            total_count = len(col_data)
            
            if valid_count > total_count * 0.5:  # ถ้าข้อมูลที่ใช้ได้มากกว่า 50%
                return True, datetime_data
            else:
                return False, None
        except Exception:
            return False, None

    def _check_column_numeric(self, col_name):
        """ตรวจสอบว่าคอลัมน์มีข้อมูลตัวเลขที่ใช้ได้หรือไม่"""
        if col_name not in self._df.columns:
            return False, f"คอลัมน์ '{col_name}' ไม่มีในข้อมูล"
        
        col_data = self._df[col_name]
        
        # ตรวจสอบว่าคอลัมน์ว่างหรือไม่
        if col_data.empty:
            return False, f"คอลัมน์ '{col_name}' ว่าง"
        
        # ตรวจสอบว่าทุกค่าเป็น NaN หรือไม่
        if col_data.isna().all():
            return False, f"คอลัมน์ '{col_name}' มีแต่ค่า NaN"
        
        # ตรวจสอบว่าเป็น datetime หรือไม่
        if pd.api.types.is_datetime64_any_dtype(col_data):
            return True, f"คอลัมน์ '{col_name}' เป็นข้อมูลเวลา (datetime) - ใช้ได้สำหรับแกน X"
        
        # ลองแปลงเป็นตัวเลข
        try:
            numeric_data = pd.to_numeric(col_data, errors="coerce")
            valid_count = numeric_data.notna().sum()
            total_count = len(col_data)
            
            if valid_count == 0:
                # ลองแปลงเป็น datetime
                try:
                    datetime_data = pd.to_datetime(col_data, errors="coerce")
                    datetime_valid_count = datetime_data.notna().sum()
                    if datetime_valid_count > 0:
                        return True, f"คอลัมน์ '{col_name}' เป็นข้อมูลเวลา (datetime) - ใช้ได้สำหรับแกน X"
                except Exception:
                    pass
                
                return False, f"คอลัมน์ '{col_name}' ไม่สามารถแปลงเป็นตัวเลขหรือเวลาได้"
            elif valid_count < total_count * 0.5:  # ถ้าข้อมูลที่ใช้ได้น้อยกว่า 50%
                return False, f"คอลัมน์ '{col_name}' มีข้อมูลตัวเลขเพียง {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)"
            else:
                return True, f"คอลัมน์ '{col_name}' มีข้อมูลตัวเลข {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)"
                
        except Exception as e:
            return False, f"เกิดข้อผิดพลาดในการตรวจสอบคอลัมน์ '{col_name}': {e}"

    def _get_xy(self):
        if self._df is None:
            QMessageBox.warning(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'"); return None, None
        if self.cbX.count() == 0 or self.cbY.count() == 0:
            QMessageBox.information(self, "ยังไม่ได้โหลดคอลัมน์", "กดปุ่ม 'โหลดคอลัมน์จากข้อมูล' ก่อน"); return None, None

        x_col = self.cbX.currentText(); y_col = self.cbY.currentText()
        if x_col not in self._df.columns or y_col not in self._df.columns:
            QMessageBox.warning(self, "คอลัมน์ไม่ถูกต้อง", "โปรดเลือกคอลัมน์ X/Y ใหม่"); return None, None

        # ตรวจสอบข้อมูลก่อนประมวลผล
        x_valid, x_msg = self._check_column_numeric(x_col)
        y_valid, y_msg = self._check_column_numeric(y_col)
        
        if not x_valid and not y_valid:
            QMessageBox.warning(self, "ไม่มีข้อมูลที่ใช้ได้", f"ทั้งสองคอลัมน์มีปัญหา:\n• {x_msg}\n• {y_msg}")
            return None, None
        elif not x_valid:
            QMessageBox.warning(self, "คอลัมน์ X มีปัญหา", x_msg)
            return None, None
        elif not y_valid:
            QMessageBox.warning(self, "คอลัมน์ Y มีปัญหา", y_msg)
            return None, None

        try:
            x = self._df[x_col].values; y = self._df[y_col].values
            
            # แสดงข้อมูลเริ่มต้นสำหรับ debug
            print(f"Debug: X column '{x_col}' - dtype: {self._df[x_col].dtype}, sample: {x[:3] if len(x) > 0 else 'empty'}")
            print(f"Debug: Y column '{y_col}' - dtype: {self._df[y_col].dtype}, sample: {y[:3] if len(y) > 0 else 'empty'}")
            
            # Convert Y to numeric with error handling
            try: 
                y_original_count = len(y)
                y = pd.to_numeric(y, errors="coerce")
                y_nan_count = pd.isna(y).sum()
                print(f"Debug: Y conversion - original: {y_original_count}, NaN after conversion: {y_nan_count}, valid: {y_original_count - y_nan_count}")
            except Exception as e:
                print(f"Y column conversion error: {e}")
                y = pd.to_numeric(y, errors="coerce")  # Try again
            
            # Handle datetime X axis
            if len(x) > 0 and (np.issubdtype(type(x[0]), np.datetime64) or pd.api.types.is_datetime64_any_dtype(self._df[x_col])):
                print("Debug: X is datetime, filtering by Y NaN only")
                mask = ~(pd.isna(y))
                x = x[mask]; y = y[mask]
                print(f"Debug: After datetime filtering - X: {len(x)}, Y: {len(y)}")
            else:
                # Convert X to numeric with error handling
                try: 
                    x_original_count = len(x)
                    x = pd.to_numeric(x, errors="coerce")
                    x_nan_count = pd.isna(x).sum()
                    print(f"Debug: X conversion - original: {x_original_count}, NaN after conversion: {x_nan_count}, valid: {x_original_count - x_nan_count}")
                except Exception as e:
                    print(f"X column conversion error: {e}")
                    x = pd.to_numeric(x, errors="coerce")
                
                # Remove NaN values from both X and Y
                mask = ~(pd.isna(x) | pd.isna(y))
                x = x[mask]; y = y[mask]
                print(f"Debug: After NaN filtering - X: {len(x)}, Y: {len(y)}")
            
            # Validate final data with more detailed error messages
            if len(x) == 0 or len(y) == 0:
                # ให้ข้อมูลที่ละเอียดขึ้น
                x_col_info = f"X column '{x_col}' (dtype: {self._df[x_col].dtype})"
                y_col_info = f"Y column '{y_col}' (dtype: {self._df[y_col].dtype})"
                
                # ตรวจสอบว่าคอลัมน์มีข้อมูลหรือไม่
                x_empty = self._df[x_col].isna().all() if len(self._df[x_col]) > 0 else True
                y_empty = self._df[y_col].isna().all() if len(self._df[y_col]) > 0 else True
                
                if x_empty and y_empty:
                    error_msg = f"ทั้งสองคอลัมน์ไม่มีข้อมูล:\n• {x_col_info}\n• {y_col_info}"
                elif x_empty:
                    error_msg = f"คอลัมน์ X ไม่มีข้อมูล: {x_col_info}"
                elif y_empty:
                    error_msg = f"คอลัมน์ Y ไม่มีข้อมูล: {y_col_info}"
                else:
                    # ตรวจสอบว่าคอลัมน์ไหนเป็นข้อมูลเวลาที่ไม่สามารถแปลงเป็นตัวเลขได้
                    x_is_datetime = pd.api.types.is_datetime64_any_dtype(self._df[x_col])
                    y_is_datetime = pd.api.types.is_datetime64_any_dtype(self._df[y_col])
                    
                    if x_is_datetime and not y_is_datetime:
                        error_msg = f"คอลัมน์ X เป็นข้อมูลเวลา (datetime) ซึ่งใช้ได้สำหรับแกน X:\n• {x_col_info}\n\nคอลัมน์ Y ไม่สามารถแปลงเป็นตัวเลขได้:\n• {y_col_info}\n\nลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงคอลัมน์ Y เป็น Float"
                    elif not x_is_datetime and y_is_datetime:
                        error_msg = f"คอลัมน์ X ไม่สามารถแปลงเป็นตัวเลขได้:\n• {x_col_info}\n\nคอลัมน์ Y เป็นข้อมูลเวลา (datetime):\n• {y_col_info}\n\nลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงคอลัมน์ X เป็น Float หรือใช้คอลัมน์ Y เป็นแกน X"
                    elif x_is_datetime and y_is_datetime:
                        error_msg = f"ทั้งสองคอลัมน์เป็นข้อมูลเวลา (datetime):\n• {x_col_info}\n• {y_col_info}\n\nลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงคอลัมน์หนึ่งเป็น Float"
                    else:
                        error_msg = f"ไม่สามารถแปลงข้อมูลเป็นตัวเลขได้:\n• {x_col_info}\n• {y_col_info}\n\nลองใช้ 'กำหนดชนิดคอลัมน์' เพื่อแปลงข้อมูลก่อน"
                
                QMessageBox.warning(self, "ไม่มีข้อมูลที่ใช้ได้", error_msg)
                return None, None
            
            if len(x) != len(y):
                QMessageBox.warning(self, "ข้อมูลไม่ตรงกัน", f"จำนวนข้อมูล X ({len(x)}) และ Y ({len(y)}) ไม่เท่ากัน")
                return None, None
            
            print(f"Debug: Final data ready for plotting - X: {len(x)}, Y: {len(y)}")
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
        print("Debug: plot_line() called")
        x, y = self._get_xy()
        if x is None: 
            print("Debug: plot_line() - no data to plot")
            return
        
        print(f"Debug: plot_line() - got data: x={len(x)}, y={len(y)}")
        print(f"Debug: plot_line() - x sample: {x[:5] if len(x) > 0 else 'empty'}")
        print(f"Debug: plot_line() - y sample: {y[:5] if len(y) > 0 else 'empty'}")
        
        # Get current tab directly
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, "ไม่มีแท็บ", "ไม่มีแท็บที่เปิดอยู่")
            return
            
        print(f"Debug: plot_line() - current tab: {current_tab_id}")
        selected_tab_ids = [current_tab_id]
            
        try:
            lw = self.spLineWidth.value()
            marker = "o" if self.chkMarker.isChecked() else None
            label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
            
            print(f"Debug: plot_line() - parameters: lw={lw}, marker={marker}, label={label}")
            
            # Plot to selected tabs
            self.tabs.plot_to_tabs(
                selected_tab_ids, x, y, 
                label=label, 
                style="line",
                linewidth=lw, 
                marker=marker
            )
            
            # Set labels after plotting
            for tab_id in selected_tab_ids:
                if tab_id in self.tabs.tabs:
                    tab = self.tabs.tabs[tab_id]
                    ax = tab.get_axes()
                    ax.set_xlabel(self.cbX.currentText())
                    ax.set_ylabel(self.cbY.currentText())
                    print(f"Debug: plot_line() - labels set for tab {tab_id}")
            
            # Apply beautification to each tab
            for tab_id in selected_tab_ids:
                if tab_id in self.tabs.tabs:
                    tab = self.tabs.tabs[tab_id]
                    try:
                        beautify_axes(tab.get_axes(), x_is_datetime=self._is_datetime_column(self.cbX.currentText()))
                        print(f"Debug: plot_line() - beautification applied to tab {tab_id}")
                    except Exception as beautify_error:
                        print(f"Line plot beautify error: {beautify_error}")
                    
                    # Force multiple draw attempts
                    for attempt in range(3):
                        try:
                            tab.draw()
                            print(f"Debug: plot_line() - draw attempt {attempt+1} successful")
                            break
                        except Exception as e:
                            print(f"Debug: plot_line() - draw attempt {attempt+1} failed: {e}")
                            if attempt == 2:  # Last attempt
                                # Try emergency redraw
                                try:
                                    tab.canvas.fig.canvas.draw_idle()
                                    print(f"Debug: plot_line() - emergency draw_idle successful")
                                except Exception as e2:
                                    print(f"Debug: plot_line() - emergency draw_idle failed: {e2}")
            
            self.statusBar().showMessage("พล็อตกราฟเส้นสำเร็จ")
            print("Debug: plot_line() completed successfully")
                
        except Exception as e:
            print(f"Debug: plot_line() failed: {e}")
            QMessageBox.critical(self, "พล็อตกราฟเส้นไม่สำเร็จ", f"สาเหตุ: {e}")
            import traceback
            traceback.print_exc()

    def plot_scatter(self):
        print("Debug: plot_scatter() called")
        x, y = self._get_xy()
        if x is None: 
            print("Debug: plot_scatter() - no data to plot")
            return
        
        print(f"Debug: plot_scatter() - got data: x={len(x)}, y={len(y)}")
        
        # Get current tab directly
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, "ไม่มีแท็บ", "ไม่มีแท็บที่เปิดอยู่")
            return
            
        print(f"Debug: plot_scatter() - current tab: {current_tab_id}")
        selected_tab_ids = [current_tab_id]
            
        try:
            size = self.spLineWidth.value() * 5
            label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
            
            print(f"Debug: plot_scatter() - parameters: size={size}, label={label}")
            
            # Plot to selected tabs
            self.tabs.plot_to_tabs(
                selected_tab_ids, x, y, 
                label=label, 
                style="scatter",
                s=size
            )
            
            # Set labels after plotting
            for tab_id in selected_tab_ids:
                if tab_id in self.tabs.tabs:
                    tab = self.tabs.tabs[tab_id]
                    ax = tab.get_axes()
                    ax.set_xlabel(self.cbX.currentText())
                    ax.set_ylabel(self.cbY.currentText())
                    print(f"Debug: plot_scatter() - labels set for tab {tab_id}")
            
            # Apply beautification to each tab
            for tab_id in selected_tab_ids:
                if tab_id in self.tabs.tabs:
                    tab = self.tabs.tabs[tab_id]
                    try:
                        beautify_axes(tab.get_axes(), x_is_datetime=self._is_datetime_column(self.cbX.currentText()))
                        print(f"Debug: plot_scatter() - beautification applied to tab {tab_id}")
                    except Exception as beautify_error:
                        print(f"Scatter plot beautify error: {beautify_error}")
                    tab.draw()
            
            self.statusBar().showMessage("พล็อตกราฟจุดสำเร็จ")
            print("Debug: plot_scatter() completed successfully")
                
        except Exception as e:
            print(f"Debug: plot_scatter() failed: {e}")
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
        
        # Get current tab directly
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, "ไม่มีแท็บ", "ไม่มีแท็บที่เปิดอยู่")
            return
            
        selected_tab_ids = [current_tab_id]
        
        try:
            # Validate data
            vals = pd.to_numeric(self._df[col], errors="coerce").dropna().values
            if vals.size == 0:
                QMessageBox.information(self, "ไม่มีข้อมูล", "คอลัมน์ที่เลือกไม่มีค่าตัวเลข"); return
            
            bins = int(self.spHistBins.value())
            if bins <= 0:
                bins = 20  # Default fallback
            
            # Clear selected tabs and create histogram
            for tab_id in selected_tab_ids:
                if tab_id in self.tabs.tabs:
                    self.tabs.tabs[tab_id].clear()
            
            # Create histogram on selected tabs
            for tab_id in selected_tab_ids:
                if tab_id in self.tabs.tabs:
                    tab = self.tabs.tabs[tab_id]
                    ax = tab.get_axes()
                    
                    try:
                        n, b, _ = ax.hist(vals, bins=bins, alpha=0.7, color="#6aa0f8", edgecolor="#2d3a5a")
                        # Use English labels to avoid font issues
                        ax.set_xlabel(col)
                        ax.set_ylabel("Count")
                        ax.set_title(f"Histogram of {col} (bins={bins})")
                        
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
                                    ax.plot(xs, pdf_scaled, color="#e36a6a", linewidth=2, label=f"Normal fit mu={mu:.2f}, sigma={sigma:.2f}")
                                    ax.legend(loc="best")
                            except Exception as fit_error:
                                print(f"Gaussian fit error: {fit_error}")  # Debug info

                        # Apply beautification with error handling
                        try:
                            beautify_axes(ax)
                        except Exception as beautify_error:
                            print(f"Beautify error: {beautify_error}")  # Debug info
                        
                        # Draw the canvas
                        tab.draw()
                        
                    except Exception as hist_error:
                        QMessageBox.critical(self, "สร้างฮิสโตแกรมไม่สำเร็จ", f"สาเหตุ: {hist_error}")
                        return
            
            self.statusBar().showMessage("พล็อต Histogram สำเร็จ")
                
        except Exception as e:
            QMessageBox.critical(self, "พล็อตไม่สำเร็จ", f"สาเหตุ: {e}")
            import traceback
            traceback.print_exc()  # Debug info

    # UI-REFINE: วาดกราฟแท่งแบบง่าย
    def plot_bar(self, x, y, *, xlabel: str = "", ylabel: str = "", title: str = ""):
        # Get current tab directly
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, "ไม่มีแท็บ", "ไม่มีแท็บที่เปิดอยู่")
            return
            
        selected_tab_ids = [current_tab_id]
            
        # Plot to selected tabs
        self.tabs.plot_to_tabs(
            selected_tab_ids, x, y, 
            style="bar"
        )
        
        # Set labels and title after plotting
        for tab_id in selected_tab_ids:
            if tab_id in self.tabs.tabs:
                tab = self.tabs.tabs[tab_id]
                ax = tab.get_axes()
                if xlabel:
                    ax.set_xlabel(xlabel)
                if ylabel:
                    ax.set_ylabel(ylabel)
                if title:
                    ax.set_title(title)
        
        # Apply beautification to each tab
        for tab_id in selected_tab_ids:
            if tab_id in self.tabs.tabs:
                tab = self.tabs.tabs[tab_id]
                ax = tab.get_axes()
                
                # Set x-axis labels
                ax.set_xticks(range(len(x)))
                try:
                    ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
                except Exception:
                    pass
                    
                beautify_axes(ax, title=title)
                tab.draw()

    def refresh_plot(self, keep_limits: bool = True) -> None:
        """
        อะแดปเตอร์เรียกวาดกราฟใหม่
        - keep_limits: ถ้า True พยายามรักษา xlim/ylim เดิมไว้
        """
        # เดาว่าคุณมีฟังก์ชันวาดอยู่แล้ว เช่น update_plot()/redraw_plot()
        # ปรับชื่อให้ตรงกับของคุณ
        target = None
        for name in ("update_plot", "redraw_plot", "plot_current", "plot_data"):
            if hasattr(self, name):
                target = getattr(self, name)
                break

        if target is None:
            # fallback แบบเบา ๆ: เคลียร์แกนแล้ววาดใหม่จากข้อมูลล่าสุดถ้ามี
            fig = self.canvas.figure
            ax = fig.axes[0] if fig.axes else fig.add_subplot(111)
            xlim = ax.get_xlim() if keep_limits else None
            ylim = ax.get_ylim() if keep_limits else None
            ax.clear()
            # ถ้ามีเมธอดช่วยดึงข้อมูลปัจจุบัน ให้เรียกที่นี่แทน
            if hasattr(self, "_plot_current"):
                self._plot_current(ax)  # ปรับชื่อให้ตรงโปรเจกต์คุณ
            fig.canvas.draw_idle()
            if keep_limits and xlim and ylim:
                ax.set_xlim(*xlim); ax.set_ylim(*ylim)
            return

        # ถ้ามีเมธอดหลักอยู่แล้วก็เรียกเลย
        target()

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
            # รีเฟรชกราฟหลังจากแปลงชนิดข้อมูล
            self.refresh_plot()
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

    # UI-SPECTROGRAM: ฟีเจอร์ Spectrogram
    def open_spectrogram_dialog(self):
        """เปิด dialog สำหรับ Spectrogram Analysis"""
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดเปิดไฟล์ข้อมูลก่อน")
            return
        
        # เปิด dialog
        dialog = SpectrogramDialog(self._df, self)
        
        # เชื่อมต่อ signals
        dialog.preview_requested.connect(self.on_spectrogram_preview)
        dialog.export_image_requested.connect(self.on_spectrogram_export_image)
        dialog.export_csv_requested.connect(self.on_spectrogram_export_csv)
        dialog.send_to_fft_requested.connect(self.on_spectrogram_send_to_fft)
        dialog.send_to_curvefit_requested.connect(self.on_spectrogram_send_to_curvefit)
        
        # แสดง dialog
        dialog.exec()
    
    def on_spectrogram_preview(self, params):
        """แสดง preview ของ Spectrogram"""
        try:
            # ดึงข้อมูล
            time_col = params["time_col"]
            signal_col = params["signal_col"]
            mode = params["mode"]
            to_db = params["to_db"]
            
            # ตรวจสอบคอลัมน์
            if time_col not in self._df.columns or signal_col not in self._df.columns:
                QMessageBox.warning(self, "ไม่พบคอลัมน์", "โปรดเลือกคอลัมน์ที่ถูกต้อง")
                return
            
            # ตรวจสอบข้อมูลเพิ่มเติม
            time_data = self._df[time_col]
            signal_data = self._df[signal_col]
            
            # ตรวจสอบว่าข้อมูลไม่ว่าง
            if time_data.empty or signal_data.empty:
                QMessageBox.warning(self, "ข้อมูลว่าง", "คอลัมน์ที่เลือกไม่มีข้อมูล")
                return
            
            # ตรวจสอบว่าข้อมูลมีค่าที่ใช้ได้
            valid_time = time_data.notna().sum()
            valid_signal = signal_data.notna().sum()
            
            if valid_time < 10 or valid_signal < 10:
                QMessageBox.warning(self, "ข้อมูลไม่เพียงพอ", 
                                  f"คอลัมน์เวลา: {valid_time} จุด, คอลัมน์สัญญาณ: {valid_signal} จุด\nต้องมีอย่างน้อย 10 จุด")
                return
            
            # ตรวจสอบว่าข้อมูลเวลาเรียงลำดับ
            if pd.api.types.is_datetime64_any_dtype(time_data):
                if not time_data.is_monotonic_increasing:
                    QMessageBox.warning(self, "ข้อมูลเวลาไม่เรียงลำดับ", 
                                      "ข้อมูลเวลาต้องเรียงลำดับจากน้อยไปมาก")
                    return
            
            # คำนวณ spectrogram
            if "STFT" in mode:
                # STFT parameters
                window = params["window"]
                nperseg = params["nperseg"]
                noverlap = params["noverlap"]
                scaling = params["scaling"]
                detrend = params.get("detrend", True)
                contrast_percentiles = params.get("contrast_percentiles", (5, 95))
                max_frequency = params.get("max_frequency", 80)
                
                T, F, S, meta = compute_spectrogram(
                    self._df[time_col], self._df[signal_col],
                    fs=None, window=window, nperseg=nperseg,
                    noverlap=noverlap, scaling=scaling, to_db=to_db,
                    detrend=detrend, contrast_percentiles=contrast_percentiles
                )
            else:
                # CWT parameters
                wavelet = params["wavelet"]
                scales = params["scales"]
                
                T, F, S, meta = compute_cwt(
                    self._df[time_col], self._df[signal_col],
                    wavelet=wavelet, scales=scales, to_db=to_db
                )
            
            # แสดง spectrogram บน axes หลัก
            self.canvas.ax.clear()
            
            # ลบ colorbar เก่าถ้ามี
            if hasattr(self, '_last_cbar') and self._last_cbar is not None:
                try:
                    self._last_cbar.remove()
                except Exception:
                    pass
                self._last_cbar = None
            
            # ใช้ imshow สำหรับ spectrogram
            if meta["is_datetime"]:
                # สำหรับ datetime ใช้ extent ที่เหมาะสม
                time_start = meta["time_range"][0]
                time_end = meta["time_range"][1]
                extent = [0, len(T), F.min(), F.max()]
                
                im = self.canvas.ax.imshow(S, origin='lower', aspect='auto', 
                                         extent=extent, cmap='viridis')
                
                # ตั้งค่าแกนเวลา
                time_ticks = np.linspace(0, len(T), 5)
                time_labels = pd.date_range(start=time_start, end=time_end, periods=5)
                self.canvas.ax.set_xticks(time_ticks)
                self.canvas.ax.set_xticklabels([t.strftime('%H:%M:%S') for t in time_labels])
                
            else:
                # สำหรับข้อมูลตัวเลข
                extent = [T.min(), T.max(), F.min(), F.max()]
                im = self.canvas.ax.imshow(S, origin='lower', aspect='auto', 
                                         extent=extent, cmap='viridis')
            
            # ตั้งค่า contrast limits
            if "vmin" in meta and "vmax" in meta:
                im.set_clim(meta["vmin"], meta["vmax"])
            
            # ตั้งค่าแกนความถี่
            if "max_frequency" in params:
                max_freq = params["max_frequency"]
                self.canvas.ax.set_ylim(0, max_freq)
            
            # เพิ่ม colorbar
            self._last_cbar = self.canvas.fig.colorbar(im, ax=self.canvas.ax)
            power_label = "Power (dB)" if to_db else "Power"
            self._last_cbar.set_label(power_label)
            
            # ตั้งชื่อแกน
            self.canvas.ax.set_xlabel('Time')
            self.canvas.ax.set_ylabel('Frequency (Hz)')
            
            # ตั้งชื่อกราฟ
            method = "STFT" if "STFT" in mode else "CWT"
            title = f"Spectrogram ({method}) - {signal_col}"
            self.canvas.ax.set_title(title)
            
            # จัดรูปแบบกราฟ
            self.canvas.ax.grid(True, alpha=0.3)
            
            # อัปเดตกราฟ
            self.canvas.draw()
            
            # เพิ่ม crosshair callback สำหรับ spectrogram
            if hasattr(self, '_cid_motion') and self._cid_motion is not None:
                try:
                    self.canvas.mpl_disconnect(self._cid_motion)
                except Exception:
                    pass
            
            # เชื่อมต่อ crosshair สำหรับ spectrogram
            self._cid_motion = self.canvas.mpl_connect('motion_notify_event', self._on_spectrogram_mouse_move)
            
            # แสดงสถานะ
            self.statusBar().showMessage(f"Spectrogram preview เสร็จสิ้น: {method}")
            
            # เก็บข้อมูลสำหรับ export
            self._current_spectrogram = {
                'T': T, 'F': F, 'S': S, 'meta': meta, 'params': params
            }
            
        except ImportError as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถใช้งานได้: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการคำนวณ: {str(e)}")
            print(f"Spectrogram error: {e}")
    
    def on_spectrogram_export_image(self, params):
        """Export Spectrogram เป็นรูปภาพ PNG"""
        try:
            if not hasattr(self, '_current_spectrogram'):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return
            
            # เลือกไฟล์สำหรับบันทึก
            filename, _ = QFileDialog.getSaveFileName(
                self, "บันทึก Spectrogram", 
                f"spectrogram_{params['mode'].split()[0].lower()}.png",
                "PNG Files (*.png)"
            )
            
            if filename:
                # บันทึกกราฟปัจจุบัน
                self.canvas.fig.savefig(filename, dpi=150, bbox_inches='tight')
                self.statusBar().showMessage(f"บันทึก Spectrogram เป็น {filename}")
                
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการบันทึก: {str(e)}")
    
    def on_spectrogram_export_csv(self, params):
        """Export Spectrogram เป็นไฟล์ CSV"""
        try:
            if not hasattr(self, '_current_spectrogram'):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return
            
            # เลือกไฟล์สำหรับบันทึก
            filename, _ = QFileDialog.getSaveFileName(
                self, "บันทึก Spectrogram CSV", 
                f"spectrogram_{params['mode'].split()[0].lower()}.csv",
                "CSV Files (*.csv)"
            )
            
            if filename:
                # Export ข้อมูล
                T = self._current_spectrogram['T']
                F = self._current_spectrogram['S']
                S = self._current_spectrogram['S']
                meta = self._current_spectrogram['meta']
                
                export_spectrogram_data(T, F, S, meta, filename)
                self.statusBar().showMessage(f"บันทึก Spectrogram CSV เป็น {filename}")
                
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาดในการบันทึก: {str(e)}")

    def on_spectrogram_send_to_fft(self, params):
        """ส่งข้อมูลจาก Spectrogram ไปยัง FFT"""
        try:
            if not hasattr(self, '_current_spectrogram'):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return
            
            # ดึงข้อมูล spectrogram
            T = self._current_spectrogram['T']
            F = self._current_spectrogram['F']
            S = self._current_spectrogram['S']
            meta = self._current_spectrogram['meta']
            
            # สร้างข้อมูลใหม่สำหรับ FFT โดยใช้ช่วงเวลาที่เลือก
            time_col = params["time_col"]
            signal_col = params["signal_col"]
            
            # ใช้ข้อมูลต้นฉบับจาก DataFrame
            if time_col in self._df.columns and signal_col in self._df.columns:
                # เปิด FFT dialog
                self.run_fft_dialog()
                self.statusBar().showMessage("ส่งข้อมูลไปยัง FFT แล้ว")
            else:
                QMessageBox.warning(self, "ไม่พบคอลัมน์", "ไม่พบคอลัมน์ที่เลือกในข้อมูล")
                
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}")
    
    def on_spectrogram_send_to_curvefit(self, params):
        """ส่งข้อมูลจาก Spectrogram ไปยัง CurveFit"""
        try:
            if not hasattr(self, '_current_spectrogram'):
                QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดทำ Preview ก่อน")
                return
            
            # ดึงข้อมูล spectrogram
            T = self._current_spectrogram['T']
            F = self._current_spectrogram['F']
            S = self._current_spectrogram['S']
            meta = self._current_spectrogram['meta']
            
            # สร้างข้อมูลใหม่สำหรับ CurveFit โดยใช้ช่วงเวลาที่เลือก
            time_col = params["time_col"]
            signal_col = params["signal_col"]
            
            # ใช้ข้อมูลต้นฉบับจาก DataFrame
            if time_col in self._df.columns and signal_col in self._df.columns:
                # เปิด CurveFit dialog
                self._open_fit_dialog()
                self.statusBar().showMessage("ส่งข้อมูลไปยัง CurveFit แล้ว")
            else:
                QMessageBox.warning(self, "ไม่พบคอลัมน์", "ไม่พบคอลัมน์ที่เลือกในข้อมูล")
                
        except Exception as e:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}")

    def _on_spectrogram_mouse_move(self, event):
        """Crosshair callback สำหรับ spectrogram"""
        if not hasattr(self, '_current_spectrogram') or event.inaxes != self.canvas.ax:
            return
        
        try:
            # ดึงข้อมูล spectrogram
            T = self._current_spectrogram['T']
            F = self._current_spectrogram['F']
            S = self._current_spectrogram['S']
            meta = self._current_spectrogram['meta']
            
            # แปลงพิกัดเมาส์เป็นเวลาและความถี่
            x_data, y_data = event.xdata, event.ydata
            
            if x_data is None or y_data is None:
                return
            
            # หาค่าเวลาและความถี่ที่ใกล้ที่สุด
            if meta["is_datetime"]:
                time_idx = int(x_data)
                if 0 <= time_idx < len(T):
                    time_val = T[time_idx]
                    time_str = time_val.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_str = "N/A"
            else:
                time_val = x_data
                time_str = f"{time_val:.3f}"
            
            freq_val = y_data
            freq_str = f"{freq_val:.2f} Hz"
            
            # หาค่า power ที่ตำแหน่งนั้น
            if 0 <= int(x_data) < S.shape[0] and 0 <= int(y_data) < S.shape[1]:
                power_val = S[int(x_data), int(y_data)]
                power_str = f"{power_val:.2f} {'dB' if meta.get('to_db', False) else ''}"
            else:
                power_str = "N/A"
            
            # แสดงข้อมูลใน status bar
            status_text = f"Time: {time_str} | Freq: {freq_str} | Power: {power_str}"
            self.statusBar().showMessage(status_text)
            
        except Exception as e:
            # ถ้าเกิดข้อผิดพลาด ให้แสดงข้อความปกติ
            pass

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

    def toggle_error_panel(self, checked: bool):
        """เปิด/ปิด Error Panel"""
        try:
            if checked:
                # แสดง Error Panel เป็น floating window
                self.error_panel.setFloating(True)
                self.error_panel.show()
                self.error_panel.raise_()
                self.error_panel.activateWindow()
            else:
                self.error_panel.hide()
        except Exception as e:
            logging.getLogger(__name__).error(f"Error toggling error panel: {e}")

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
        # Clear current tab
        current_tab_id = self.tabs.get_current_tab_id()
        if current_tab_id and current_tab_id in self.tabs.tabs:
            self.tabs.tabs[current_tab_id].clear()
            self.statusBar().showMessage("ล้างกราฟแล้ว")
            
    def _reset_view(self):
        """Reset view for current tab"""
        current_tab_id = self.tabs.get_current_tab_id()
        if current_tab_id and current_tab_id in self.tabs.tabs:
            tab = self.tabs.tabs[current_tab_id]
            tab.get_axes().set_xlim(auto=True)
            tab.get_axes().set_ylim(auto=True)
            tab.draw()
            
    def _update_canvas_reference(self):
        """Update canvas reference to point to current tab's canvas"""
        current_tab_id = self.tabs.get_current_tab_id()
        if current_tab_id and current_tab_id in self.tabs.tabs:
            self.canvas = self.tabs.tabs[current_tab_id].canvas
        elif self.tabs.count() > 0:
            # Fallback: get first tab's canvas
            first_tab_widget = self.tabs.widget(0)
            for tab_id, tab in self.tabs.tabs.items():
                if tab == first_tab_widget:
                    self.canvas = tab.canvas
                    break
            
    def _add_new_tab(self):
        """Add a new graph tab"""
        self.tabs.add_tab()
        self.statusBar().showMessage("เพิ่มแท็บใหม่แล้ว")

    def on_export_report(self):
        """Export a comprehensive report to PDF containing data analysis and plots"""
        if self._df is None:
            QMessageBox.warning(self, "ไม่มีข้อมูล", "โปรดเปิดไฟล์ข้อมูลก่อน")
            return
            
        if not hasattr(self.canvas, 'fig') or not self.canvas.fig:
            QMessageBox.warning(self, "ไม่มีกราฟ", "โปรดสร้างกราฟก่อน")
            return
            
        # Show Export Report Dialog
        dialog = ExportReportDialog(self._df, self)
        if dialog.exec() != QDialog.Accepted:
            return
            
        # Get options from dialog
        options = dialog.get_options()
        
        # Validate options
        if not options["include_meta"] and not options["include_stats"] and not options["include_fig"]:
            QMessageBox.warning(self, "ไม่มีการเลือกเนื้อหา", "โปรดเลือกเนื้อหาอย่างน้อยหนึ่งอย่าง")
            return
            
        # Get save path from user
        path, _ = QFileDialog.getSaveFileName(
            self, 
            "บันทึกรายงานเป็น PDF", 
            "sciplotter_report.pdf", 
            "PDF Document (*.pdf)"
        )
        
        if not path:
            return
            
        try:
            # Prepare metadata with more information
            meta = {
                'filename': os.path.basename(self._current_path) if self._current_path else 'Unknown',
                'columns_used': []
            }
            
            # Get columns used for plotting if available
            if hasattr(self, 'cbX') and self.cbX.currentText():
                meta['columns_used'].append(self.cbX.currentText())
            if hasattr(self, 'cbY') and self.cbY.currentText():
                meta['columns_used'].append(self.cbY.currentText())
            
            # Add more metadata if available
            if hasattr(self, '_datasets') and self._current_path:
                for name, data in self._datasets.items():
                    if data.get('path') == self._current_path:
                        meta['dataset_name'] = name
                        break
            
            # Generate report with options
            success = export_report(
                fig=self.canvas.fig,
                df=self._df,
                meta=meta,
                save_path=path,
                options=options
            )
            
            if success:
                self.statusBar().showMessage(f"บันทึกรายงานแล้ว: {path}")
                QMessageBox.information(self, "สำเร็จ", f"บันทึกรายงานแล้ว:\n{path}")
            else:
                QMessageBox.critical(self, "บันทึกไม่สำเร็จ", "เกิดข้อผิดพลาดในการสร้างรายงาน")
                
        except Exception as e:
                            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    def open_units_dialog(self):
        """Open units and calibration dialog"""
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "No Data", "ยังไม่มีข้อมูล")
            return
        
        try:
            dlg = UnitsDialog(self._df, self)
            if dlg.exec():
                mapping = dlg.result  # {col: {dim, from_unit, to_unit, a, b}}
                
                # Apply transformations
                df_new = self._df.copy()
                from core.units import apply_to_dataframe
                
                for col, cfg in mapping.items():
                    if col in df_new.columns:
                        # Get the units
                        from_unit = UNIT_REGISTRY.find_unit(cfg['from_unit'])
                        to_unit = UNIT_REGISTRY.find_unit(cfg['to_unit'])
                        
                        if from_unit and to_unit:
                            # Generate new column name
                            new_col = f"{col} ({cfg['to_unit']})"
                            
                            # Apply transformation
                            df_new = apply_to_dataframe(
                                df_new, column=col,
                                a=cfg["a"], b=cfg["b"],
                                unit_from=from_unit, unit_to=to_unit,
                                new_col=new_col
                            )
                
                # Update dataframe
                self._df = df_new
                
                # Store units mapping in metadata
                if not hasattr(self, 'meta'):
                    self.meta = {}
                self.meta.setdefault("units", {})
                self.meta["units"].update(mapping)
                
                # Refresh display
                self.refresh_plot()
                if hasattr(self, "refresh_stats"):
                    self.refresh_stats()
                
                QMessageBox.information(self, "Done", "แปลงหน่วยและสอบเทียบเรียบร้อย (สร้างคอลัมน์ใหม่)")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"เกิดข้อผิดพลาด: {str(e)}")
    
    def open_derived_column_dialog(self):
        """เปิด dialog สำหรับสร้างคอลัมน์ใหม่จากนิพจน์ทางคณิตศาสตร์"""
        # ตรวจสอบว่ามีข้อมูลหรือไม่
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "ไม่มีข้อมูล", "กรุณาโหลดข้อมูลก่อนสร้างคอลัมน์ใหม่")
            return
        
        try:
            # เปิด DerivedColumnDialog
            dlg = DerivedColumnDialog(self, self._df)
            
            # รอให้ผู้ใช้ป้อนข้อมูลและกด Apply
            if dlg.exec() == QDialog.Accepted:
                # Dialog จะสร้างคอลัมน์ใหม่ใน self._df โดยตรง
                # ดังนั้นเราต้องรีเฟรชการแสดงผลเท่านั้น
                
                # รีเฟรชกราฟ
                self.refresh_plot()
                
                # รีเฟรชสถิติถ้ามี
                if hasattr(self, "refresh_stats"):
                    self.refresh_stats()
                
                # แสดงข้อความสำเร็จ
                QMessageBox.information(
                    self, "สำเร็จ", 
                    "สร้างคอลัมน์ใหม่เรียบร้อยแล้ว\nกราฟจะอัปเดตอัตโนมัติ"
                )
                
        except Exception as e:
            # แสดงข้อผิดพลาดถ้าเกิดปัญหา
            QMessageBox.critical(
                self, "ข้อผิดพลาด", 
                f"ไม่สามารถเปิด dialog สร้างคอลัมน์ใหม่ได้:\n{str(e)}"
            )

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "บันทึกรูปภาพเป็น", "plot.png", "PNG Image (*.png)")
        if not path: return
        try:
            self.canvas.fig.savefig(path, dpi=300, bbox_inches="ight")
            self.statusBar().showMessage(f"บันทึกรูปภาพแล้ว: {path}")
        except Exception as e:
            QMessageBox.critical(self, "บันทึกไม่สำเร็จ", f"สาเหตุ: {e}")

    # CHANGE: helper โหลดไอคอนจากโฟลเดอร์ไอคอน (รองรับ .svg/.png และชื่อไฟล์ไม่ตรงเคส)
    def _icon(self, name: str, fallback_sp: QStyle.StandardPixmap) -> QIcon:
        try:
            base = os.path.dirname(__file__)
            # 1) ตรงตัวก่อน
            candidates = [
                os.path.join(base, "logo", f"{name}.png"),
                os.path.join(base, "assets", "icons", f"{name}.svg"),
                os.path.join(base, "assets", "icons", f"{name}.png"),
            ]
            for p in candidates:
                if os.path.isfile(p):
                    return QIcon(p)

            # 2) ค้นหาแบบ case-insensitive ใน assets/icons (รองรับ .svg/.png/.ico/.jpg)
            try:
                icons_dir = os.path.join(base, "assets", "icons")
                if os.path.isdir(icons_dir):
                    lname = name.lower()
                    for fname in os.listdir(icons_dir):
                        stem, ext = os.path.splitext(fname)
                        if stem.lower() == lname and ext.lower() in (".svg", ".png", ".ico", ".jpg", ".jpeg"):
                            return QIcon(os.path.join(icons_dir, fname))
            except Exception:
                pass
        except Exception:
            pass
        try:
            return self.style().standardIcon(fallback_sp)
        except Exception:
            return QIcon()

    def show_about(self):
        # เกี่ยวกับโปรแกรม (อัปเดตเนื้อหาให้รวมฟีเจอร์ใหม่และธีม)
        text = (
            f"{APP_TITLE}\n\n"
            "เครื่องมือวิเคราะห์/พล็อตข้อมูลวิทยาศาสตร์บนเดสก์ท็อป (PySide6 + Matplotlib)\n"
            "- นำเข้าข้อมูล: CSV/TSV/Excel, NetCDF/CDF (เลือกตัวแปรแบบ On‑Demand)\n"
            "- ประมวลผล: Derived Column, Moving Average, FFT, Spectrogram\n"
            "- Annotation: ข้อความ/ลูกศร/เส้น/สี่เหลี่ยม/วงรี/Callout พร้อม Style Dock\n"
            "- Analysis: Multi‑Cursor Cross‑Correlation, Peak Detection (ตรวจจุดยอดอัตโนมัติ)\n"
            "- Export: PNG/CSV/Excel/รายงาน PDF\n\n"
            "ธีม: Modern Dark (QSS), ฟอนต์รองรับภาษาไทย\n"
            "ที่มาของโค้ด: main/dialogs/loaders/processors/styles/..."
        )
        QMessageBox.information(self, "เกี่ยวกับโปรแกรม", text)

    # DnD
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path): self.load_data(path); break

def main():
    app = QApplication(sys.argv)
    
    # Setup logging system
    setup_logging()
    
    # บังคับทั้งแอปให้ใช้เลขอารบิก, จุดทศนิยมเป็น "." ฯลฯ
    from PySide6.QtCore import QLocale
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    
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
