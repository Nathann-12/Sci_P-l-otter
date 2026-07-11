# -*- coding: utf-8 -*-
# main.py
import os, sys
import logging
import locale

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
logger.debug("Matplotlib backend set to: %s", matplotlib.get_backend())

from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox, QToolBar, QSplitter, QSizePolicy, QFrame, QStyle, QStackedWidget, QTabWidget, QScrollArea
from PySide6.QtGui import QIcon
from typing import Any, Dict, Optional

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


from styles.theme import (
    apply_theme,
    apply_theme_from_config,
    apply_mpl_from_config,
    build_theme_palette,
    icon_theme_colors,
    themed_icon,
)
from settings import settings_manager
from core.plot_request import PlotOptions
from main_window_data_mixin import MainWindowDataMixin
from main_window_menu_mixin import MainWindowMenuMixin
from main_window_toolbar_mixin import MainWindowToolbarMixin
from main_window_panels_mixin import MainWindowPanelsMixin
from main_window_export_mixin import MainWindowExportMixin
from main_window_fit_mixin import MainWindowFitMixin
from main_window_plot_mixin import MainWindowPlotMixin
from main_window_plotcore_mixin import MainWindowPlotCoreMixin
from main_window_session_mixin import MainWindowSessionMixin
from main_window_spectrogram_mixin import MainWindowSpectrogramMixin
from main_window_view_mixin import MainWindowViewMixin
from main_window_analysis_mixin import MainWindowAnalysisMixin
from main_window_equation_mixin import MainWindowEquationMixin
from main_window_settings_mixin import MainWindowSettingsMixin
from main_window_features_mixin import MainWindowFeaturesMixin
from main_window_actions_mixin import MainWindowActionsMixin
from main_window_ai_mixin import MainWindowAIMixin
from main_window_modules_mixin import MainWindowModulesMixin
from main_window_gassensor_mixin import MainWindowGasSensorMixin
from main_window_electrochemistry_mixin import MainWindowElectrochemistryMixin
from main_window_spectroscopy_mixin import MainWindowSpectroscopyMixin
from main_window_materials_mixin import MainWindowMaterialsMixin
from main_window_physics_mixin import MainWindowPhysicsMixin
from main_window_workflow_mixin import MainWindowWorkflowMixin
from main_window_plotstyle_mixin import MainWindowPlotStyleMixin
from main_window_plotextra_mixin import MainWindowPlotExtraMixin
from main_window_gallery_mixin import MainWindowGalleryMixin
from main_window_view_access_mixin import MainWindowViewAccessMixin
from widgets.command_palette import CommandPalette
from UI.shell.app_shell import AppShell
from UI.welcome import WelcomeWidget
from widgets.workbook import WorkbookWidget
from UI.mdi_workspace import MdiWorkspace
from UI.project_explorer import ProjectExplorer
from UI.docks.ai_dock import AiAssistantDock
from UI.docks.log_dock import OperationLogDock
from core.logging_setup import setup_logging
from UI.widgets.error_panel import ErrorPanel
from widgets.plot_tabs import (
    CompactPlotPanel as _PlotTabsCompactPlotPanel,
    GraphTab as _PlotTabsGraphTab,
    PlotCanvas as _PlotTabsPlotCanvas,
    TabManager as _PlotTabsTabManager,
)
from core import session as session_store
# [Equation Plotter]

APP_TITLE = "SciPlotter (Modular + Features)"

APP_ICON_FILENAME = "icon_app.png"
APP_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "icons", APP_ICON_FILENAME)
APP_USER_MODEL_ID = "SciPlotter.SciPlotterApp"

# Map the app's icon names to thin line-style vector icons (qtawesome /
# Material Design Icons), OriginPro-like. _icon() prefers these when
# qtawesome is available, else falls back to files. Kept light + outline so a
# dense toolbar stays airy rather than heavy.
_QTA_ICON_MAP = {
    "open": "mdi.folder-open-outline",
    "batch_import": "mdi.folder-multiple-outline",
    "open_project": "mdi.folder-outline",
    "save_project": "mdi.content-save-outline",
    "inspector": "mdi.view-column-outline",
    "Plot_from_Equation": "mdi.function-variant",
    "plot": "mdi.chart-line",
    "spectrogram": "mdi.chart-areaspline",
    "fft": "mdi.sine-wave",
    "psd": "mdi.chart-bell-curve-cumulative",
    "addtab": "mdi.table-plus",
    "processors": "mdi.tune-variant",
    "settings": "mdi.application-cog-outline",
    "export": "mdi.export-variant",
    "export_figure": "mdi.image-export",
    "export_data": "mdi.database-export-outline",
    "batch_export": "mdi.export",
    "copy_graph": "mdi.content-copy",
    "error_panel": "mdi.alert-circle-outline",
    "clear": "mdi.eraser",
    "fit": "mdi.chart-bell-curve",
    "crosshair": "mdi.crosshairs",
    "boxzoom": "mdi.magnify-scan",
    "gas": "mdi.weather-windy",
    "electrochemistry": "mdi.flash-outline",
    "spectroscopy": "mdi.waveform",
    "materials": "mdi.atom",
    "physics_lab": "mdi.flask-outline",
    "modules": "mdi.view-dashboard-outline",
    "format": "mdi.brush-outline",
    "gallery": "mdi.view-gallery-outline",
    "use_active_book": "mdi.database-check-outline",
    "reload_columns": "mdi.table-refresh",
    "add_row": "mdi.table-row-plus-after",
    "add_column": "mdi.table-column-plus-after",
    "derived_column": "mdi.table-edit",
    "column_types": "mdi.table-cog",
    "units_calibration": "mdi.ruler-square",
    "error_bars": "mdi.chart-timeline-variant",
    "fill_band": "mdi.chart-areaspline",
    "secondary_y": "mdi.axis-y-arrow",
    "broken_axis": "mdi.axis-arrow-lock",
    "window_cascade": "mdi.dock-window",
    "window_tile": "mdi.view-grid-outline",
    "reset_view": "mdi.restore",
    "zoom_in": "mdi.magnify-plus-outline",
    "zoom_out": "mdi.magnify-minus-outline",
    "annotate": "mdi.comment-text-outline",
    "annotate_manage": "mdi.comment-multiple-outline",
    "plot_line": "mdi.chart-line",
    "plot_scatter": "mdi.scatter-plot-outline",
    "plot_linesymbol": "mdi.chart-line-variant",
    "plot_bar": "mdi.chart-bar",
    "plot_histogram": "mdi.chart-histogram",
    "moving_average": "mdi.chart-line-variant",
    "magnitude": "mdi.vector-triangle",
    "bangkok_time": "mdi.clock-time-seven-outline",
    "aggregate": "mdi.sigma",
    "dataset_duplicate": "mdi.book-multiple-outline",
    "dataset_rename": "mdi.book-edit-outline",
    "dataset_group": "mdi.table-group",
    "dataset_merge": "mdi.table-merge-cells",
    "dataset_split": "mdi.table-split-cell",
    "dataset_filter": "mdi.table-filter",
    "dataset_search": "mdi.table-search",
    "fill_missing": "mdi.format-color-fill",
    "interpolate_missing": "mdi.vector-line",
    "remove_missing_rows": "mdi.table-row-remove",
    "remove_duplicates": "mdi.content-duplicate",
    "remove_outliers": "mdi.filter-remove-outline",
    "crop_range": "mdi.crop-free",
    "normalize": "mdi.scale-balance",
    "detrend": "mdi.trending-down",
    "sort": "mdi.sort",
    "resample": "mdi.timeline-clock-outline",
    "time_merge": "mdi.timeline-check-outline",
    "butterworth": "mdi.filter-variant",
    "smooth": "mdi.waves",
    "window_func": "mdi.window-closed-variant",
    "hilbert": "mdi.waveform",
    "envelope": "mdi.chart-bell-curve",
    "instant_freq": "mdi.speedometer",
    "autocorr": "mdi.vector-link",
    "convolution": "mdi.set-merge",
    "deconvolution": "mdi.set-split",
    "decimation": "mdi.arrow-collapse-horizontal",
    "harmonic": "mdi.music-accidental-sharp",
    "ifft": "mdi.sine-wave",
    "stft": "mdi.chart-gantt",
    "zero_pad": "mdi.numeric-0-box-multiple-outline",
    "stats": "mdi.chart-box-outline",
    "covariance": "mdi.grid",
    "peak_metrics": "mdi.chart-line-stacked",
    "signal_quality": "mdi.signal-cellular-3",
    "cc_window": "mdi.select-compare",
    "cc_compute": "mdi.compare-horizontal",
    "cc_clear": "mdi.close-circle-outline",
    "peak_settings": "mdi.tune-vertical",
    "peak_detect": "mdi.chart-areaspline-variant",
    "peak_export": "mdi.table-arrow-right",
    "peak_clear": "mdi.delete-sweep-outline",
    "ann_enable": "mdi.cursor-default-click-outline",
    "ann_text": "mdi.format-text",
    "ann_arrow": "mdi.arrow-top-right",
    "ann_line": "mdi.vector-line",
    "ann_rect": "mdi.rectangle-outline",
    "ann_ellipse": "mdi.ellipse-outline",
    "ann_callout": "mdi.comment-text-outline",
    "ann_manage": "mdi.shape-outline",
    "undo": "mdi.undo",
    "redo": "mdi.redo",
    "gas_response": "mdi.weather-windy",
    "gas_cycles": "mdi.sync-circle",
    "gas_calibration": "mdi.chart-scatter-plot",
    "gas_dilution": "mdi.beaker-outline",
    "workflow_history": "mdi.history",
    "workflow_export": "mdi.file-export-outline",
    "workflow_import": "mdi.file-import-outline",
    "workflow_script": "mdi.script-text-outline",
    "workflow_report": "mdi.file-chart-outline",
    "workflow_snapshot": "mdi.camera-outline",
    "workflow_compare": "mdi.compare",
    "workflow_audit": "mdi.clipboard-list-outline",
    "workflow_clear": "mdi.history-remove",
}

# Thin light icon tint (OriginPro-like); one place so every icon matches.
ICON_COLOR = "#b8bec6"

_QTA_MODULE = None
_QTA_IMPORT_FAILED = False
_ICON_CACHE: Dict[tuple[str, object], QIcon] = {}
_ICON_PATH_CACHE: Dict[str, Optional[str]] = {}


def _current_icon_theme_palette():
    app = QApplication.instance()
    if app is None:
        return build_theme_palette("dark", "#4F9CF9")
    mode = str(app.property("sciplotterThemeMode") or "dark")
    accent = str(app.property("sciplotterAccentColor") or "#4F9CF9")
    background = str(app.property("sciplotterBackgroundColor") or "")
    return build_theme_palette(mode, accent, background)


def _current_icon_theme_colors() -> dict[str, str]:
    return icon_theme_colors(_current_icon_theme_palette())


def _fallback_icon_key(fallback_sp: QStyle.StandardPixmap) -> object:
    try:
        return fallback_sp.value
    except Exception:
        try:
            return int(fallback_sp)
        except Exception:
            return repr(fallback_sp)


def _qtawesome_module():
    global _QTA_MODULE, _QTA_IMPORT_FAILED
    if _QTA_IMPORT_FAILED:
        return None
    if _QTA_MODULE is None:
        try:
            import qtawesome as qta
        except Exception:
            _QTA_IMPORT_FAILED = True
            return None
        _QTA_MODULE = qta
    return _QTA_MODULE


def _qtawesome_icon(qta_id: str) -> Optional[QIcon]:
    colors = _current_icon_theme_colors()
    signature = tuple(colors[key] for key in ("normal", "disabled", "active", "selected"))
    cache_key = ("qta", qta_id, signature)
    cached = _ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    qta = _qtawesome_module()
    if qta is None:
        return None
    try:
        source_icon = qta.icon(
            qta_id,
            color=colors["normal"],
            color_disabled=colors["disabled"],
            color_active=colors["active"],
            color_selected=colors["selected"],
        )
        icon = themed_icon(source_icon, _current_icon_theme_palette())
    except Exception:
        return None
    _ICON_CACHE[cache_key] = icon
    return icon


def _resolve_icon_path(name: str) -> Optional[str]:
    if name in _ICON_PATH_CACHE:
        return _ICON_PATH_CACHE[name]
    base = os.path.dirname(__file__)
    candidates = [
        os.path.join(base, "logo", f"{name}.png"),
        os.path.join(base, "assets", "icons", f"{name}.svg"),
        os.path.join(base, "assets", "icons", f"{name}.png"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            _ICON_PATH_CACHE[name] = path
            return path
    try:
        icons_dir = os.path.join(base, "assets", "icons")
        if os.path.isdir(icons_dir):
            lname = name.lower()
            for fname in os.listdir(icons_dir):
                stem, ext = os.path.splitext(fname)
                if stem.lower() == lname and ext.lower() in (".svg", ".png", ".ico", ".jpg", ".jpeg"):
                    path = os.path.join(icons_dir, fname)
                    _ICON_PATH_CACHE[name] = path
                    return path
    except Exception:
        pass
    _ICON_PATH_CACHE[name] = None
    return None

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
    MainWindowPlotCoreMixin,
    MainWindowFitMixin,
    MainWindowExportMixin,
    MainWindowSessionMixin,
    MainWindowSpectrogramMixin,
    MainWindowViewMixin,
    MainWindowMenuMixin,
    MainWindowToolbarMixin,
    MainWindowPanelsMixin,
    MainWindowAnalysisMixin,
    MainWindowEquationMixin,
    MainWindowSettingsMixin,
    MainWindowFeaturesMixin,
    MainWindowActionsMixin,
    MainWindowAIMixin,
    MainWindowModulesMixin,
    MainWindowGasSensorMixin,
    MainWindowElectrochemistryMixin,
    MainWindowSpectroscopyMixin,
    MainWindowMaterialsMixin,
    MainWindowPhysicsMixin,
    MainWindowWorkflowMixin,
    MainWindowPlotStyleMixin,
    MainWindowPlotExtraMixin,
    MainWindowGalleryMixin,
    MainWindowViewAccessMixin,
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
        self._plot_options = PlotOptions()

        # Plotting settings/state (Overlay vs Replace)
        try:
            self.settings = getattr(self, "settings", QSettings("SciPlotter", "SciPlotter"))
            val = self.settings.value("plot/mode", PlotMode.OVERLAY.value)
            self.plot_mode = PlotMode(val) if isinstance(val, str) else PlotMode.OVERLAY
        except Exception:
            self.plot_mode = PlotMode.OVERLAY

        # === Research OS shell: activity rail | context | workspace | inspector + bottom docks ===
        self.shell = AppShell(self)
        self.setCentralWidget(self.shell)

        # กลาง = MDI workspace แบบ Origin (Book/Graph เป็นหน้าต่างลูกลอยได้)
        # MdiWorkspace เลียนแบบ API ของ TabManager → โค้ดพล็อตเดิม reuse ได้ทั้งหมด
        self.workbook = WorkbookWidget(self)
        self.workbook.dataset_name = "Book1"
        self.mdi = MdiWorkspace(self, start_with_graph=False)
        self.mdi.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabs = self.mdi
        # Startup ต้อง clean แบบ sheet-first: ยังไม่สร้าง Graph จนกว่าผู้ใช้สั่ง plot
        self._book_sub = self.mdi.add_book(self.workbook, "Book1")   # worksheet แบบ Origin
        # Origin multi-book: คลิกหน้าต่าง Book ไหน = ใช้ข้อมูลชุดนั้น
        self.mdi.bookActivated.connect(self._on_book_activated)
        try:
            self.mdi.mdi.setActiveSubWindow(self._book_sub)          # โชว์ Book1 หน้าสุดตอนเปิด
        except Exception:
            logger.debug("activate Book1 skipped", exc_info=True)
        self.shell.set_workspace(self.mdi)

        # Parked side panels: Project Explorer + logs/assistant live beside the
        # workspace as vertical tabs, keeping the bottom graph area clear.
        try:
            self.project_explorer = ProjectExplorer(self, workspace=self.mdi)
            self.project_explorer.setMinimumWidth(130)
            self.shell.add_side_panel("Project Explorer (1)", self.project_explorer)
        except Exception:
            logger.debug("Project Explorer side panel init skipped", exc_info=True)

        # Keep reference to current canvas for backward compatibility
        self.canvas = None
        try:
            self._update_canvas_reference()
        except Exception:
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
        self.error_panel.hide()

        # Origin-pure shell: ไม่มีแผงซ้ายแล้ว — ทุกอย่างทำผ่าน Worksheet +
        # แถบไอคอนพล็อต + Project Explorer + เมนู. แผงนี้ยังถูก "สร้าง" ไว้แบบ
        # ซ่อนเพื่อเป็น compatibility holder ของ column selection และ actions
        # ที่ mixin เก่ายังใช้; plot styling/export state แยกเป็น immutable models แล้ว
        self._panel_left = QWidget(self)
        self._panel_left.setObjectName("SidePanel")
        self._left_layout = QVBoxLayout(self._panel_left)
        self._build_left_panel()
        self._panel_left.hide()

        # ขวา = Inspector Tabs (Plot/Processing/Export)
        self._panel_right = QWidget(self)
        self._right_layout = QVBoxLayout(self._panel_right)
        self._right_layout.setContentsMargins(8, 8, 8, 8)
        self._right_layout.setSpacing(8)
        self._build_inspector_tabs()
        self._panel_right.setMinimumWidth(220)
        try:
            self._panel_right.setMaximumWidth(420)
        except Exception:
            pass
        self.shell.set_inspector(self._panel_right)

        # Parked side panels: AI assistant + operation log. These used to live
        # in the bottom dock, but side tabs preserve vertical graph space.
        try:
            self.ai_dock = AiAssistantDock(self)
            self.op_log_dock = OperationLogDock(self)
            self.shell.add_side_panel("Messages Log", self.op_log_dock)
            self.shell.add_side_panel("Smart Hint Log", self.ai_dock)
        except Exception:
            pass

        # Build toolbar with organized groups first (to create actions)
        try:
            self.build_toolbar()
        except AttributeError:
            # Fallback: create a basic toolbar and actions if method not bound
            try:
                self.tb = QToolBar("Main Toolbar", self)
                self.tb.setIconSize(QSize(16, 16))
                self.addToolBar(self.tb)
                if hasattr(self, '_create_toolbar_actions'):
                    self._create_toolbar_actions()
                if hasattr(self, '_apply_toolbar_styling'):
                    self._apply_toolbar_styling()
            except Exception:
                pass
        
        self._init_menu()
        # Origin-style left / right / bottom tool docks (after the menu so the
        # annotation/window actions they surface already exist)
        try:
            self.build_side_toolbars()
        except Exception:
            logging.getLogger(__name__).debug("side toolbars skipped", exc_info=True)
        self._connect_signals()  # UI-REFINE: เชื่อมสัญญาณหลังจากวิดเจ็ตถูกสร้างครบ

        # Local AI assistant: wire the parked AI dock to the tool-using agent.
        try:
            self.init_ai_assistant()
        except Exception:
            logging.getLogger(__name__).debug("AI assistant wiring skipped", exc_info=True)

        # โมดูลเฉพาะทางตัวแรก: Gas Sensor ลงทะเบียนไว้ แต่ไม่เปิด rail/context
        # เองตอน startup เพื่อให้หน้าจอเริ่มต้นเหลือ worksheet/workspace คลีน ๆ
        try:
            self.init_gas_sensor_module()
        except Exception:
            logger.debug("gas sensor module init skipped", exc_info=True)

        try:
            self.init_electrochemistry_module()
        except Exception:
            logger.debug("electrochemistry module init skipped", exc_info=True)

        try:
            self.init_spectroscopy_module()
        except Exception:
            logger.debug("spectroscopy module init skipped", exc_info=True)

        try:
            self.init_materials_module()
        except Exception:
            logger.debug("materials module init skipped", exc_info=True)

        try:
            self.init_physics_module()
        except Exception:
            logger.debug("physics module init skipped", exc_info=True)

        # Reproducibility: ประวัติการวิเคราะห์ + workflow (เมนู Tools)
        try:
            self.init_workflow_module()
        except Exception:
            logger.debug("workflow module init skipped", exc_info=True)

        # Command palette (Ctrl+K) - searchable list of all menu/toolbar actions
        try:
            from PySide6.QtGui import QAction, QShortcut, QKeySequence
            self._command_palette = CommandPalette(self)
            _cmds = []
            for _act in self.findChildren(QAction):
                _txt = _act.text().replace("&", "").strip()
                if _txt:
                    _cmds.append((_txt, _act.trigger))
            self._command_palette.set_commands(_cmds)
            self.shell.set_command_palette(self._command_palette)
            _sc = QShortcut(QKeySequence("Ctrl+K"), self)
            _sc.activated.connect(self.shell.open_command_palette)
        except Exception:
            pass
        
        # Persistent StatusBar state.
        self._sb_rows = QLabel("rows: -")
        self._sb_fs = QLabel("fs: -")
        self._sb_cursor = QLabel("x=-, y=-")
        self.statusBar().addPermanentWidget(self._sb_rows)
        self.statusBar().addPermanentWidget(self._sb_fs)
        self.statusBar().addPermanentWidget(self._sb_cursor)
        self.statusBar().showMessage(
            "Start: open data or type into Book1, use the worksheet data, choose X/Y, then plot.")
        self.setAcceptDrops(True)

        # UI-REFINE: ซ่อน Inspector ตอนเริ่ม และ sync ปุ่ม (ผ่าน toggle_inspector
        # เพื่อให้คอลัมน์ inspector ใน shell ยุบไปด้วย ไม่เหลือแถบว่างขวา)
        self.toggle_inspector(False)
        try: self.actToggleInspector.setChecked(False)
        except Exception: pass

        try:
            self._apply_english_ui_texts()
            self._install_english_ui_filter()
        except Exception:
            logger.debug("English UI normalization skipped", exc_info=True)
        
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

        # Origin: double-click a graph opens Plot Details. Bind the current
        # graph now and rebind whenever a graph is created/activated.
        try:
            self.bind_graph_dblclick()
            self.tabs.currentChanged.connect(self.bind_graph_dblclick)
            if hasattr(self.tabs, 'tabCreated'):
                self.tabs.tabCreated.connect(self.bind_graph_dblclick)
        except Exception:
            logger.debug("graph dblclick wiring skipped", exc_info=True)

        # Origin-style worksheet: fill it when data is loaded, and jump to the
        # graph tab when the user actually plots. Hooks ride existing signals /
        # aliased buttons — no logic in the mixins is touched.
        try:
            if hasattr(self, 'btnLoadCols') and self.btnLoadCols is not None:
                self.btnLoadCols.clicked.connect(lambda _=False: self._refresh_workbook())
            for _btn_name in ('btnLine', 'btnScatter', 'btnCurveFit'):
                _btn = getattr(self, _btn_name, None)
                if _btn is not None:
                    _btn.clicked.connect(lambda _=False: self._show_plot_view())
            # Book1 เป็นจุดเริ่ม workflow ได้เอง: พิมพ์ข้อมูล → ใช้ข้อมูล → พล็อต
            self.workbook.use_data_requested.connect(self.adopt_workbook_data)
            # Origin model: พล็อตจากชีต = Graph ใหม่; overlay = ลงกราฟปัจจุบัน
            self.workbook.plot_requested.connect(
                lambda s: self.plot_from_workbook(s, new_graph=True))
            self.workbook.overlay_requested.connect(
                lambda s: self.plot_from_workbook(s, new_graph=False))
        except Exception:
            logger.debug("workbook wiring skipped", exc_info=True)
        # เผื่อ session ถูก restore แล้วมีข้อมูลอยู่ก่อน — เติมตารางครั้งแรก
        self._refresh_workbook()

    # UI-REFINE: มิเรอร์ DataFrame ปัจจุบันลง worksheet แบบ Origin
    def _refresh_workbook(self) -> None:
        """Mirror the active DataFrame into the Origin-style worksheet and show it.

        Lightweight + guarded: เรียกได้บ่อยโดยไม่พัง และไม่แตะ logic ใน mixin
        """
        try:
            wb = getattr(self, "workbook", None)
            if wb is None:
                return
            df = getattr(self, "_df", None)
            if df is not None and not df.empty:
                wb.set_dataframe(df)
                self._show_data_view()
        except Exception:
            logger.debug("workbook refresh skipped", exc_info=True)

    def _show_data_view(self) -> None:
        """Raise the ACTIVE Book's sub-window in the MDI area (multi-book)."""
        try:
            target = None
            for kind, _title, sub in self.mdi.sub_windows():
                if kind == "book" and sub.widget() is self.workbook:
                    target = sub
                    break
            if target is None:
                target = getattr(self, "_book_sub", None)
            if target is not None:
                self.mdi.mdi.setActiveSubWindow(target)
        except Exception:
            logger.debug("show data view skipped", exc_info=True)

    def _show_plot_view(self) -> None:
        """Raise the current Graph sub-window (the one that was just plotted)."""
        try:
            self.mdi.raise_current_graph()
        except Exception:
            logger.debug("show plot view skipped", exc_info=True)

    # UI-REFINE: แยกสร้างแผงซ้าย (Staging) และแท็บ Inspector ขวา
    def _prompt_restore_session(self):
        # Removed: the "Restore last session" pop-up. Persistence is now
        # explicit via File → Save/Open Project (*.sciproj). Kept as a no-op so
        # the startup QTimer hook stays valid.
        return

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
            logger.debug("Checking for plot buttons")
            logger.debug("hasattr(self, 'btn_line'): %s", hasattr(self, 'btn_line'))
            if hasattr(self, 'btn_line'):
                logger.debug("self.btn_line: %s", self.btn_line)
            logger.debug("hasattr(self, 'btnLine'): %s", hasattr(self, 'btnLine'))
            if hasattr(self, 'btnLine'):
                logger.debug("self.btnLine: %s", self.btnLine)
                
            if hasattr(self, 'btn_line') and self.btn_line:
                self.btn_line.clicked.connect(self.plot_line)
                logger.debug("Connected btn_line to plot_line")
            elif hasattr(self, 'btnLine') and self.btnLine:
                self.btnLine.clicked.connect(self.plot_line)
                logger.debug("Connected btnLine to plot_line")
            else:
                logger.debug("No line button found to connect")
                
            if hasattr(self, 'btn_scatter') and self.btn_scatter:
                self.btn_scatter.clicked.connect(self.plot_scatter)
                logger.debug("Connected btn_scatter to plot_scatter")
            elif hasattr(self, 'btnScatter') and self.btnScatter:
                self.btnScatter.clicked.connect(self.plot_scatter)
                logger.debug("Connected btnScatter to plot_scatter")
            else:
                logger.debug("No scatter button found to connect")
            
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
        # View tools (ฝั่งซ้าย) — staging list ถูกแทนด้วย Origin multi-book แล้ว
        self.chkCross.toggled.connect(self.toggle_crosshair)
        self.btnBoxZoom.clicked.connect(self.start_box_zoom)

    def _wire_load_button(self):
        try:
            # disconnect() warns (not raises) when nothing is connected — silence it
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore")
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
    def resizeEvent(self, event):
        try:
            self._update_compact_ui()
        except Exception:
            pass
        return super().resizeEvent(event)

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

    def _icon(self, name: str, fallback_sp: QStyle.StandardPixmap) -> QIcon:
        colors = _current_icon_theme_colors()
        cache_key = (
            name,
            _fallback_icon_key(fallback_sp),
            colors["normal"],
            colors["disabled"],
            colors["active"],
        )
        cached = _ICON_CACHE.get(cache_key)
        if cached is not None:
            return cached

        qta_id = _QTA_ICON_MAP.get(name)
        if qta_id:
            icon = _qtawesome_icon(qta_id)
            if icon is not None:
                _ICON_CACHE[cache_key] = icon
                return icon

        path = _resolve_icon_path(name)
        if path:
            icon = QIcon(path)
            _ICON_CACHE[cache_key] = icon
            return icon

        try:
            icon = self.style().standardIcon(fallback_sp)
        except Exception:
            icon = QIcon()
        _ICON_CACHE[cache_key] = icon
        return icon

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


def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            logger.debug('Failed to set AppUserModelID', exc_info=True)

    # Native Windows dialogs do not consume Qt palettes/QSS. Keep menus and
    # file/color dialogs inside Qt so Appearance settings cover every popup.
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    QApplication.setAttribute(Qt.AA_DontUseNativeMenuWindows, True)
    app = QApplication(sys.argv)
    try:
        if os.path.isfile(APP_ICON_PATH):
            app_icon = QIcon(APP_ICON_PATH)
            app.setWindowIcon(app_icon)
    except Exception:
        logger.debug('Failed to set application icon', exc_info=True)

    # CLI: register the .sciproj file association then exit (used by installers
    # or a one-time setup). Runs before the GUI so it stays headless.
    if "--register-file-assoc" in sys.argv:
        from core import file_assoc
        ok, msg = file_assoc.register()
        print(msg)
        sys.exit(0 if ok else 1)

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

    # Opened via a .sciproj file (double-click / "Open with") → load it.
    try:
        proj = next((a for a in sys.argv[1:]
                     if a.lower().endswith(".sciproj") and os.path.isfile(a)), None)
        if proj:
            from PySide6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(0, lambda: win.open_project_path(proj))
    except Exception:
        logger.debug("open project from argv skipped", exc_info=True)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()







