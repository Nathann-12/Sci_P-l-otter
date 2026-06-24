# -*- coding: utf-8 -*-
# main.py
import os, sys
import numpy as np
import pandas as pd
import logging
import locale
import json
import itertools
import math
from datetime import datetime, date

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
from PySide6.QtCore import Qt, QSize, QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QDockWidget, QMessageBox, QSpinBox, QCheckBox, QDialog,
    QListWidget, QToolBar, QInputDialog, QSplitter, QTabWidget, QSizePolicy,
    QFrame, QGroupBox, QStyle, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QAction, QIcon
from enum import Enum
from typing import Any, Dict, List, Optional

import matplotlib.dates as mdates  # CHANGE: handle datetime axes formatting
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection
import matplotlib.pyplot as plt

from core.plot_data import (
    axis_uses_dates as _axis_uses_dates,
    clamp_date_limits as _clamp_date_limits,
    is_invalid_plot_value as _is_invalid_plot_value,
    prepare_plot_data as _prepare_plot_data,
    reset_numeric_axis as _reset_numeric_axis,
    sanitize_plot_xy as _sanitize_plot_xy,
    to_sequence_for_plot as _to_sequence_for_plot,
)

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


from dialogs import MultiDimSliceDialog, ColumnTypeDialog
from dialogs import AggregateDialog  # UI-REFINE: Aggregate dialog
from dialogs import FitDialog  # UI-FIT: Curve Fit dialog
from dialogs import DerivedColumnDialog  # UI-DERIVED: Derived Column dialog
from dialogs_histogram import HistogramDialog  # NEW: Histogram dialog
from charts_gallery import ChartGalleryMenu
from dialogs_units import UnitsDialog  # UI-UNITS: Units and calibration dialog
from core.units import UNIT_REGISTRY  # UI-UNITS: Unit registry for conversions
from processors import add_time_bangkok, add_magnitude, add_moving_average, apply_column_types, compute_fft
from processors import beautify_axes  # CHANGE: plot beautification
from styles.theme import apply_theme, apply_theme_from_config, apply_mpl_from_config, refresh_matplotlib_canvases  # UI-REFINE: ใช้ธีมอ่านง่าย
from settings import settings_manager
from main_window_data_mixin import MainWindowDataMixin
from main_window_menu_mixin import MainWindowMenuMixin
from main_window_toolbar_mixin import MainWindowToolbarMixin
from main_window_panels_mixin import MainWindowPanelsMixin
from main_window_export_mixin import MainWindowExportMixin
from main_window_fit_mixin import MainWindowFitMixin
from main_window_plot_mixin import MainWindowPlotMixin
from main_window_session_mixin import MainWindowSessionMixin
from main_window_spectrogram_mixin import MainWindowSpectrogramMixin
from main_window_view_mixin import MainWindowViewMixin
from dialogs_settings import SettingsDialog
from report_generator import export_report
from dialogs_report import ExportReportDialog
from dialogs_tabs import SelectTabsDialog
from core.logging_setup import setup_logging
from UI.widgets.error_panel import ErrorPanel
from annotations import AnnotationStyleDock, AnnotationListDialog
from crosscorr import CrossCorrManager, CrossCorrDock
from peaks import PeakDetectorManager, PeakDetectionDock
from three_d_view import ThreeDViewDock
from widgets.plot_tabs import (
    CompactPlotPanel as _PlotTabsCompactPlotPanel,
    GraphTab as _PlotTabsGraphTab,
    PlotCanvas as _PlotTabsPlotCanvas,
    TabManager as _PlotTabsTabManager,
)
from core import session as session_store
# [Equation Plotter]
from dialogs_equation import EquationPlotDialog
from eqplot import plot_equations_on_axes
from eqplot3d import plot_surfaces_on_axes

APP_TITLE = "SciPlotter (Modular + Features)"

APP_ICON_FILENAME = "icon_app.png"
APP_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "icons", APP_ICON_FILENAME)
APP_USER_MODEL_ID = "SciPlotter.SciPlotterApp"

from core.plot_mode import PlotMode  # re-exported here for backward compatibility

class PlotCanvas(_PlotTabsPlotCanvas):
    """Compatibility export for the canonical plot canvas in widgets.plot_tabs."""


class GraphTab(_PlotTabsGraphTab):
    """Compatibility export for the canonical graph tab in widgets.plot_tabs."""


class TabManager(_PlotTabsTabManager):
    """Compatibility export for the canonical tab manager in widgets.plot_tabs."""

    def get_open_tabs(self):
        return super().get_open_tabs()

    def plot_to_tabs(self, tab_ids, x, y, label="", style="line", meta: Optional[Dict[str, Any]] = None, **kwargs):
        return super().plot_to_tabs(tab_ids, x, y, label=label, style=style, meta=meta, **kwargs)


class CompactPlotPanel(_PlotTabsCompactPlotPanel):
    """Compatibility export for the canonical compact plot panel in widgets.plot_tabs."""


class MainWindow(
    MainWindowDataMixin,
    MainWindowPlotMixin,
    MainWindowFitMixin,
    MainWindowExportMixin,
    MainWindowSessionMixin,
    MainWindowSpectrogramMixin,
    MainWindowViewMixin,
    MainWindowMenuMixin,
    MainWindowToolbarMixin,
    MainWindowPanelsMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE); self.resize(1180, 760)
        try:
            app_icon = self._icon('icon_app', QStyle.StandardPixmap.SP_DesktopIcon)
            if not app_icon.isNull():
                self.setWindowIcon(app_icon)
        except Exception:
            pass
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

        # Plotting settings/state (Overlay vs Replace)
        try:
            self.settings = getattr(self, "settings", QSettings("SciPlotter", "SciPlotter"))
            val = self.settings.value("plot/mode", PlotMode.OVERLAY.value)
            self.plot_mode = PlotMode(val) if isinstance(val, str) else PlotMode.OVERLAY
        except Exception:
            self.plot_mode = PlotMode.OVERLAY
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
        try:
            self._update_canvas_reference()
        except Exception:
            # Fallback: try to grab first tab's canvas if method not yet available
            try:
                if self.tabs.count() > 0:
                    first_tab_widget = self.tabs.widget(0)
                    for tid, tab in self.tabs.tabs.items():
                        if tab == first_tab_widget:
                            self.canvas = tab.canvas
                            break
            except Exception:
                pass
        
        # Error Panel (hidden by default)
        self.error_panel = ErrorPanel(self)
        self.error_panel.hide()  # ซ่อนไว้ก่อน

        # ซ้าย = File/Staging
        self._panel_left = QWidget(self)
        self._panel_left.setObjectName("SidePanel")
        self._left_layout = QVBoxLayout(self._panel_left)
        self._left_layout.setContentsMargins(12, 12, 12, 12)
        self._left_layout.setSpacing(10)
        self._build_left_panel()  # UI-REFINE
        # Apply sidepanel styles and classes after building
        try:
            self.apply_sidepanel_style()
        except Exception:
            pass
        # UI-REFINE: sidebar ซ้ายมีความกว้างขั้นต่ำ
        # Ensure side panel is wide enough so Thai labels on buttons don't clip
        self._panel_left.setMinimumWidth(260)
        self.splitter.insertWidget(0, self._panel_left)

        # ขวา = Inspector Tabs (Plot/Processing/Export)
        self._panel_right = QWidget(self)
        self._right_layout = QVBoxLayout(self._panel_right)
        self._right_layout.setContentsMargins(8, 8, 8, 8)  # CHANGE: panel margins
        self._right_layout.setSpacing(8)
        self._build_inspector_tabs()  # UI-REFINE
        # UI-REFINE: inspector ขวามีความกว้างขั้นต่ำ
        self._panel_right.setMinimumWidth(220)
        try:
            # Limit right inspector panel so it doesn't get too wide on large windows
            self._panel_right.setMaximumWidth(420)
        except Exception:
            pass
        self.splitter.addWidget(self._panel_right)

        # UI-REFINE: ขนาดสัดส่วนเริ่มต้น (ซ้าย=200, กลาง=600, ขวา=200)
        self.splitter.setSizes([260, 600, 200])
        self.splitter.setHandleWidth(8)  # CHANGE: wider handle for usability
        # UI-REFINE: กลางต้องขยายเมื่อหน้าต่างกว้างขึ้น
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        # Build toolbar with organized groups first (to create actions)
        try:
            self.build_toolbar()
        except AttributeError:
            # Fallback: create a basic toolbar and actions if method not bound
            try:
                self.tb = QToolBar("Main Toolbar", self)
                self.tb.setIconSize(QSize(24, 24))
                self.addToolBar(self.tb)
                if hasattr(self, '_create_toolbar_actions'):
                    self._create_toolbar_actions()
                if hasattr(self, '_apply_toolbar_styling'):
                    self._apply_toolbar_styling()
            except Exception:
                pass
        
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
        
        # Connect tab change signal to update canvas reference (safe getattr)
        try:
            self.tabs.currentChanged.connect(self._update_canvas_reference)
        except Exception:
            try:
                self.tabs.currentChanged.connect(lambda _: hasattr(self, '_update_canvas_reference') and self._update_canvas_reference())
            except Exception:
                pass
        try:
            self.tabs.currentChanged.connect(lambda _: self._mount_layer_manager())
            if hasattr(self.tabs, 'tabCreated'):
                self.tabs.tabCreated.connect(lambda _: self._mount_layer_manager())
            if hasattr(self.tabs, 'tabRemoved'):
                self.tabs.tabRemoved.connect(lambda _: self._mount_layer_manager())
        except Exception:
            pass

    # UI-REFINE: แยกสร้างแผงซ้าย (Staging) และแท็บ Inspector ขวา
    def _prompt_restore_session(self):
        try:
            if not session_store.session_available():
                return
            reply = QMessageBox.question(
                self,
                "Restore last session",
                "พบเซสชันก่อนหน้าที่บันทึกไว้ ต้องการกู้คืนหรือไม่?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                session_store.load_session(self)
        except Exception:
            logger.warning('Session restore failed', exc_info=True)

    # UI-REFINE: รวมการเชื่อมสัญญาณไว้ที่เดียว เพื่อให้แน่ใจว่าวิดเจ็ตถูกสร้างครบก่อน
    def _connect_signals(self):
        # Plot/Processing/Export (ฝั่งขวา)
        try:
            # Prevent duplicate connections; centralize wiring
            try:
                self._wire_load_button()
            except Exception:
                pass
            
            # Connect plot buttons - use the correct button references from CompactPlotPanel
            print(f"Debug: Checking for plot buttons...")
            print(f"Debug: hasattr(self, 'btn_line'): {hasattr(self, 'btn_line')}")
            if hasattr(self, 'btn_line'):
                print(f"Debug: self.btn_line: {self.btn_line}")
            print(f"Debug: hasattr(self, 'btnLine'): {hasattr(self, 'btnLine')}")
            if hasattr(self, 'btnLine'):
                print(f"Debug: self.btnLine: {self.btnLine}")
                
            if hasattr(self, 'btn_line') and self.btn_line:
                self.btn_line.clicked.connect(self.plot_line)
                print("Debug: Connected btn_line to plot_line")
            elif hasattr(self, 'btnLine') and self.btnLine:
                self.btnLine.clicked.connect(self.plot_line)
                print("Debug: Connected btnLine to plot_line")
            else:
                print("Debug: No line button found to connect")
                
            if hasattr(self, 'btn_scatter') and self.btn_scatter:
                self.btn_scatter.clicked.connect(self.plot_scatter)
                print("Debug: Connected btn_scatter to plot_scatter")
            elif hasattr(self, 'btnScatter') and self.btnScatter:
                self.btnScatter.clicked.connect(self.plot_scatter)
                print("Debug: Connected btnScatter to plot_scatter")
            else:
                print("Debug: No scatter button found to connect")
            
            # Overlay add buttons
            if hasattr(self, 'btnLineAdd'):
                self.btnLineAdd.clicked.connect(self.add_line_overlay)
            if hasattr(self, 'btnScatterAdd'):
                self.btnScatterAdd.clicked.connect(self.add_scatter_overlay)
                
            # Connect fit and clear buttons
            if hasattr(self, 'btn_fit') and self.btn_fit:
                self.btn_fit.clicked.connect(self._open_fit_dialog)
            elif hasattr(self, 'btnCurveFit') and self.btnCurveFit:
                self.btnCurveFit.clicked.connect(self._open_fit_dialog)
                
            if hasattr(self, 'btn_clear') and self.btn_clear:
                self.btn_clear.clicked.connect(self.clear_plot)
            elif hasattr(self, 'btnClear') and self.btnClear:
                self.btnClear.clicked.connect(self.clear_plot)
            # Histogram controls moved to Analysis dialog
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

    def _wire_load_button(self):
        try:
            self.btnLoadCols.clicked.disconnect()
        except Exception:
            pass
        # Assign stable object names and deduplicate if multiple exist
        try:
            self.btnLoadCols.setObjectName("btnLoadColumns")
        except Exception:
            pass
        # (cleanup moved to _build_inspector_tabs after injecting CompactPlotPanel)
        try:
            self.cbX.setObjectName("cboX"); self.cbY.setObjectName("cboY")
        except Exception:
            pass
        try:
            dups = self.findChildren(QPushButton, "btnLoadColumns")
            for i, w in enumerate(dups):
                if i > 0:
                    w.setParent(None); w.deleteLater()
        except Exception:
            pass
        try:
            # Prefer the smarter refresh API if available
            self.btnLoadCols.clicked.connect(self.refresh_xy_columns)
        except Exception:
            # Fallback to legacy method
            self.btnLoadCols.clicked.connect(self.load_columns_from_df)

    # ---------- Central plotting helpers ----------
    def get_main_axes(self, prefer_3d: bool = False):
        """Return a matplotlib Axes for plotting based on current PlotMode.
        - OVERLAY: reuse last axes when possible; create new if 2D/3D differs
        - REPLACE: clear figure and create fresh axes
        """
        try:
            fig = self.canvas.fig
        except Exception:
            try:
                tab = self.tabs.currentWidget()
                fig = tab.get_figure()
            except Exception:
                from matplotlib.figure import Figure as _Figure
                fig = _Figure()

        mode = getattr(self, 'plot_mode', PlotMode.OVERLAY)
        if mode == PlotMode.REPLACE or not fig.axes:
            fig.clear()
            return fig.add_subplot(111, projection='3d' if prefer_3d else None)

        ax = fig.axes[-1]
        is3d = hasattr(ax, 'zaxis')
        if prefer_3d and not is3d:
            return fig.add_subplot(111, projection='3d')
        if not prefer_3d and is3d:
            return fig.add_subplot(111)
        return ax

    def apply_plot(self, drawer, prefer_3d: bool = False):
        tab = None
        canvas = None
        initial_layer_ids = set()
        pre_artist_ids = set()
        try:
            if hasattr(self, '_update_canvas_reference') and hasattr(self, 'tabs'):
                self._update_canvas_reference()
            tab = self.tabs.currentWidget() if hasattr(self, 'tabs') else None
        except Exception:
            tab = None

        mode = getattr(self, 'plot_mode', PlotMode.OVERLAY)

        if tab is not None and hasattr(tab, 'canvas'):
            canvas = tab.canvas
            self.canvas = canvas
            ax = canvas.ax
            is3d = hasattr(ax, 'zaxis')
            if prefer_3d and not is3d:
                canvas.fig.clf()
                ax = canvas.fig.add_subplot(111, projection='3d')
                canvas.ax = ax
            elif not prefer_3d and is3d:
                canvas.fig.clf()
                ax = canvas.fig.add_subplot(111)
                canvas.ax = ax
            else:
                ax = canvas.ax
            try:
                import matplotlib as _mpl
                fig_fc = _mpl.rcParams.get('figure.facecolor', '#1e2126') or '#1e2126'
                ax_fc = _mpl.rcParams.get('axes.facecolor', '#1e2126') or '#1e2126'
                canvas.fig.patch.set_facecolor(fig_fc)
                ax.set_facecolor(ax_fc)
            except Exception:
                pass

            if mode == PlotMode.REPLACE:
                try:
                    ax.clear()
                except Exception:
                    pass
                _clamp_date_limits(ax)
                try:
                    tab.clear_layers()
                except Exception:
                    pass

            initial_layer_ids = set(getattr(tab, 'layers', {}).keys())
            pre_artist_ids = {id(artist) for artist in self._collect_plot_artists(ax)}
        else:
            ax = self.get_main_axes(prefer_3d=prefer_3d)
            tab = None
            pre_artist_ids = {id(artist) for artist in self._collect_plot_artists(ax)}

        drawer(ax)

        try:
            if hasattr(ax, 'relim'):
                ax.relim()
            if hasattr(ax, 'autoscale_view'):
                ax.autoscale_view(True, True, True)
        except Exception:
            pass

        post_layer_ids = set(getattr(tab, 'layers', {}).keys()) if tab is not None else set()
        if tab is not None and post_layer_ids == initial_layer_ids:
            new_artists = [artist for artist in self._collect_plot_artists(ax) if id(artist) not in pre_artist_ids]
            if new_artists:
                used_labels = {info.get('label', '') for info in tab.layers.values() if info.get('label')}
                registered = False
                for artist in new_artists:
                    style = self._infer_artist_style(artist)
                    if style == 'layer':
                        continue
                    try:
                        label = artist.get_label()
                    except Exception:
                        label = ''
                    if not label or str(label).startswith('_'):
                        label = self._generate_auto_layer_label(tab, style, used_labels)
                    else:
                        used_labels.add(label)
                    layer_meta = {'source': 'analysis.apply_plot', 'style': style}
                    layer_id = tab.register_layer([artist], label, style, meta=layer_meta, kwargs={})
                    if layer_id:
                        registered = True
                if registered:
                    try:
                        tab._refresh_legend()
                    except Exception:
                        pass

        try:
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc='best')
        except Exception:
            pass
        try:
            ax.figure.canvas.draw_idle()
        except Exception:
            pass
        if tab is not None:
            try:
                tab.draw()
            except Exception:
                try:
                    tab.canvas.draw()
                except Exception:
                    pass


    def _collect_plot_artists(self, ax):
        """Return new plot artists (lines/collections) for layer registration."""
        artists = []
        try:
            artists.extend(getattr(ax, 'lines', []))
        except Exception:
            pass
        try:
            artists.extend(getattr(ax, 'collections', []))
        except Exception:
            pass
        unique = []
        seen = set()
        for artist in artists:
            if artist is None:
                continue
            art_id = id(artist)
            if art_id in seen:
                continue
            seen.add(art_id)
            unique.append(artist)
        return unique

    @staticmethod
    def _infer_artist_style(artist: object) -> str:
        if isinstance(artist, Line2D):
            return 'line'
        if isinstance(artist, PathCollection):
            return 'scatter'
        return 'layer'

    def _generate_auto_layer_label(self, tab, style: str, used_labels: set) -> str:
        base = 'Series' if style == 'line' else (style.capitalize() if style else 'Series')
        idx = 1
        candidate = f"{base} {idx}"
        while candidate in used_labels:
            idx += 1
            candidate = f"{base} {idx}"
        used_labels.add(candidate)
        return candidate

    def _resolve_active_dataframe(self) -> pd.DataFrame:
        """Return the current DataFrame, falling back to staged datasets."""
        df = getattr(self, '_df', None)
        if isinstance(df, pd.DataFrame):
            return df
        df = getattr(self, 'current_df', None)
        if isinstance(df, pd.DataFrame):
            return df
    def get_current_dataframe(self) -> pd.DataFrame:
        """คืน DataFrame ปัจจุบัน (ถ้าไม่มีให้ผลลัพธ์ว่าง)."""
        df = self._resolve_active_dataframe()
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

        datasets = getattr(self, '_datasets', {}) if hasattr(self, '_datasets') else {}
        lst_widget = getattr(self, 'lstFiles', None)
        current_item = None
        if lst_widget is not None:
            try:
                current_item = lst_widget.currentItem()
            except Exception:
                current_item = None
        if current_item is not None and isinstance(datasets, dict):
            data = datasets.get(current_item.text())
            df_candidate = data.get('df') if isinstance(data, dict) else None
            if isinstance(df_candidate, pd.DataFrame):
                if getattr(self, '_df', None) is None:
                    try:
                        self._df = df_candidate.copy()
                    except Exception:
                        self._df = df_candidate
                try:
                    if isinstance(data, dict) and data.get('path'):
                        self._current_path = data.get('path')
                except Exception:
                    pass
                return df_candidate
        if isinstance(datasets, dict):
            for data in datasets.values():
                if not isinstance(data, dict):
                    continue
                df_candidate = data.get('df')
                if isinstance(df_candidate, pd.DataFrame):
                    if getattr(self, '_df', None) is None:
                        try:
                            self._df = df_candidate.copy()
                        except Exception:
                            self._df = df_candidate
                    try:
                        if data.get('path'):
                            self._current_path = data.get('path')
                    except Exception:
                        pass
                    return df_candidate
        return pd.DataFrame()

    # --- Apply current Matplotlib theme to the active canvas (useful on first launch) ---
    def apply_current_mpl_theme_to_canvas(self):
        try:
            import matplotlib as _mpl
            tab = self.tabs.currentWidget()
            if not tab: return
            fig = tab.get_figure(); ax = tab.get_axes()
            fig_fc = _mpl.rcParams.get("figure.facecolor", "#1e2126") or "#1e2126"
            ax_fc = _mpl.rcParams.get("axes.facecolor", "#1e2126") or "#1e2126"
            grid_col = _mpl.rcParams.get("grid.color", "#3a3f44") or "#3a3f44"
            grid_alpha = float(_mpl.rcParams.get("grid.alpha", 0.3))
            grid_ls = _mpl.rcParams.get("grid.linestyle", "-") or "-"
            text_col = _mpl.rcParams.get("text.color", "#e6e6e6") or "#e6e6e6"

            if fig: fig.patch.set_facecolor(fig_fc)
            if ax:
                ax.set_facecolor(ax_fc)
                for sp in ax.spines.values():
                    sp.set_color(_mpl.rcParams.get("axes.edgecolor", "#3a3f44"))
                ax.tick_params(colors=text_col)
                ax.yaxis.label.set_color(text_col)
                ax.xaxis.label.set_color(text_col)
                if bool(_mpl.rcParams.get("axes.grid", True)):
                    ax.grid(True, alpha=grid_alpha, linestyle=grid_ls, color=grid_col)
            fig.canvas.draw_idle()
        except Exception:
            pass
        
        # Add keyboard shortcuts
        self.actOpen.setShortcut("Ctrl+O")
        self.actSettings.setShortcut("Ctrl+,")
        
        # UI-DERIVED: เพิ่มคีย์ลัดสำหรับ Create Derived Column
        data_menu = getattr(self, "dataMenu", None)
        if data_menu and not hasattr(self, "_actDataDerived"):
            self._actDataDerived = data_menu.addAction("สร้างคอลัมน์ใหม่…")
            self._actDataDerived.setShortcut("Ctrl+D")
            self._actDataDerived.triggered.connect(self.open_derived_column_dialog)

        
        # Load saved plot style preference
        self._load_plot_style_config()
        
        # Load and apply settings from config
        self._load_and_apply_settings()
        QTimer.singleShot(300, self._prompt_restore_session)

    def resizeEvent(self, event):
        try:
            self._update_compact_ui()
        except Exception:
            pass
        return super().resizeEvent(event)

    # --- Cleanup helpers ---
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
            if not on:
                self.peaks.clear()
                return
            table = self.pkDock.table
            rows = table.rowCount()
            if rows == 0:
                return
            header_map = {}
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                if item is None:
                    continue
                header_map[item.text().strip().lower()] = c
            col_x = header_map.get('x_peak', 0)
            col_y = header_map.get('y_peak', 1)
            col_idx = header_map.get('index', 2)
            col_kind = header_map.get('type', header_map.get('kind'))
            xs = []
            ys = []
            idx_vals = []
            kinds = []
            for r in range(rows):
                item_x = table.item(r, col_x)
                item_y = table.item(r, col_y)
                item_idx = table.item(r, col_idx)
                if not item_x or not item_y or not item_idx:
                    continue
                try:
                    x_val = float(item_x.text())
                    y_val = float(item_y.text())
                    idx_val = int(float(item_idx.text()))
                except Exception:
                    continue
                xs.append(x_val)
                ys.append(y_val)
                idx_vals.append(idx_val)
                if col_kind is not None:
                    item_kind = table.item(r, col_kind)
                    txt = item_kind.text().strip().lower() if item_kind else ''
                    if 'trough' in txt:
                        kinds.append('trough')
                    elif 'peak' in txt:
                        kinds.append('peak')
                    else:
                        kinds.append(txt or 'peak')
            if not xs:
                return
            res = {'x_peak': xs, 'y_peak': ys, 'index': idx_vals}
            if col_kind is not None and len(kinds) == len(xs):
                res['kind'] = kinds
            df = getattr(self, '_df', None)
            if df is None or df.empty:
                self.peaks.annotate(np.asarray(xs, float), np.asarray(ys, float), res)
                return
            xcol = self.pkDock.cbX.currentText()
            ycol = self.pkDock.cbY.currentText()
            x_data = df[xcol].to_numpy() if xcol in df.columns else np.arange(len(df))
            y_data = df[ycol].to_numpy() if ycol in df.columns else np.asarray(ys, float)
            self.peaks.annotate(x_data, y_data, res)
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
            if not fn:
                return
            table = self.pkDock.table
            header_map = {}
            for c in range(table.columnCount()):
                item = table.horizontalHeaderItem(c)
                if item is None:
                    continue
                header_map[item.text().strip().lower()] = c
            col_x = header_map.get('x_peak')
            col_y = header_map.get('y_peak')
            col_idx = header_map.get('index')
            col_kind = header_map.get('type', header_map.get('kind'))
            if col_x is None or col_y is None or col_idx is None:
                QMessageBox.warning(self, "Export", "Peak table is missing required columns.")
                return
            def _cell_text(row, col):
                item = table.item(row, col)
                return item.text() if item else ''
            xs = [_cell_text(r, col_x) for r in range(table.rowCount())]
            ys = [_cell_text(r, col_y) for r in range(table.rowCount())]
            idx_vals = [_cell_text(r, col_idx) for r in range(table.rowCount())]
            kinds = [_cell_text(r, col_kind) for r in range(table.rowCount())] if col_kind is not None else []
            data = {'x_peak': xs, 'y_peak': ys, 'index': idx_vals}
            if col_kind is not None:
                data['type'] = kinds
            if pd is not None and fn.lower().endswith('.xlsx'):
                pd.DataFrame(data).to_excel(fn, index=False)
            else:
                import csv
                headers = ['x_peak', 'y_peak', 'index']
                if col_kind is not None:
                    headers.append('type')
                with open(fn, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for row_idx in range(len(xs)):
                        row = [xs[row_idx], ys[row_idx], idx_vals[row_idx]]
                        if col_kind is not None:
                            row.append(kinds[row_idx])
                        writer.writerow(row)
            QMessageBox.information(self, "Export", f"Saved: {fn}")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Export failed: {e}")
    
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

    # Toolbar: histogram plot using compact controls
    def _on_toolbar_plot_histogram(self):
        try:
            # Sync hidden panel controls then reuse existing logic
            if hasattr(self, 'tbCbHist'):
                col = self.tbCbHist.currentText()
                if hasattr(self, 'cbHist'):
                    try: self.cbHist.setCurrentText(col)
                    except Exception: pass
            if hasattr(self, 'tbHistBins') and hasattr(self, 'spHistBins'):
                try: self.spHistBins.setValue(int(self.tbHistBins.value()))
                except Exception: pass
            if hasattr(self, 'tbHistFit') and hasattr(self, 'chkHistFit'):
                try: self.chkHistFit.setChecked(bool(self.tbHistFit.isChecked()))
                except Exception: pass
            # Call existing workflow
            self.plot_histogram()
        except Exception as e:
            print(f"Debug: toolbar histogram failed: {e}")

    # Menu: Plot Histogram (uses toolbar or panel controls)
    def on_histogram_menu(self):
        # Open new non-modal Histogram dialog
        try:
            self.show_histogram_dialog()
        except Exception as e:
            print(f"Debug: open histogram dialog failed: {e}")

    # === Analysis overlay dialogs ===
    def get_current_xy(self):
        """Return (x,y) currently selected in Plot tab, using existing _get_xy logic."""
        try:
            x, y = self._get_xy()
            return x, y
        except Exception:
            return None, None

    def show_histogram_dialog(self):
        dlg = HistogramDialog(parent=self, get_current_data=self.get_current_xy)
        try:
            from PySide6.QtCore import Qt
            dlg.setWindowModality(Qt.NonModal)
        except Exception:
            pass
        dlg.resize(720, 480)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.show()

    def show_spectrogram_dialog(self):
        # Reuse existing spectrogram dialog path
        self.open_spectrogram_dialog()

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
                    matplotlib.rcParams["figure.facecolor"] = "#1e2126"
                    matplotlib.rcParams["axes.facecolor"] = "#1e2126"
                    matplotlib.rcParams["axes.edgecolor"] = "#3a3f44"
                    matplotlib.rcParams["axes.labelcolor"] = "#e6e6e6"
                    matplotlib.rcParams["xtick.color"] = "#cfd3d6"
                    matplotlib.rcParams["ytick.color"] = "#cfd3d6"
                    matplotlib.rcParams["text.color"] = "#e6e6e6"
                    matplotlib.rcParams["grid.color"] = "#3a3f44"
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

    # [Equation Plotter]
    def _ensure_plot_axes_dimension(self, ax, mode: str):
        """Ensure the active axes match the requested dimensionality."""
        if ax is None:
            return None
        canvas = getattr(self, "canvas", None)
        fig = ax.figure
        facecolor = fig.get_facecolor()
        try:
            axes_facecolor = ax.get_facecolor()
        except Exception:
            axes_facecolor = None

        target = "3d_surface" if mode == "3d_surface" else "2d"

        if target == "3d_surface" and not hasattr(ax, "zaxis"):
            fig.clf()
            new_ax = fig.add_subplot(111, projection="3d")
            fig.patch.set_facecolor(facecolor)
            if axes_facecolor is not None:
                try:
                    new_ax.set_facecolor(axes_facecolor)
                except Exception:
                    pass
            if canvas is not None:
                canvas.ax = new_ax
            for attr in ("axes", "ax"):
                if hasattr(self, attr):
                    setattr(self, attr, new_ax)
            return new_ax

        if target == "2d" and hasattr(ax, "zaxis"):
            fig.clf()
            new_ax = fig.add_subplot(111)
            fig.patch.set_facecolor(facecolor)
            if axes_facecolor is not None:
                try:
                    new_ax.set_facecolor(axes_facecolor)
                except Exception:
                    pass
            if canvas is not None:
                canvas.ax = new_ax
            for attr in ("axes", "ax"):
                if hasattr(self, attr):
                    setattr(self, attr, new_ax)
            return new_ax

        return ax

    # [Equation Plotter]
    def on_plot_from_equation(self):
        dlg = EquationPlotDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        vals = dlg.get_values()
        expressions = vals["expressions"]
        if not expressions:
            self._show_status("\u0e01\u0e23\u0e38\u0e13\u0e32\u0e1e\u0e34\u0e21\u0e1e\u0e4c\u0e2a\u0e21\u0e01\u0e32\u0e23\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e19\u0e49\u0e2d\u0e22 1 \u0e1a\u0e23\u0e23\u0e17\u0e31\u0e14", error=True)
            return
        mode = vals.get("mode", "2d")
        try:
            tab = None
            current_tab_id = None
            try:
                if hasattr(self, "tabs") and hasattr(self.tabs, "get_current_tab_id"):
                    current_tab_id = self.tabs.get_current_tab_id()
            except Exception:
                current_tab_id = None
            if current_tab_id and hasattr(self.tabs, "tabs"):
                tab = self.tabs.tabs.get(current_tab_id)
            overlay_flag = bool(vals.get("overlay", True))
            tab_cleared = False
            ax = None
            if tab is not None:
                try:
                    if hasattr(tab, "canvas"):
                        self.canvas = tab.canvas
                    if not overlay_flag:
                        tab.clear()
                        tab_cleared = True
                    ax = tab.get_axes()
                except Exception:
                    ax = None
            if ax is None:
                ax = getattr(self, "axes", None)
            if ax is None:
                ax = getattr(self, "ax", None)
            if ax is None:
                canvas = getattr(self, "canvas", None)
                if canvas is not None:
                    ax = getattr(canvas, "axes", None)
                    if ax is None:
                        ax = getattr(canvas, "ax", None)
                    if ax is None and hasattr(canvas, "fig"):
                        fig_axes = getattr(canvas.fig, "axes", []) or []
                        if fig_axes:
                            ax = fig_axes[0]
            if ax is None:
                self._show_status("\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e41\u0e01\u0e19 Matplotlib", error=True)
                return
            ax = self._ensure_plot_axes_dimension(ax, mode)
            if ax is None:
                self._show_status("\u0e44\u0e21\u0e48\u0e1e\u0e1a\u0e41\u0e01\u0e19 Matplotlib", error=True)
                return

            eq_overlay = overlay_flag
            if tab_cleared:
                eq_overlay = True

            layer_infos = []
            if mode == "3d_surface":
                layer_infos = plot_surfaces_on_axes(
                    ax=ax,
                    expressions=expressions,
                    x_min=vals["x_min"],
                    x_max=vals["x_max"],
                    n_points=vals["n_points"],
                    y_min=vals.get("y_min", -10.0),
                    y_max=vals.get("y_max", 10.0),
                    n_y_points=vals.get("n_y_points", 200),
                    params_str=vals["params"],
                    wireframe=vals["wireframe"],
                    overlay=eq_overlay,
                )
                self._show_status("\u0e27\u0e32\u0e14\u0e1e\u0e37\u0e49\u0e19\u0e1c\u0e34\u0e27 3D \u0e08\u0e32\u0e01\u0e2a\u0e21\u0e01\u0e32\u0e23\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22")
            else:
                layer_infos = plot_equations_on_axes(
                    ax=ax,
                    expressions=expressions,
                    x_min=vals["x_min"],
                    x_max=vals["x_max"],
                    n_points=vals["n_points"],
                    params_str=vals["params"],
                    y_scale=vals["y_scale"],
                    overlay=eq_overlay,
                )
                self._show_status("\u0e27\u0e32\u0e14\u0e01\u0e23\u0e32\u0e1f\u0e08\u0e32\u0e01\u0e2a\u0e21\u0e01\u0e32\u0e23\u0e40\u0e23\u0e35\u0e22\u0e1a\u0e23\u0e49\u0e2d\u0e22")

            if tab is not None:
                for info in layer_infos:
                    artists = info.get('artists') or []
                    if not artists:
                        continue
                    label = info.get('label') or 'Equation'
                    style = info.get('style', 'line')
                    style_kwargs = info.get('style_kwargs', {})
                    meta = self._build_layer_meta(style, label, style_kwargs, source='plot_equation')
                    tab.register_layer(artists, label, style, meta=meta, kwargs=style_kwargs)
                try:
                    tab._refresh_legend()
                except Exception:
                    pass
                _clamp_date_limits(ax)
                try:
                    tab.draw()
                except Exception:
                    pass
                _clamp_date_limits(ax)
                try:
                    self._mount_layer_manager()
                except Exception:
                    pass

            self._update_3d_controls_state(ax, tab)
        except ValueError as exc:
            self._warn_equation_failure(str(exc))
        except Exception as exc:
            self._show_status("\u0e40\u0e01\u0e34\u0e14\u0e02\u0e49\u0e2d\u0e1c\u0e34\u0e14\u0e1e\u0e25\u0e32\u0e14: {}".format(exc), error=True)


    # [Equation Plotter]
    def _warn_equation_failure(self, details: str) -> None:
        clean = (details or "").strip()
        if not clean:
            clean = "unknown error"
        message = "\u0e44\u0e21\u0e48\u0e2a\u0e32\u0e21\u0e32\u0e23\u0e16\u0e1e\u0e25\u0e47\u0e2d\u0e15\u0e2a\u0e21\u0e01\u0e32\u0e23\u0e44\u0e14\u0e49:\n{}".format(clean)
        self._show_status(message, error=True)
        try:
            QMessageBox.warning(self, "Plot from Equation", message)
        except Exception:
            logger.warning("Failed to show equation warning dialog: %s", message, exc_info=True)
            print(message)


    def _update_3d_controls_state(self, ax=None, tab=None) -> None:
        if not hasattr(self, "view3DDock"):
            return
        try:
            current_ax = ax
            current_tab = tab
            if current_ax is None:
                tab_id = None
                try:
                    tab_id = self.tabs.get_current_tab_id() if hasattr(self.tabs, "get_current_tab_id") else None
                except Exception:
                    tab_id = None
                if tab_id and hasattr(self.tabs, "tabs"):
                    current_tab = self.tabs.tabs.get(tab_id)
                if current_tab is not None and hasattr(current_tab, "get_axes"):
                    try:
                        current_ax = current_tab.get_axes()
                    except Exception:
                        current_ax = None
            if current_ax is not None and hasattr(current_ax, "zaxis"):
                canvas = getattr(current_tab, "canvas", None) if current_tab is not None else getattr(self, "canvas", None)
                toolbar = getattr(current_tab, "toolbar", None) if current_tab is not None else None
                self.view3DDock.attach_axes(current_ax, canvas=canvas, toolbar=toolbar)
                try:
                    should_show = self.view3DDock.toggleViewAction().isChecked()
                except Exception:
                    should_show = self.view3DDock.isVisible()
                if not getattr(self, "_3d_dock_has_shown", False) or should_show:
                    self.view3DDock.show()
                    self._3d_dock_has_shown = True
            else:
                self.view3DDock.detach_axes()
                self.view3DDock.hide()
        except Exception:
            logger.debug("Failed to update 3D dock state", exc_info=True)


    def _show_status(self, msg: str, error: bool = False) -> None:
        try:
            bar = self.statusBar()
        except Exception:
            bar = None
        if bar is not None:
            try:
                bar.showMessage(msg, 5000)
                return
            except Exception:
                pass
        print(msg)
        if error:
            logging.getLogger(__name__).debug("Status error: %s", msg)

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
            try:
                mode = getattr(self, 'plot_mode', PlotMode.OVERLAY)
            except Exception:
                mode = PlotMode.OVERLAY
            if mode == PlotMode.REPLACE:
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
        try:
            if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                self.canvas.clear()
        except Exception:
            pass
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

            try:
                if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                    self.canvas.clear()
            except Exception:
                pass
            self.canvas.ax.plot(df_fft["freq_Hz"].values, df_fft["amplitude"].values, linewidth=2)
            self.canvas.ax.set_xlabel("Frequency (Hz)")
            self.canvas.ax.set_ylabel("Amplitude")
            beautify_axes(self.canvas.ax, title=f"FFT of {y_col} (fs≈{fs:.3f} Hz, window={window}, detrend={detrend})")
            self.statusBar().showMessage("คำนวณ FFT เสร็จแล้ว • ใช้ Export FFT เพื่อบันทึกผลได้")

        except Exception as e:
            QMessageBox.critical(self, "FFT ไม่สำเร็จ", f"สาเหตุ: {e}")

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
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            logger.debug('Failed to set AppUserModelID', exc_info=True)

    app = QApplication(sys.argv)
    try:
        if os.path.isfile(APP_ICON_PATH):
            app_icon = QIcon(APP_ICON_PATH)
            app.setWindowIcon(app_icon)
    except Exception:
        logger.debug('Failed to set application icon', exc_info=True)

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
    # Ensure the very first canvas adopts current Matplotlib theme
    try:
        win.apply_current_mpl_theme_to_canvas()
    except Exception:
        pass
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()







