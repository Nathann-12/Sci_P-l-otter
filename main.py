# -*- coding: utf-8 -*-
# main.py
import os, sys
import numpy as np
import pandas as pd
import logging
import locale
import json
import itertools

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
from PySide6.QtCore import Qt, QSize, QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QDockWidget, QMessageBox, QSpinBox, QCheckBox, QDialog,
    QListWidget, QListWidgetItem, QToolBar, QInputDialog, QSplitter, QTabWidget, QSizePolicy,
    QFrame, QGroupBox, QStyle, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QAction, QIcon
from enum import Enum
from typing import Any, Dict, List, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from toolbar import PlotNavigationToolbar
import matplotlib.dates as mdates  # CHANGE: handle datetime axes formatting
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection
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
from dialogs_fit import NonlinearFitDialog
from dialogs_spectrogram import SpectrogramDialog  # UI-SPECTROGRAM: Spectrogram dialog
from dialogs_histogram import HistogramDialog  # NEW: Histogram dialog
from charts_gallery import ChartGalleryMenu
from dialogs_units import UnitsDialog  # UI-UNITS: Units and calibration dialog
from core.units import UNIT_REGISTRY  # UI-UNITS: Unit registry for conversions
from processors import add_time_bangkok, add_magnitude, add_moving_average, apply_column_types, compute_fft, FitResult
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
from three_d_view import ThreeDViewDock
from context_menu import ContextMenuManager
from widgets.layer_manager import LayerManagerWidget
from core import session as session_store
# [Equation Plotter]
from dialogs_equation import EquationPlotDialog
from eqplot import plot_equations_on_axes
from eqplot3d import plot_surfaces_on_axes

APP_TITLE = "SciPlotter (Modular + Features)"

APP_ICON_FILENAME = "icon_app.png"
APP_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "icons", APP_ICON_FILENAME)
APP_USER_MODEL_ID = "SciPlotter.SciPlotterApp"

class PlotMode(str, Enum):
    OVERLAY = "overlay"
    REPLACE = "replace"

class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig); self.setParent(parent)
        # Ensure facecolors/grid match current theme immediately on startup
        try:
            import matplotlib as _mpl
            # ใช้ค่าที่กลมกลืนกับธีมเป็นค่าเริ่มต้นเสมอ
            fig_fc = _mpl.rcParams.get("figure.facecolor", "#1e2126") or "#1e2126"
            ax_fc = _mpl.rcParams.get("axes.facecolor", "#1e2126") or "#1e2126"
            grid_col = _mpl.rcParams.get("grid.color", "#3a3f44") or "#3a3f44"
            grid_alpha = float(_mpl.rcParams.get("grid.alpha", 0.3))
            grid_ls = _mpl.rcParams.get("grid.linestyle", "-") or "-"
            text_col = _mpl.rcParams.get("text.color", "#e6e6e6") or "#e6e6e6"

            self.fig.patch.set_facecolor(fig_fc)
            self.ax.set_facecolor(ax_fc)
            # spines/ticks สีให้เหมาะกับธีม
            for sp in self.ax.spines.values():
                sp.set_color(_mpl.rcParams.get("axes.edgecolor", "#3a3f44"))
            self.ax.tick_params(colors=text_col)
            self.ax.yaxis.label.set_color(text_col)
            self.ax.xaxis.label.set_color(text_col)
            # grid on if requested by rc
            if bool(_mpl.rcParams.get("axes.grid", True)):
                self.ax.grid(True, alpha=grid_alpha, linestyle=grid_ls, color=grid_col)
        except Exception:
            pass
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
            current_facecolor = matplotlib.rcParams.get("figure.facecolor", "#1e2126")
            current_axes_facecolor = matplotlib.rcParams.get("axes.facecolor", "#1e2126")
            
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
                current_facecolor = matplotlib.rcParams.get("figure.facecolor", "#1e2126")
                current_axes_facecolor = matplotlib.rcParams.get("axes.facecolor", "#1e2126")
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
        self.toolbar = PlotNavigationToolbar(self.canvas, self)
        
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
        self.layer_manager = LayerManagerWidget(self)
        self.layer_manager.layerVisibilityChanged.connect(self._on_layer_visibility_changed)
        self.layer_manager.layerRenameRequested.connect(self._on_layer_rename)
        self.layer_manager.layerRemoveRequested.connect(self._on_layer_remove)
        self.layer_manager.layerStyleRequested.connect(self._on_layer_style_request)
        self.layers: Dict[str, Dict[str, Any]] = {}
        self._layer_id_seq = itertools.count(1)

        # Rich context menu manager
        try:
            # find MainWindow to pass managers into context menu
            p = self.parent()
            while p is not None and not hasattr(p, 'parent'):
                p = getattr(p, 'parent', lambda: None)()
            mw = self.parent().parent() if hasattr(self.parent(), 'parent') else None
            self.ctx_menu = ContextMenuManager(
                self.canvas, self.canvas.ax,
                main=mw,
                annotation_mgr=self.annotation_manager,
                peak_mgr=getattr(mw, 'peaks', None) if mw else None,
                xcorr_mgr=getattr(mw, 'crosscorr', None) if mw else None,
            )
        except Exception:
            pass
        
    def clear(self):
        """Clear the canvas"""
        self.canvas.clear()
        self.clear_layers()
        
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



    def clear_layers(self) -> None:
        for info in self.layers.values():
            for artist in info.get('artists', []):
                try:
                    artist.remove()
                except Exception:
                    pass
        self.layers.clear()
        self.layer_manager.clear_layers()

    def register_layer(self, artists, label: str, style: str, meta: Optional[Dict[str, Any]] = None, kwargs: Optional[Dict[str, Any]] = None):
        if not artists:
            return None
        if not isinstance(artists, (list, tuple)):
            artists = [artists]
        layer_id = f"{self.tab_id}_L{next(self._layer_id_seq)}"
        visible = True
        for artist in artists:
            try:
                if not artist.get_visible():
                    visible = False
                    break
            except Exception:
                continue
        info = {
            'artists': list(artists),
            'label': label,
            'style': style,
            'meta': dict(meta or {}),
            'kwargs': dict(kwargs or {}),
            'visible': visible,
        }
        self.layers[layer_id] = info
        self.layer_manager.add_layer(layer_id, label, style, visible=visible)
        return layer_id

    def serialize_layers(self) -> List[Dict[str, Any]]:
        data = []
        for layer_id, info in self.layers.items():
            entry = {
                'id': layer_id,
                'label': info.get('label', ''),
                'style': info.get('style', 'line'),
                'visible': info.get('visible', True),
                'meta': info.get('meta', {}),
                'kwargs': info.get('kwargs', {}),
                'data': {},
            }
            artists = info.get('artists', [])
            if artists:
                artist = artists[0]
                try:
                    xdata = artist.get_xdata()
                    ydata = artist.get_ydata()
                    entry['data'] = {
                        'x': self._to_serializable_array(xdata),
                        'y': self._to_serializable_array(ydata),
                    }
                except Exception:
                    try:
                        offsets = artist.get_offsets()
                        entry['data'] = {
                            'x': self._to_serializable_array([pt[0] for pt in offsets]),
                            'y': self._to_serializable_array([pt[1] for pt in offsets]),
                        }
                    except Exception:
                        entry['data'] = {}
            data.append(entry)
        return data

    def restore_layers(self, layers: List[Dict[str, Any]], main_window) -> None:
        try:
            parent_manager = self.parent()
        except Exception:
            parent_manager = None
        if not parent_manager or not hasattr(parent_manager, 'add_series_to_tabs'):
            return
        self.clear()
        self.clear_layers()
        for layer in layers:
            label = layer.get('label', '')
            style = layer.get('style', 'line')
            kwargs = dict(layer.get('kwargs', {}))
            meta = dict(layer.get('meta', {}))
            data = layer.get('data', {}) or {}
            x = data.get('x')
            y = data.get('y')
            if (not x or not y) and main_window is not None:
                df = main_window.get_dataframe_for_layer(meta)
                if df is not None:
                    x_col = meta.get('x_column')
                    y_col = meta.get('y_column')
                    if x_col in df.columns and y_col in df.columns:
                        x = df[x_col].tolist()
                        y = df[y_col].tolist()
            if x is None or y is None:
                continue
            created = parent_manager.add_series_to_tabs([self.tab_id], x, y, label=label, style=style, meta=meta, **kwargs)
            if not layer.get('visible', True) and created:
                for tab_id, new_id in created:
                    if tab_id == self.tab_id and new_id:
                        self.layer_manager.update_layer_visibility(new_id, False)
                        self._set_layer_visibility(new_id, False, refresh=False)
        self.canvas.draw_idle()

    @staticmethod
    def _to_serializable_array(data):
        try:
            import numpy as _np
            arr = _np.asarray(data)
            return arr.astype(float).tolist()
        except Exception:
            try:
                return [float(v) for v in data]
            except Exception:
                try:
                    return list(data)
                except Exception:
                    return []

    def _set_layer_visibility(self, layer_id: str, visible: bool, refresh: bool = True) -> None:
        info = self.layers.get(layer_id)
        if not info:
            return
        for artist in info.get('artists', []):
            try:
                artist.set_visible(visible)
            except Exception:
                pass
        info['visible'] = visible
        if refresh:
            self._refresh_legend()
            try:
                self.canvas.draw_idle()
            except Exception:
                pass

    def _refresh_legend(self) -> None:
        ax = self.get_axes()
        try:
            legend = ax.get_legend()
            if legend:
                legend.remove()
        except Exception:
            pass
        try:
            handles, labels = ax.get_legend_handles_labels()
            pairs = [
                (h, lbl) for h, lbl in zip(handles, labels)
                if lbl and not str(lbl).startswith('_') and getattr(h, 'get_visible', lambda: True)()
            ]
            if pairs:
                h, l = zip(*pairs)
                ax.legend(h, l, loc='best')
        except Exception:
            pass

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        self._set_layer_visibility(layer_id, visible)

    def _on_layer_rename(self, layer_id: str, new_label: str) -> None:
        info = self.layers.get(layer_id)
        if not info:
            return
        info['label'] = new_label
        info.setdefault('meta', {})
        info['meta']['label'] = new_label
        for artist in info.get('artists', []):
            try:
                artist.set_label(new_label)
            except Exception:
                pass
        self.layer_manager.update_layer_label(layer_id, new_label)
        self._refresh_legend()
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

    def _on_layer_remove(self, layer_id: str) -> None:
        info = self.layers.pop(layer_id, None)
        if not info:
            return
        for artist in info.get('artists', []):
            try:
                artist.remove()
            except Exception:
                pass
        self.layer_manager.remove_layer(layer_id)
        self._refresh_legend()
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

    def _on_layer_style_request(self, layer_id: str) -> None:
        info = self.layers.get(layer_id)
        if not info:
            return
        if info.get('style') != 'line':
            return
        artists = [a for a in info.get('artists', []) if hasattr(a, 'set_color')]
        if not artists:
            return
        info.setdefault('kwargs', {})
        info.setdefault('meta', {})
        style_meta = dict(info['meta'].get('style_kwargs', {}))
        color = self.layer_manager.prompt_color()
        if color and getattr(color, 'isValid', lambda: False)():
            color_name = color.name()
            for artist in artists:
                try:
                    artist.set_color(color_name)
                except Exception:
                    pass
            info['kwargs']['color'] = color_name
            style_meta['color'] = color_name
        try:
            from PySide6.QtWidgets import QInputDialog
            current_width = artists[0].get_linewidth() if artists else 1.0
            width, ok = QInputDialog.getDouble(self, "Line Width", "Width:", float(current_width), 0.1, 50.0, 2)
            if ok:
                for artist in artists:
                    try:
                        artist.set_linewidth(width)
                    except Exception:
                        pass
                info['kwargs']['linewidth'] = float(width)
                style_meta['linewidth'] = float(width)
        except Exception:
            pass
        if style_meta:
            info['meta']['style_kwargs'] = style_meta
        self._refresh_legend()
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

class TabManager(QTabWidget):
    """
    Manages multiple graph tabs with browser-like functionality.
    """
    tabCreated = Signal(str)
    tabRemoved = Signal(str)

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
        
        # Store reference FIRST before setting current index
        self.tabs[tab_id] = graph_tab
        
        # Set current index AFTER storing reference
        self.setCurrentIndex(index)
        
        try:
            self.tabCreated.emit(tab_id)
        except Exception:
            pass
        
        return tab_id

    def remove_all_tabs(self):
        while self.count():
            widget = self.widget(0)
            tab_identifier = None
            for tid, tab in list(self.tabs.items()):
                if tab == widget:
                    tab_identifier = tid
                    break
            self.removeTab(0)
            if tab_identifier:
                self.tabs.pop(tab_identifier, None)
                try:
                    self.tabRemoved.emit(tab_identifier)
                except Exception:
                    pass
            if widget is not None:
                try:
                    widget.deleteLater()
                except Exception:
                    pass
        
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
            try:
                self.tabRemoved.emit(tab_id)
            except Exception:
                pass

        self.removeTab(index)

        if tab_widget is not None:
            try:
                tab_widget.hide()
            except Exception:
                pass
            try:
                tab_widget.deleteLater()
            except Exception:
                pass

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
        
    def plot_to_tabs(self, tab_ids, x, y, label="", style="line", meta: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Plot data to specified tabs. If the main window is in overlay mode, defer
        to add_series_to_tabs so existing layers are preserved.
        """
        created = []
        for tab_id in tab_ids:
            if tab_id not in self.tabs:
                continue
            tab = self.tabs[tab_id]
            ax = tab.get_axes()
            try:
                mw = self.parent() if hasattr(self, 'parent') else None
                mode = getattr(mw, 'plot_mode', None)
            except Exception:
                mode = None
            overlay_mode = mode is not None and not str(mode).endswith('REPLACE')
            if overlay_mode:
                created.extend(self.add_series_to_tabs([tab_id], x, y, label=label, style=style, meta=meta, **kwargs))
                continue
            tab.clear_layers()
            ax.clear()
            local_kwargs = dict(kwargs)
            artists = []
            if style == "line":
                artists = list(ax.plot(x, y, label=label, **local_kwargs))
            elif style == "scatter":
                artists = [ax.scatter(x, y, label=label, **local_kwargs)]
            elif style == "bar":
                container = ax.bar(range(len(x)), y, label=label, **local_kwargs)
                artists = list(container)
                ax.set_xticks(range(len(x)))
                try:
                    ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
                except Exception:
                    pass
            elif style == "histogram":
                hist = ax.hist(y, label=label, **local_kwargs)
                artists = list(hist[2]) if len(hist) >= 3 else []
            else:
                artists = list(ax.plot(x, y, label=label, **local_kwargs))
            ax.relim(); ax.autoscale_view()
            ax.grid(True, alpha=0.3)
            if label:
                try:
                    ax.legend(loc="best")
                except Exception:
                    pass
            try:
                tab.canvas.fig.tight_layout()
            except Exception:
                pass
            try:
                tab.draw()
            except Exception:
                try:
                    tab.canvas.draw()
                except Exception:
                    try:
                        tab.canvas.fig.canvas.draw_idle()
                    except Exception:
                        pass
            layer_meta = dict(meta or {})
            layer_meta.setdefault('style', style)
            if label:
                layer_meta.setdefault('label', label)
            layer_id = tab.register_layer(artists, label or "", style, meta=layer_meta, kwargs=local_kwargs)
            if layer_id:
                created.append((tab_id, layer_id))
                if hasattr(tab, '_refresh_legend'):
                    tab._refresh_legend()
        return created

    def add_series_to_tabs(self, tab_ids, x, y, label: str = "", style: str = "line", meta: Optional[Dict[str, Any]] = None, **kwargs):
        """Overlay a new series onto existing plots without clearing."""
        created = []
        base_kwargs = dict(kwargs)
        for tab_id in tab_ids:
            if tab_id not in self.tabs:
                continue
            tab = self.tabs[tab_id]
            ax = tab.get_axes()
            auto_label = label
            if not auto_label:
                try:
                    auto_label = f"Series {len([l for l in ax.get_lines() if not l.get_label().startswith('_')]) + 1}"
                except Exception:
                    auto_label = "Series"
            local_kwargs = dict(base_kwargs)
            artists = []
            try:
                if style == "line":
                    artists = list(ax.plot(x, y, label=auto_label, **local_kwargs))
                elif style == "scatter":
                    artists = [ax.scatter(x, y, label=auto_label, **local_kwargs)]
                elif style == "bar":
                    container = ax.bar(range(len(x)), y, label=auto_label, **local_kwargs)
                    artists = list(container)
                    ax.set_xticks(range(len(x)))
                    try:
                        ax.set_xticklabels(list(map(str, x)), rotation=45, ha="right")
                    except Exception:
                        pass
                elif style == "histogram":
                    hist = ax.hist(y, label=auto_label, **local_kwargs)
                    artists = list(hist[2]) if len(hist) >= 3 else []
                else:
                    artists = list(ax.plot(x, y, label=auto_label, **local_kwargs))
                ax.relim(); ax.autoscale_view()
                try:
                    handles, labels = ax.get_legend_handles_labels()
                    if any(lbl and not lbl.startswith('_') for lbl in labels):
                        ax.legend(loc="best")
                except Exception:
                    pass
                try:
                    from processors import beautify_axes
                    beautify_axes(ax)
                except Exception:
                    pass
                try:
                    tab.canvas.fig.tight_layout()
                except Exception:
                    pass
                try:
                    tab.draw()
                except Exception:
                    try:
                        tab.canvas.draw()
                    except Exception:
                        try:
                            tab.canvas.fig.canvas.draw_idle()
                        except Exception:
                            pass
                layer_meta = dict(meta or {})
                layer_meta.setdefault('style', style)
                layer_meta.setdefault('label', auto_label)
                layer_id = tab.register_layer(artists, auto_label, style, meta=layer_meta, kwargs=local_kwargs)
                if layer_id:
                    created.append((tab_id, layer_id))
                    if hasattr(tab, '_refresh_legend'):
                        tab._refresh_legend()
            except Exception as e:
                print(f"Debug: add_series_to_tabs error on {tab_id}: {e}")
        return created

    def add_series_to_current_tab(self, x, y, label: str = "", style: str = "line", meta: Optional[Dict[str, Any]] = None, **kwargs):
        """Convenience wrapper to add a series to the currently active tab without clearing."""
        current_tab_id = self.get_current_tab_id()
        if not current_tab_id:
            return []
        return self.add_series_to_tabs([current_tab_id], x, y, label=label, style=style, meta=meta, **kwargs)


class CompactPlotPanel(QWidget):
    """
    Compact Plot controls panel using form/grid layouts.
    Exposes widgets so the app can wire signals without changing logic.
    Attributes exposed:
      - btnLoadCols, cbo_x, cbo_y, spin_width, chk_points,
        btn_line, btn_scatter, btn_clear, btn_fit
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlotPanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # Load columns button (kept for existing workflow)
        self.btnLoadCols = QPushButton("โหลดคอลัมน์จากข้อมูล")
        self.btnLoadCols.setMinimumHeight(28)
        self.btnLoadCols.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer.addWidget(self.btnLoadCols)

        # Form section
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        self.cbo_x = QComboBox(); self.cbo_y = QComboBox()
        for cb in (self.cbo_x, self.cbo_y):
            cb.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            cb.setMinimumWidth(140)
            cb.setFixedHeight(28)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 10)
        self.spin_width.setValue(2)
        self.spin_width.setFixedHeight(28)

        self.chk_points = QCheckBox("แสดงจุดข้อมูล")

        form.addRow("เลือกคอลัมน์แกน X", self.cbo_x)
        form.addRow("เลือกคอลัมน์แกน Y", self.cbo_y)
        form.addRow("ความหนาเส้น", self.spin_width)
        form.addRow("", self.chk_points)
        outer.addLayout(form)

        # Buttons grid 2x2
        grid = QGridLayout(); grid.setContentsMargins(0, 0, 0, 0); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(6)
        self.btn_line = QPushButton("แสดงกราฟเส้น")
        self.btn_scatter = QPushButton("แสดงกราฟจุด (Scatter)")
        self.btn_clear = QPushButton("ล้างกราฟ")
        self.btn_fit = QPushButton("Curve Fit...")
        for b in (self.btn_line, self.btn_scatter, self.btn_clear, self.btn_fit):
            b.setMinimumHeight(32); b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid.addWidget(self.btn_line, 0, 0)
        grid.addWidget(self.btn_scatter, 0, 1)
        grid.addWidget(self.btn_clear, 1, 0)
        grid.addWidget(self.btn_fit, 1, 1)
        outer.addLayout(grid)

        # width limit
        self.setMaximumWidth(420)

        # Compact style
        self.setStyleSheet(
            """
            QWidget#PlotPanel QComboBox, QWidget#PlotPanel QSpinBox {
                padding: 2px 6px; min-height: 24px; border-radius: 6px;
            }
            QWidget#PlotPanel QPushButton {
                padding: 4px 10px; min-height: 28px; border-radius: 8px;
            }
            """
        )


class MainWindow(QMainWindow):
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
    def _build_left_panel(self):
        l = self._left_layout
        self.lblFile = QLabel("ยังไม่ได้เปิดไฟล์"); self.lblFile.setWordWrap(True); l.addWidget(self.lblFile)

        # CHANGE: กล่อง "ไฟล์ที่เตรียมไว้"
        gb_files = QGroupBox("ไฟล์ที่เตรียมไว้")
        gbf = QVBoxLayout(gb_files); gbf.setContentsMargins(8, 8, 8, 8); gbf.setSpacing(8)
        self.lstFiles = QListWidget(); self.lstFiles.setSelectionMode(QListWidget.SingleSelection); gbf.addWidget(self.lstFiles)
        rowStage = QHBoxLayout()
        self.btnAddStage = QPushButton("เพิ่มไฟล์…"); self.btnUseStage = QPushButton("ใช้ไฟล์นี้"); self.btnDelStage = QPushButton("ลบออก")
        rowStage.addWidget(self.btnAddStage); rowStage.addWidget(self.btnUseStage); rowStage.addWidget(self.btnDelStage);
        # Ensure equal widths for the 3 buttons and compact spacing
        try:
            rowStage.setStretch(0, 1); rowStage.setStretch(1, 1); rowStage.setStretch(2, 1)
            rowStage.setSpacing(8)
            rowStage.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        gbf.addLayout(rowStage)
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
        """
        Inspector ด้านขวา: Plot / Processing / Export
        - Plot ใช้ CompactPlotPanel เพียงชุดเดียว (ไม่มีวิดเจ็ตเก่าซ้ำซ้อน)
        - ทำ alias ตัวแปรเดิมให้โค้ดส่วนอื่นเรียกต่อได้
        """
        from PySide6.QtWidgets import (
            QTabWidget, QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QPushButton, QFrame
        )
        from PySide6.QtCore import Qt

        r = self._right_layout

        # ---------- Tabs ----------
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)
        try:
            tabs.setMaximumWidth(420)
        except Exception:
            pass

        # ================== TAB: PLOT ==================
        tab_plot = QWidget()
        tp = QVBoxLayout(tab_plot)
        tp.setContentsMargins(8,8,8,8)
        tp.setSpacing(8)

        # ใช้ CompactPlotPanel เพียงตัวเดียว
        panel = CompactPlotPanel(self)
        tp.addWidget(panel)

        # --- Alias ให้ชื่อเดิม เพื่อไม่ให้โค้ดส่วนอื่นพัง ---
        self.panel_plot = panel
        self.btnLoadCols = getattr(panel, "btnLoadCols", getattr(panel, "btn_load_cols", None))
        self.cbX         = panel.cbo_x
        self.cbY         = panel.cbo_y
        self.spLineWidth = panel.spin_width
        self.chkMarker   = panel.chk_points
        self.btnLine     = panel.btn_line
        self.btnScatter  = panel.btn_scatter
        self.btnClear    = panel.btn_clear
        self.btnCurveFit = panel.btn_fit
        self.layerGroup = QGroupBox("Layers", self)
        self.layerGroupLayout = QVBoxLayout(self.layerGroup)
        self.layerGroupLayout.setContentsMargins(6, 6, 6, 6)
        self.layerGroupLayout.setSpacing(6)
        self._layer_manager_empty = QLabel("ยังไม่มีเลเยอร์", self.layerGroup)
        self._layer_manager_empty.setAlignment(Qt.AlignCenter)
        self.layerGroupLayout.addWidget(self._layer_manager_empty)
        tp.addWidget(self.layerGroup)

        tabs.addTab(tab_plot, "Plot")

        # ================== TAB: PROCESSING ==================
        tab_proc = QWidget()
        pr = QVBoxLayout(tab_proc); pr.setContentsMargins(8,8,8,8); pr.setSpacing(8)

        gb_feat = QGroupBox("ฟีเจอร์เสริม"); pr.addWidget(gb_feat)
        gbl = QVBoxLayout(gb_feat); gbl.setContentsMargins(8,8,8,8); gbl.setSpacing(8)
        row1 = QHBoxLayout(); 
        self.btnTZ  = QPushButton("เพิ่มคอลัมน์เวลา +7h (Bangkok)"); 
        self.btnMag = QPushButton("เพิ่มคอลัมน์ |B| จาก 3 แกน"); 
        row1.addWidget(self.btnTZ); row1.addWidget(self.btnMag); gbl.addLayout(row1)
        row2 = QHBoxLayout(); 
        self.btnMA  = QPushButton("เพิ่มคอลัมน์ Moving Average (จาก Y)"); 
        row2.addWidget(self.btnMA); gbl.addLayout(row2)
        rowAgg = QHBoxLayout(); 
        self.btnAgg = QPushButton("Aggregate…"); 
        rowAgg.addWidget(self.btnAgg); gbl.addLayout(rowAgg)

        gb_fmt = QGroupBox("การจัดรูปแบบข้อมูล"); pr.addWidget(gb_fmt)
        gbf = QVBoxLayout(gb_fmt); gbf.setContentsMargins(8,8,8,8); gbf.setSpacing(8)
        row3 = QHBoxLayout(); 
        self.btnTypes = QPushButton("กำหนดชนิดคอลัมน์"); 
        row3.addWidget(self.btnTypes); gbf.addLayout(row3)

        tabs.addTab(tab_proc, "Processing")

        # ================== TAB: EXPORT ==================
        tab_exp = QWidget()
        ex = QVBoxLayout(tab_exp); ex.setContentsMargins(8,8,8,8); ex.setSpacing(8)
        self.btnExport      = QPushButton("บันทึกรูปภาพ (PNG)"); ex.addWidget(self.btnExport)
        self.btnExportRange = QPushButton("ส่งออกช่วงที่เห็น (CSV)"); ex.addWidget(self.btnExportRange)
        self.btnExportAgg   = QPushButton("Export Aggregated CSV"); ex.addWidget(self.btnExportAgg)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        ex.addWidget(sep)

        self.btnExportReport = QPushButton("Export Report (PDF)"); ex.addWidget(self.btnExportReport)

        tabs.addTab(tab_exp, "Export")

        # ---------- mount ----------
        r.addWidget(tabs)
        self._mount_layer_manager()
        return
        # Legacy load-cols and X/Y controls are replaced by CompactPlotPanel; do not add duplicates
        # self.btnLoadCols = QPushButton("โหลดคอลัมน์จากข้อมูล")
        # tp.addWidget(self.btnLoadCols)
        # tp.addWidget(QLabel("เลือกคอลัมน์แกน X")); self.cbX = QComboBox(); tp.addWidget(self.cbX)
        # tp.addWidget(QLabel("เลือกคอลัมน์แกน Y")); self.cbY = QComboBox(); tp.addWidget(self.cbY)
        styleRow = QHBoxLayout(); styleRow.addWidget(QLabel("ความหนาเส้น")); self.spLineWidth = QSpinBox(); self.spLineWidth.setRange(1,10); self.spLineWidth.setValue(2); styleRow.addWidget(self.spLineWidth); tp.addLayout(styleRow)
        markerRow = QHBoxLayout(); self.chkMarker = QCheckBox("แสดงจุดข้อมูล"); self.chkMarker.setChecked(False); markerRow.addWidget(self.chkMarker); markerRow.addStretch(1); tp.addLayout(markerRow)
        btnRow = QHBoxLayout(); self.btnLine = QPushButton("แสดงกราฟเส้น"); self.btnScatter = QPushButton("แสดงกราฟจุด (Scatter)"); btnRow.addWidget(self.btnLine); btnRow.addWidget(self.btnScatter); tp.addLayout(btnRow)
        # UI-REFINE: ปุ่มล้างกราฟ (Clear Plot)
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
        # Inject compact plot panel and remap references before signals are connected
        try:
            _panel = CompactPlotPanel(self)
            # Replace legacy widget refs with compact ones for downstream logic
            self.btnLoadCols = _panel.btnLoadCols
            self.cbX = _panel.cbo_x
            self.cbY = _panel.cbo_y
            self.spLineWidth = _panel.spin_width
            self.chkMarker = _panel.chk_points
            self.btnLine = _panel.btn_line
            self.btnScatter = _panel.btn_scatter
            self.btnClear = _panel.btn_clear
            self.btnCurveFit = _panel.btn_fit
            # Place compact panel at top
            try:
                tp.insertWidget(0, _panel)
            except Exception:
                tp.addWidget(_panel)
            try:
                self.btnLoadCols.raise_()
            except Exception:
                pass
            # Remove legacy controls in Plot tab that are not inside CompactPlotPanel
            try:
                from PySide6.QtWidgets import QPushButton as _QB, QComboBox as _QCB, QSpinBox as _QSB, QCheckBox as _QCK, QLabel as _QL
                def _remove_if_not_in_panel(widget):
                    try:
                        if _panel.isAncestorOf(widget):
                            return
                    except Exception:
                        return
                    try:
                        parent = widget.parent()
                        widget.setParent(None)
                        widget.deleteLater()
                        if parent and hasattr(parent, 'update'):
                            parent.update()
                    except Exception:
                        pass
                for cls in (_QB, _QCB, _QSB, _QCK, _QL):
                    for w in tab_plot.findChildren(cls):
                        _remove_if_not_in_panel(w)
            except Exception:
                pass
        except Exception:
            pass
        # Hide Spectrogram/Histogram controls in Plot tab (moved to Analysis dialogs)
        try:
            if hasattr(self, 'btnSpectrogram'): self.btnSpectrogram.setVisible(False)
            if hasattr(self, 'cbHist'): self.cbHist.setVisible(False)
            if hasattr(self, 'spHistBins'): self.spHistBins.setVisible(False)
            if hasattr(self, 'chkHistFit'): self.chkHistFit.setVisible(False)
            if hasattr(self, 'btnHist'): self.btnHist.setVisible(False)
            # Hide the 'Histogram' title label if present
            for _lbl in tab_plot.findChildren(QLabel):
                try:
                    if str(_lbl.text()).strip().lower() == "histogram":
                        _lbl.setVisible(False)
                except Exception:
                    pass
        except Exception:
            pass
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
        # Remove legacy Spectrogram/Histogram controls from Plot tab and tighten layout
        try:
            self._post_build_cleanup_plot_panel(tab_plot)
        except Exception:
            pass

    def _mount_layer_manager(self):
        layout = getattr(self, 'layerGroupLayout', None)
        if layout is None:
            return
        # Clear current widget(s) inside container
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                try:
                    widget.hide()
                except Exception:
                    pass
                widget.setParent(None)
        tab_widget = None
        try:
            tab_widget = self.tabs.currentWidget()
        except Exception:
            tab_widget = None
        if tab_widget and hasattr(tab_widget, 'layer_manager'):
            layer_widget = tab_widget.layer_manager
            try:
                layer_widget.setParent(self.layerGroup)
            except Exception:
                pass
            layout.addWidget(layer_widget)
            layer_widget.show()
        else:
            placeholder = getattr(self, '_layer_manager_empty', None)
            if placeholder is None:
                placeholder = QLabel('ยังไม่มีเลเยอร์', self.layerGroup if hasattr(self, 'layerGroup') else None)
                placeholder.setAlignment(Qt.AlignCenter)
                self._layer_manager_empty = placeholder
            try:
                placeholder.setParent(self.layerGroup)
            except Exception:
                pass
            layout.addWidget(placeholder)
            placeholder.show()

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

    def refresh_xy_columns(self):
        """
        โหลดคอลัมน์จาก DataFrame ปัจจุบัน → เติมลง cbo_x/cbo_y
        - คงค่าที่ผู้ใช้เลือกไว้ถ้ายังมีคอลัมน์นั้นอยู่
        - กรองเฉพาะคอลัมน์ตัวเลขสำหรับ Y
        - เดา X จากชื่อ time/t/timestamp/datetime ถ้ามี
        """
        try:
            from PySide6.QtCore import QSignalBlocker as _QSignalBlocker
        except Exception:
            _QSignalBlocker = None
        # Resolve current DataFrame
        df = getattr(self, 'current_df', None)
        if df is None or (hasattr(df, 'empty') and df.empty):
            df = getattr(self, '_df', None)
        if (df is None) or (hasattr(df, 'empty') and df.empty):
            # Try staging selection
            try:
                if hasattr(self, 'lstFiles') and hasattr(self, '_datasets'):
                    item = self.lstFiles.currentItem()
                    if item is not None:
                        data = self._datasets.get(item.text())
                        if data and isinstance(data.get('df'), pd.DataFrame):
                            df = data['df']
                            self._df = df.copy()
                            self._current_path = data.get('path')
            except Exception:
                pass
        if df is None or (hasattr(df, 'empty') and df.empty):
            QMessageBox.information(self, "No data", "ยังไม่มีข้อมูลที่ใช้งานอยู่")
            return

        cols = [str(c) for c in df.columns]
        try:
            num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        except Exception:
            num_cols = cols[:]

        # Preserve old selection
        try:
            old_x = self.cbX.currentText().strip()
        except Exception:
            old_x = ""
        try:
            old_y = self.cbY.currentText().strip()
        except Exception:
            old_y = ""

        # Fill combos with signal blocking
        if _QSignalBlocker is not None:
            try:
                with _QSignalBlocker(self.cbX), _QSignalBlocker(self.cbY):
                    self.cbX.clear(); self.cbY.clear()
                    self.cbX.addItems(cols)
                    self.cbY.addItems(num_cols if num_cols else cols)
            except Exception:
                self.cbX.clear(); self.cbY.clear()
                self.cbX.addItems(cols)
                self.cbY.addItems(num_cols if num_cols else cols)
        else:
            self.cbX.clear(); self.cbY.clear()
            self.cbX.addItems(cols)
            self.cbY.addItems(num_cols if num_cols else cols)
        # Sync histogram column combo if present
        try:
            if hasattr(self, 'cbHist') and isinstance(self.cbHist, QComboBox):
                if _QSignalBlocker is not None:
                    with _QSignalBlocker(self.cbHist):
                        self.cbHist.clear(); self.cbHist.addItems(cols)
                else:
                    self.cbHist.clear(); self.cbHist.addItems(cols)
        except Exception:
            pass

        # Restore X if possible; else guess by time-like names
        idx = self.cbX.findText(old_x) if old_x else -1
        if idx >= 0:
            self.cbX.setCurrentIndex(idx)
        else:
            t_candidates = [c for c in cols if any(k in str(c).lower() for k in ("time","t","timestamp","datetime"))]
            self.cbX.setCurrentText(t_candidates[0] if t_candidates else (num_cols[0] if num_cols else cols[0]))

        # Restore Y if possible; else first numeric not equal to X
        idy = self.cbY.findText(old_y) if old_y else -1
        if idy >= 0:
            self.cbY.setCurrentIndex(idy)
        else:
            try:
                pref = [c for c in num_cols if c != self.cbX.currentText()]
                self.cbY.setCurrentText(pref[0] if pref else (num_cols[0] if num_cols else cols[0]))
            except Exception:
                if cols:
                    self.cbY.setCurrentText(cols[0])

        # Status/labels
        try:
            rows_count = len(df)
            cols_count = len(df.columns)
            try:
                self._sb_rows.setText(f"rows: {rows_count:,}")
            except Exception:
                pass
            self.statusBar().showMessage(f"Loaded columns: rows={rows_count:,}, cols={cols_count}")
        except Exception:
            pass

    def apply_sidepanel_style(self):
        """Assign object names, classes, sizes, and shadows to the left side panel."""
        try:
            # Container name for QSS scoping
            self._panel_left.setObjectName("SidePanel")

            # Staging list styling hooks
            try:
                self.lstFiles.setObjectName("StagingList")
                self.lstFiles.setAlternatingRowColors(False)
                self.lstFiles.setUniformItemSizes(False)
                try:
                    self.lstFiles.setWordWrap(False)
                    self.lstFiles.setTextElideMode(Qt.ElideNone)
                except Exception:
                    pass
            except Exception:
                pass

            # Buttons sizing + class names
            for btn, cls in (
                (self.btnUseStage, "btn-primary"),
                (self.btnAddStage, "btn-secondary"),
                (self.btnDelStage, "btn-secondary"),
                (self.btnBoxZoom, "btn-primary"),
            ):
                try:
                    btn.setProperty("class", cls)
                    btn.setMinimumHeight(34)
                    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    # Allow shrink so three can fit on narrow sidebars
                    try:
                        btn.setMinimumWidth(0)
                    except Exception:
                        pass
                except Exception:
                    pass
            # Button/checkbox readable Thai/English labels
            try:
                self.btnAddStage.setText("เพิ่มไฟล์")
                self.btnUseStage.setText("ใช้ไฟล์")
                self.btnDelStage.setText("ลบ")
                self.btnBoxZoom.setText("เลือกช่วง (ลากเพื่อซูม)")
                self.chkCross.setText("แสดง Crosshair")
            except Exception:
                pass

            # Card-like frames: add class and shadow, adjust padding
            try:
                cards = self._panel_left.findChildren(QGroupBox)
                for card in cards:
                    try:
                        card.setProperty("class", "card")
                        lay = card.layout()
                        if lay:
                            lay.setContentsMargins(12, 12, 12, 12)
                            lay.setSpacing(10)
                        # Subtle drop shadow
                        eff = QGraphicsDropShadowEffect(card)
                        eff.setColor(Qt.black)
                        eff.setBlurRadius(18)
                        eff.setOffset(0, 2)
                        card.setGraphicsEffect(eff)
                    except Exception:
                        pass
                # Set clean Thai/English titles by containment
                for card in cards:
                    try:
                        if hasattr(self, 'lstFiles') and isinstance(self.lstFiles, QListWidget) and card.isAncestorOf(self.lstFiles):
                            card.setTitle("ไฟล์ที่เตรียมไว้")
                        elif hasattr(self, 'chkCross') and isinstance(self.chkCross, QCheckBox) and card.isAncestorOf(self.chkCross):
                            card.setTitle("Crosshair")
                        elif hasattr(self, 'btnBoxZoom') and isinstance(self.btnBoxZoom, QPushButton) and card.isAncestorOf(self.btnBoxZoom):
                            card.setTitle("มุมมอง / เมาส์")
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def _init_menu(self):
        m = self.menuBar()
        fileMenu = m.addMenu("&File")  # UI-REFINE: File
        self.actOpen = fileMenu.addAction("Open Data (CSV/TSV/TXT/XLSX/NC/CDF)...")
        self.actOpen.triggered.connect(lambda: getattr(self, 'open_file', lambda: None)())
        actExport = fileMenu.addAction("Export PNG..."); actExport.triggered.connect(self.on_action_export_figure)
        fileMenu.addSeparator()
        actExit = fileMenu.addAction("ออกจากโปรแกรม"); actExit.triggered.connect(self.close)

        viewMenu = m.addMenu("&มุมมอง")  # UI-REFINE: View
        actReset = viewMenu.addAction("รีเซ็ตมุมมองกราฟ")
        actReset.triggered.connect(lambda: [self.canvas.ax.set_xlim(auto=True), self.canvas.ax.set_ylim(auto=True), self.canvas.draw()])
        try:
            viewMenu.addAction(self.actToggleInspector)
            try:
                viewMenu.addAction(self.view3DDock.toggleViewAction())
            except Exception:
                pass
        except Exception:
            try:
                self.actToggleInspector = QAction("Inspector", self)
                self.actToggleInspector.setCheckable(True)
                self.actToggleInspector.triggered.connect(self.toggle_inspector)
                viewMenu.addAction(self.actToggleInspector)
            except Exception:
                pass
        
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

        self.dataMenu = m.addMenu("&Data")  # UI-UNITS: Data menu for units and calibration
        
        # Plot menu (top menubar) – overlay only
        plotMenu = m.addMenu("&Plot")
        actAddLine = plotMenu.addAction("Add Line (overlay)")
        actAddScatter = plotMenu.addAction("Add Scatter (overlay)")
        try:
            actAddLine.setShortcut("Ctrl+Shift+L")
            actAddScatter.setShortcut("Ctrl+Shift+S")
        except Exception:
            pass
        actAddLine.triggered.connect(self.add_line_overlay)
        actAddScatter.triggered.connect(self.add_scatter_overlay)
        if hasattr(self, 'actPlotEquation'):
            plotMenu.addAction(self.actPlotEquation)
        else:
            self.actPlotEquation = plotMenu.addAction('Plot from Equation...')
            self.actPlotEquation.triggered.connect(self.on_plot_from_equation)
            try:
                self.actPlotEquation.setIcon(self._icon('Plot_from_Equation', QStyle.StandardPixmap.SP_DialogApplyButton))
            except Exception:
                pass
        self.dataMenu.addAction("หน่วยและการสอบเทียบ…").triggered.connect(self.open_units_dialog)
        
        procMenu = m.addMenu("&Process")  # UI-REFINE: Process
        procMenu.addAction("FFT").triggered.connect(self.run_fft_dialog)
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

        # Settings menu for plotting mode
        try:
            from PySide6.QtGui import QActionGroup
            settings_menu = m.addMenu("&Settings")
            plot_mode_menu = settings_menu.addMenu("Plotting Mode")
            grp = QActionGroup(self); grp.setExclusive(True)
            act_overlay = QAction("Overlay (default)", self, checkable=True)
            act_replace = QAction("Replace", self, checkable=True)
            grp.addAction(act_overlay); grp.addAction(act_replace)
            plot_mode_menu.addAction(act_overlay); plot_mode_menu.addAction(act_replace)
            act_overlay.setChecked(getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.OVERLAY)
            act_replace.setChecked(getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE)
            def _set_mode(mode):
                try:
                    self.plot_mode = mode
                    if hasattr(self, 'settings'):
                        self.settings.setValue("plot/mode", mode.value)
                except Exception:
                    self.plot_mode = mode
            act_overlay.triggered.connect(lambda: _set_mode(PlotMode.OVERLAY))
            act_replace.triggered.connect(lambda: _set_mode(PlotMode.REPLACE))
        except Exception:
            pass

        helpMenu = m.addMenu("&ช่วยเหลือ")  # UI-REFINE: Help → Shortcuts
        actAbout = helpMenu.addAction("เกี่ยวกับโปรแกรม"); actAbout.triggered.connect(self.show_about)
        # อัปเดตช็อตคัตให้ครอบคลุมฟีเจอร์ใหม่ (Annotation/Analysis)
        help_shortcuts = (
            "CTRL+O: Open\n"
            "CTRL+R: Reset View\n"
            "CTRL+SHIFT+L: Add Line (overlay)\n"
            "CTRL+SHIFT+S: Add Scatter (overlay)\n"
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

        # Charts gallery menu (Excel-like)
        try:
            import pandas as _pd
            def _cg_get_df():
                df = getattr(self, "_df", None)
                return df if df is not None else _pd.DataFrame()
            def _cg_get_fig():
                try:
                    if getattr(self, "canvas", None) and hasattr(self.canvas, "fig"):
                        return self.canvas.fig
                except Exception:
                    pass
                try:
                    tab = self.tabs.currentWidget()
                    return tab.get_figure()
                except Exception:
                    # Last resort: create a temporary Figure (won't show on canvas)
                    from matplotlib.figure import Figure as _Figure
                    return _Figure()
            charts_menu = ChartGalleryMenu(get_dataframe=_cg_get_df, get_main_figure=_cg_get_fig, apply_plot=self.apply_plot, parent=self)
            m.addMenu(charts_menu)
        except Exception:
            pass

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

        # --- MENU-BAR ONLY: Analysis --- (No toolbar entries for Analysis)
        # Lazy-import overlay dialog and wire actions directly under Analysis
        from PySide6.QtWidgets import QMessageBox as _QMessageBox
        from pathlib import Path as _Path
        import sys as _sys, traceback as _traceback

        # Ensure project folder is on sys.path (for dialogs_charts_adv import)
        try:
            _sys.path.insert(0, str(_Path(__file__).resolve().parent))
        except Exception:
            pass

        def _get_df():
            try:
                df = self._resolve_active_dataframe()
                return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
            except Exception:
                return pd.DataFrame()

        def _apply_to_main(draw_fn, prefer_3d: bool=False):
            try:
                self.apply_plot(draw_fn, prefer_3d=prefer_3d)
            except Exception:
                # fallback: try best effort without clearing
                try:
                    fig = self.canvas.fig
                    ax = fig.axes[-1] if fig.axes else fig.add_subplot(111)
                    draw_fn(ax)
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def open_overlay(kind: str):
            try:
                from dialogs_charts_adv import ChartOptionsDialogPro as _ChartOptionsDialogPro
            except ModuleNotFoundError as e:
                _QMessageBox.critical(
                    self,
                    "Module not found",
                    (
                        "Unable to import 'dialogs_charts_adv.py'.\n"
                        "Make sure the file lives next to main.py or add its folder to PYTHONPATH."
                    ),
                )
                print("Import error:", e)
                print(_traceback.format_exc())
                return
            dlg = _ChartOptionsDialogPro(kind=kind, get_df=_get_df, apply_to_main=_apply_to_main, parent=self)
            dlg.exec()

        for title, kind in [
            ("Line…", "line"),
            ("Scatter…", "scatter"),
            ("Bar…", "bar"),
            ("Area…", "area"),
            ("Box…", "box"),
            ("Pie…", "pie"),
            ("Histogram…", "hist"),
            ("3D Scatter…", "3d_scatter"),
        ]:
            act = QAction(title, self)
            analysisMenu.addAction(act)
            act.triggered.connect(lambda _, k=kind: open_overlay(k))

        analysisMenu.addSeparator()
        fit_icon = self._icon("fit", QStyle.SP_DialogApplyButton)
        self.actNonlinearFit = analysisMenu.addAction(fit_icon, "Nonlinear Curve Fit…")
        self.actNonlinearFit.triggered.connect(self.open_nonlinear_fit_dialog)
        analysisMenu.addSeparator()

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
        self.view3DDock = ThreeDViewDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.view3DDock)
        self.view3DDock.hide()
        self._3d_dock_has_shown = False

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

        # --- Annotation menu (recreate safely) ---
        def _mgr():
            tab = self.tabs.currentWidget()
            return getattr(tab, 'annotation_manager', None)

        try:
            self.annMenu
        except Exception:
            self.annMenu = None
        if self.annMenu is None:
            try:
                self.annMenu = m.addMenu("&Annotation")
                self.actAnnEnable = self.annMenu.addAction("Enable Annotation Mode"); self.actAnnEnable.setCheckable(True)
                self.actAnnText = self.annMenu.addAction("Add Text (T)")
                self.actAnnArrow = self.annMenu.addAction("Add Arrow (W)")
                self.actAnnLine = self.annMenu.addAction("Add Line (L)")
                self.actAnnRect = self.annMenu.addAction("Add Rectangle (R)")
                self.actAnnEllipse = self.annMenu.addAction("Add Ellipse (E)")
                self.actAnnCallout = self.annMenu.addAction("Add Callout (C)")
                self.annMenu.addSeparator()
                self.actAnnStyleDock = self.annMenu.addAction("Style Dock...")
                self.actAnnManage = self.annMenu.addAction("Manage Annotations")
                self.annMenu.addSeparator()
                self.actUndo = self.annMenu.addAction("Undo"); self.actRedo = self.annMenu.addAction("Redo")
                # Shortcuts
                self.actAnnText.setShortcut("T"); self.actAnnArrow.setShortcut("W"); self.actAnnLine.setShortcut("L")
                self.actAnnRect.setShortcut("R"); self.actAnnEllipse.setShortcut("E"); self.actAnnCallout.setShortcut("C")
                self.actUndo.setShortcut("Ctrl+Z"); self.actRedo.setShortcut("Ctrl+Y")
                # Dock
                self.annStyleDock = AnnotationStyleDock(self); self.addDockWidget(Qt.RightDockWidgetArea, self.annStyleDock); self.annStyleDock.hide()
            except Exception:
                pass

        # Wire actions (guarded)
        try:
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
        except Exception:
            pass

        
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
            # Connect lazily to avoid init-order issues
            try:
                self.actOpen.triggered.connect(self.open_file)
            except Exception:
                self.actOpen.triggered.connect(lambda: getattr(self, 'open_file', lambda: None)())
            try:
                self.actOpen.setIcon(self._icon("open", QStyle.StandardPixmap.SP_DialogOpenButton))
            except Exception:
                pass
        
        if not hasattr(self, 'actSettings'):
            self.actSettings = QAction("Settings", self)
            self.actSettings.triggered.connect(self.show_settings)
        if not hasattr(self, 'actPlotEquation'):
            self.actPlotEquation = QAction('Plot from Equation...', self)
            self.actPlotEquation.triggered.connect(self.on_plot_from_equation)
            try:
                self.actPlotEquation.setIcon(self._icon('Plot_from_Equation', QStyle.StandardPixmap.SP_DialogApplyButton))
            except Exception:
                pass
        
        # === กลุ่มที่ 1: ไฟล์และข้อมูล ===
        self.tb.addAction(self.actOpen)
        # Place Inspector as the second button after Open
        self.tb.addAction(self.actToggleInspector)
        self.tb.addAction(self.actPlotEquation)
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
            act_add_tab.setIcon(self._icon("addtab", QStyle.StandardPixmap.SP_FileDialogNewFolder))
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

    # --- Cleanup helpers ---
    def _safe_remove_widget(self, w):
        try:
            if w is None:
                return
            w.hide()
            w.setParent(None)
            w.deleteLater()
        except Exception:
            pass

    def _post_build_cleanup_plot_panel(self, plot_widget):
        """Remove legacy Spectrogram/Histogram widgets from Plot tab and compact layout."""
        try:
            for name in ("btnSpectrogram", "cbHist", "spHistBins", "chkHistFit", "btnHist"):
                self._safe_remove_widget(getattr(self, name, None))
        except Exception:
            pass
        # Remove 'Histogram' label if present
        try:
            from PySide6.QtWidgets import QLabel
            for lbl in plot_widget.findChildren(QLabel):
                try:
                    t = str(lbl.text()).strip().lower()
                    if t.startswith("histogram") or t == "bins" or t == "คอลัมน์" or t == "คอลัมน์:" or t == "columns":
                        self._safe_remove_widget(lbl)
                except Exception:
                    pass
        except Exception:
            pass
        # Compact layout by removing invisible items and empty layouts
        try:
            lay = plot_widget.layout()
            def _prune(l):
                if l is None: return
                for i in reversed(range(l.count())):
                    it = l.itemAt(i)
                    # Remove nested layouts first
                    try:
                        child_lay = it.layout() if hasattr(it, 'layout') else None
                    except Exception:
                        child_lay = None
                    if child_lay is not None:
                        _prune(child_lay)
                        # if child layout empty (no visible widgets)
                        empty = True
                        for j in range(child_lay.count()):
                            it2 = child_lay.itemAt(j)
                            w2 = it2.widget() if hasattr(it2, 'widget') else None
                            if w2 is not None and w2.isVisible():
                                empty = False; break
                        if empty:
                            l.takeAt(i)
                            try:
                                child_lay.deleteLater()
                            except Exception:
                                pass
                        continue
                    # Remove hidden widgets
                    w = it.widget() if hasattr(it, 'widget') else None
                    if w is not None and not w.isVisible():
                        l.takeAt(i)
                return
            if lay is not None:
                _prune(lay)
        except Exception:
            pass

        # Make all buttons in Plot tab compact (avoid full-width expansion)
        try:
            from PySide6.QtWidgets import QPushButton
            btns = plot_widget.findChildren(QPushButton)
            for b in btns:
                try:
                    b.setMaximumWidth(220)
                    from PySide6.QtWidgets import QSizePolicy
                    b.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                except Exception:
                    pass
        except Exception:
            pass

        # Make input widgets (combos/spins/edits/labels) compact and left-aligned
        try:
            from PySide6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QLabel
            from PySide6.QtCore import Qt
            MAX_W = 260
            # Direct children alignment to left
            def _align_left(w):
                try:
                    plot_widget.layout().setAlignment(w, Qt.AlignLeft)
                except Exception:
                    pass
            for w in plot_widget.findChildren(QComboBox):
                try:
                    w.setMaximumWidth(MAX_W); _align_left(w)
                except Exception:
                    pass
            for w in plot_widget.findChildren((QSpinBox, QDoubleSpinBox)):
                try:
                    w.setMaximumWidth(100); _align_left(w)
                except Exception:
                    pass
            for w in plot_widget.findChildren(QLineEdit):
                try:
                    w.setMaximumWidth(MAX_W); _align_left(w)
                except Exception:
                    pass
            # Keep labels from stretching across the panel
            for w in plot_widget.findChildren(QLabel):
                try:
                    if w.text().strip():
                        w.setMaximumWidth(MAX_W)
                except Exception:
                    pass
        except Exception:
            pass

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
        # Auto-select dataset from staging if _df is not set yet
        if self._df is None:
            try:
                if hasattr(self, 'lstFiles') and hasattr(self, '_datasets'):
                    item = self.lstFiles.currentItem()
                    if item is not None:
                        data = self._datasets.get(item.text())
                        if data and isinstance(data.get('df'), pd.DataFrame):
                            self._df = data['df'].copy()
                            self._current_path = data.get('path')
            except Exception:
                pass
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
            # Also update toolbar histogram combo if available
            try:
                if hasattr(self, 'tbCbHist') and self.tbCbHist is not None:
                    self.tbCbHist.clear(); self.tbCbHist.addItems(cols)
            except Exception:
                pass
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
        print("Debug: _get_xy() called")
        if self._df is None:
            print("Debug: _get_xy() - no DataFrame (_df is None)")
            QMessageBox.warning(self, "ยังไม่มีข้อมูล", "โปรดเปิดไฟล์/เลือกตัวแปร แล้วกด 'โหลดคอลัมน์'"); return None, None
        print(f"Debug: _get_xy() - DataFrame shape: {self._df.shape}")
        
        if self.cbX.count() == 0 or self.cbY.count() == 0:
            print(f"Debug: _get_xy() - cbX count: {self.cbX.count()}, cbY count: {self.cbY.count()}")
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
            
            # เพิ่มการตรวจสอบข้อมูลเพิ่มเติม
            if len(x) > 0 and len(y) > 0:
                print(f"Debug: Data range - X: {x.min()} to {x.max()}, Y: {y.min():.6f} to {y.max():.6f}")
                
                # ตรวจสอบว่า X เป็น datetime หรือไม่ก่อนคำนวณ range
                try:
                    if pd.api.types.is_datetime64_any_dtype(x) or isinstance(x[0], str):
                        print(f"Debug: X is datetime/string, skipping range calculation")
                    else:
                        print(f"Debug: Data variation - X range: {x.max() - x.min()}, Y range: {y.max() - y.min():.6f}")
                except Exception as e:
                    print(f"Debug: Error calculating X range: {e}")
                    
                if len(y) > 1:
                    y_diff = np.diff(y)
                    print(f"Debug: Y variation - min diff: {y_diff.min():.6f}, max diff: {y_diff.max():.6f}, std: {y_diff.std():.6f}")
            
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
                
                # Convert datetime to numeric with proper scaling
                try:
                    # Convert to pandas datetime first to ensure proper handling
                    x_dt = pd.to_datetime(x)
                    # Use relative time from the first point
                    x_rel = (x_dt - x_dt[0]).dt.total_seconds()
                    x = x_rel.values
                    print(f"Debug: Converted datetime X to relative seconds - range: {x.min():.3f} to {x.max():.3f}")
                except Exception as e:
                    print(f"Debug: Failed to convert datetime to relative seconds: {e}")
                    # Fallback: use array index as X (like Chart Gallery does when no time column)
                    try:
                        x = np.arange(len(x))
                        print(f"Debug: Fallback to array index as X - range: {x.min()} to {x.max()}")
                    except Exception as e2:
                        print(f"Debug: All datetime conversion methods failed: {e2}")
                        # Keep original datetime format
            else:
                # Check if X is datetime string first
                try:
                    # Try to convert to datetime first
                    x_dt = pd.to_datetime(x, errors="coerce")
                    if x_dt.notna().sum() > 0:
                        print("Debug: X is datetime string, converting to relative seconds")
                        # Convert to relative time like datetime case
                        x_rel = (x_dt - x_dt[0]).total_seconds()
                        x = x_rel.values
                        print(f"Debug: Converted datetime string X to relative seconds - range: {x.min():.3f} to {x.max():.3f}")
                    else:
                        raise ValueError("Not a valid datetime string")
                except Exception as e:
                    print(f"Debug: X is not datetime string, trying numeric conversion: {e}")
                    # Convert X to numeric with error handling
                    try: 
                        x_original_count = len(x)
                        x = pd.to_numeric(x, errors="coerce")
                        x_nan_count = pd.isna(x).sum()
                        print(f"Debug: X conversion - original: {x_original_count}, NaN after conversion: {x_nan_count}, valid: {x_original_count - x_nan_count}")
                    except Exception as e2:
                        print(f"X column conversion error: {e2}")
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
            
            # ตรวจสอบข้อมูล Y สำหรับค่าผิดปกติ
            if len(y) > 0:
                y_mean = np.mean(y)
                y_std = np.std(y)
                y_median = np.median(y)
                
                print(f"Debug: Y statistics - mean: {y_mean:.6f}, std: {y_std:.6f}, median: {y_median:.6f}")
                
                # ตรวจสอบค่าผิดปกติ (outliers)
                q1, q3 = np.percentile(y, [25, 75])
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                outliers = np.where((y < lower_bound) | (y > upper_bound))[0]
                if len(outliers) > 0:
                    print(f"Debug: Found {len(outliers)} outliers in Y data (indices: {outliers[:10]}{'...' if len(outliers) > 10 else ''})")
                    print(f"Debug: Outlier percentage: {len(outliers)/len(y)*100:.2f}%")
                    
                    # แสดงข้อมูล outlier บางส่วน
                    outlier_values = y[outliers[:5]]
                    print(f"Debug: Sample outlier values: {outlier_values}")
                else:
                    print("Debug: No outliers detected in Y data")
            
            # Skip downsampling for now to test if datetime conversion is the real issue
            # max_points = 2000
            # if len(x) > max_points:
            #     print(f"Debug: Data too dense ({len(x)} points), downsampling to {max_points} points")
            #     idx = np.linspace(0, len(x) - 1, max_points).astype(int)
            #     x = x[idx]
            #     y = y[idx]
            #     print(f"Debug: After downsampling - X: {len(x)}, Y: {len(y)}")
            
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
        print("Debug: plot_line() called - button clicked!")
        x, y = self._get_xy()
        if x is None: 
            print("Debug: plot_line() - no data to plot (x is None)")
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

            plot_kwargs = {'linewidth': lw}
            if marker:
                plot_kwargs['marker'] = marker
            meta = self._build_layer_meta('line', label, plot_kwargs, source='plot_line')

            # Plot to selected tabs — overlay or replace
            if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.OVERLAY:
                self.tabs.add_series_to_tabs(
                    selected_tab_ids, x, y,
                    label=label, style="line", meta=meta, **plot_kwargs
                )
            else:
                self.tabs.plot_to_tabs(
                    selected_tab_ids, x, y,
                    label=label, style="line", meta=meta, **plot_kwargs
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

            plot_kwargs = {'s': size}
            meta = self._build_layer_meta('scatter', label, plot_kwargs, source='plot_scatter')

            # Plot to selected tabs — overlay or replace
            if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.OVERLAY:
                self.tabs.add_series_to_tabs(
                    selected_tab_ids, x, y,
                    label=label, style="scatter", meta=meta, **plot_kwargs
                )
            else:
                self.tabs.plot_to_tabs(
                    selected_tab_ids, x, y,
                    label=label, style="scatter", meta=meta, **plot_kwargs
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
                try:
                    tab.draw()
                except Exception:
                    pass
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

    def _get_dataset_name_for_path(self, path: Optional[str]) -> str:
        if not path:
            return ""
        datasets = getattr(self, '_datasets', {}) if hasattr(self, '_datasets') else {}
        if isinstance(datasets, dict):
            for name, info in datasets.items():
                if isinstance(info, dict) and info.get('path') == path:
                    return name or ""
        return ""

    def _build_layer_meta(self, style: str, label: str, extra_kwargs: Optional[Dict[str, Any]] = None, source: str = 'manual') -> Dict[str, Any]:
        meta = {
            'style': style,
            'label': label,
            'dataset_path': getattr(self, '_current_path', '') or '',
            'dataset_name': self._get_dataset_name_for_path(getattr(self, '_current_path', '')),
            'x_column': self.cbX.currentText() if hasattr(self, 'cbX') else '',
            'y_column': self.cbY.currentText() if hasattr(self, 'cbY') else '',
            'source': source,
        }
        if extra_kwargs:
            cleaned = {k: v for k, v in extra_kwargs.items() if v is not None}
            if cleaned:
                meta['style_kwargs'] = cleaned
        return meta

    def _load_dataset_from_path(self, path: str, name: Optional[str] = None):
        try:
            ext = os.path.splitext(path)[1].lower()
        except Exception:
            return None
        df = None
        try:
            if ext in {'.csv', '.tsv', '.txt', '.xlsx'}:
                df, _ = load_tabular(path, ext)
            elif ext in {'.nc', '.cdf'}:
                df = load_cdf_nc_on_demand(self, path)
        except Exception as exc:
            logger.warning('Failed to load dataset %s: %s', path, exc)
            df = None
        if df is None or getattr(df, 'empty', False):
            return None
        dataset_name = name or f"{os.path.basename(path)}"
        try:
            self._stage_insert(dataset_name, df, path)
        except Exception:
            logger.warning('Failed to stage dataset during restore: %s', dataset_name, exc_info=True)
            return None
        return dataset_name

    def add_line_overlay(self):
        print("Debug: add_line_overlay() called")
        x, y = self._get_xy()
        if x is None:
            print("Debug: add_line_overlay() - no data")
            return
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, "No Tab", "Please create/select a graph tab first"); return
        lw = self.spLineWidth.value(); marker = "o" if self.chkMarker.isChecked() else None
        label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
        plot_kwargs = {'linewidth': lw}
        if marker:
            plot_kwargs['marker'] = marker
        meta = self._build_layer_meta('line', label, plot_kwargs, source='add_line_overlay')
        try:
            self.tabs.add_series_to_tabs([current_tab_id], x, y, label=label, style="line", meta=meta, **plot_kwargs)
            try:
                tab = self.tabs.tabs[current_tab_id]; ax = tab.get_axes()
                ax.set_xlabel(self.cbX.currentText()); ax.set_ylabel(self.cbY.currentText())
                beautify_axes(ax, x_is_datetime=self._is_datetime_column(self.cbX.currentText()))
                tab.draw()
            except Exception:
                pass
            self.statusBar().showMessage("Added line series (overlay)")
        except Exception as e:
            print(f"Debug: add_line_overlay() failed: {e}")

    def add_scatter_overlay(self):
        print("Debug: add_scatter_overlay() called")
        x, y = self._get_xy()
        if x is None:
            print("Debug: add_scatter_overlay() - no data")
            return
        current_tab_id = self.tabs.get_current_tab_id()
        if not current_tab_id:
            QMessageBox.warning(self, "No Tab", "Please create/select a graph tab first"); return
        size = self.spLineWidth.value() * 5
        label = f"{self.cbY.currentText()} vs {self.cbX.currentText()}"
        plot_kwargs = {'s': size}
        meta = self._build_layer_meta('scatter', label, plot_kwargs, source='add_scatter_overlay')
        try:
            self.tabs.add_series_to_tabs([current_tab_id], x, y, label=label, style="scatter", meta=meta, **plot_kwargs)
            try:
                tab = self.tabs.tabs[current_tab_id]; ax = tab.get_axes()
                ax.set_xlabel(self.cbX.currentText()); ax.set_ylabel(self.cbY.currentText())
                beautify_axes(ax, x_is_datetime=self._is_datetime_column(self.cbX.currentText()))
                tab.draw()
            except Exception:
                pass
            self.statusBar().showMessage("Added scatter series (overlay)")
        except Exception as e:
            print(f"Debug: add_scatter_overlay() failed: {e}")

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
            
        label = title or ylabel or "Bar Series"
        meta = self._build_layer_meta('bar', label, {}, source='plot_bar')
        # Plot to selected tabs
        self.tabs.plot_to_tabs(
            selected_tab_ids, x, y, 
            label=label, style="bar", meta=meta
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

    def open_nonlinear_fit_dialog(self):
        """เปิด NonlinearFitDialog พร้อม DataFrame ปัจจุบัน"""
        df = self.get_current_dataframe()
        if df is None or df.empty:
            QMessageBox.information(self, "ไม่มีข้อมูล", "กรุณาโหลดข้อมูลก่อนทำการฟิต")
            return
        try:
            dlg = NonlinearFitDialog(self, df)
            dlg.exec()
        except Exception as exc:
            QMessageBox.critical(self, "ข้อผิดพลาด", f"เปิด Nonlinear Curve Fit ไม่สำเร็จ:\n{exc}")

    def plot_fit_result_on_active_tab(self, x: np.ndarray, res: FitResult):
        """วาดผลการฟิตและช่วงความเชื่อมั่นลงบนกราฟปัจจุบัน"""
        tab = self.tabs.currentWidget() if hasattr(self, 'tabs') else None
        if tab is None or not hasattr(tab, 'get_axes'):
            return
        try:
            ax = tab.get_axes()
        except Exception:
            ax = None
        if ax is None:
            return
        x_arr = np.asarray(x, dtype=float)
        y_fit = np.asarray(res.yfit, dtype=float) if res.yfit is not None else np.array([])
        if x_arr.size == 0 or y_fit.size == 0:
            return
        if x_arr.size != y_fit.size:
            length = min(x_arr.size, y_fit.size)
            if length <= 0:
                return
            x_arr = x_arr[:length]
            y_fit = y_fit[:length]
        order = np.argsort(x_arr)
        xs = x_arr[order]
        ys = y_fit[order]
        line, = ax.plot(xs, ys, linewidth=2.0, label="Fit")
        band = None
        if res.ci95_lower is not None and res.ci95_upper is not None:
            lo = np.asarray(res.ci95_lower, dtype=float)
            hi = np.asarray(res.ci95_upper, dtype=float)
            if lo.size == xs.size and hi.size == xs.size:
                lo_ord = lo[order]
                hi_ord = hi[order]
                band = ax.fill_between(xs, lo_ord, hi_ord, alpha=0.2, label="95% CI")
        ax.legend(loc="best")
        ax.figure.canvas.draw_idle()
        try:
            artists = [line]
            if band is not None:
                artists.append(band)
            tab.register_layer(artists, "Nonlinear Fit", 'line', meta={'kind': 'nonlinear_fit', 'success': res.success, 'message': res.message})
        except Exception:
            pass

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
        try:
            dialog.setWindowModality(Qt.NonModal)
            dialog.setAttribute(Qt.WA_DeleteOnClose, True)
            dialog.resize(720, 480)
        except Exception:
            pass
        dialog.show()
    
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
            try:
                if getattr(self, 'plot_mode', PlotMode.OVERLAY) == PlotMode.REPLACE:
                    self.canvas.ax.clear()
            except Exception:
                pass
            
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
                F = self._current_spectrogram['F']
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
        lower = min(xmin, xmax)
        upper = max(xmin, xmax)
        use_datetime = False
        x_dt = None
        try:
            if pd.api.types.is_datetime64_any_dtype(xser):
                use_datetime = True
                x_dt = pd.to_datetime(xser, errors="coerce")
            else:
                if pd.api.types.is_object_dtype(xser) or pd.api.types.is_string_dtype(xser):
                    candidate = pd.to_datetime(xser, errors="coerce")
                    if candidate.notna().any():
                        x_dt = candidate
                        use_datetime = True
            if use_datetime and x_dt is not None:
                import matplotlib.dates as mdates
                valid = x_dt.notna() if hasattr(x_dt, "notna") else ~pd.isna(x_dt)
                if np.any(valid):
                    valid_mask = valid.to_numpy() if hasattr(valid, "to_numpy") else np.asarray(valid)
                    xnum = np.full(len(xser), np.nan, dtype=float)
                    dt_values = x_dt[valid] if hasattr(x_dt, "__getitem__") else np.asarray(x_dt)[valid_mask]
                    dt_series = pd.Series(dt_values)
                    dt_series = pd.to_datetime(dt_series, errors="coerce")
                    xnum[valid_mask] = mdates.date2num(dt_series.to_numpy(dtype="datetime64[ns]"))
                    mask = np.isfinite(xnum) & (xnum >= lower) & (xnum <= upper)
                    if mask.any():
                        df_view = self._df.loc[mask].copy()
                else:
                    use_datetime = False
            if df_view is None:
                xnum = pd.to_numeric(xser, errors="coerce")
                xarr = xnum.to_numpy() if hasattr(xnum, "to_numpy") else np.asarray(xnum)
                mask = np.isfinite(xarr) & (xarr >= lower) & (xarr <= upper)
                if mask.any():
                    df_view = self._df.loc[mask].copy()
        except Exception:
            xnum = pd.to_numeric(xser, errors="coerce")
            xarr = xnum.to_numpy() if hasattr(xnum, "to_numpy") else np.asarray(xnum)
            mask = np.isfinite(xarr) & (xarr >= lower) & (xarr <= upper)
            df_view = self._df.loc[mask].copy()

        if df_view is None or df_view.empty:
            fallback_df = None
            fallback_use_datetime = use_datetime
            try:
                import matplotlib.dates as mdates

                def _line_to_numeric(values):
                    arr = np.asarray(values)
                    if arr.size == 0:
                        return arr.astype(float), False
                    if np.issubdtype(arr.dtype, np.number):
                        return arr.astype(float), False
                    numeric = pd.to_numeric(arr, errors="coerce")
                    if hasattr(numeric, "to_numpy"):
                        numeric_arr = numeric.to_numpy()
                    else:
                        numeric_arr = np.asarray(numeric, dtype=float)
                    if numeric_arr.size and np.isfinite(numeric_arr).any():
                        return numeric_arr, False
                    dt_series = pd.Series(pd.to_datetime(arr, errors="coerce"))
                    valid = dt_series.notna()
                    if not valid.any():
                        return numeric_arr, False
                    numeric_arr = np.full(len(dt_series), np.nan, dtype=float)
                    numeric_arr[valid.to_numpy()] = mdates.date2num(dt_series[valid].to_numpy(dtype="datetime64[ns]"))
                    return numeric_arr, True

                for i, ln in enumerate(ax.get_lines()):
                    x_raw = ln.get_xdata(orig=False)
                    y_raw = ln.get_ydata(orig=False)
                    x_numeric, line_is_datetime = _line_to_numeric(x_raw)
                    if x_numeric.size == 0:
                        continue
                    y_arr = np.asarray(y_raw)
                    if y_arr.size == 0:
                        continue
                    mask_line = np.isfinite(x_numeric) & (x_numeric >= lower) & (x_numeric <= upper)
                    if not mask_line.any():
                        continue
                    x_filtered = x_numeric[mask_line]
                    y_filtered = y_arr[mask_line]
                    label = ln.get_label() if ln.get_label() and not ln.get_label().startswith('_') else f'y{i+1}'
                    line_df = pd.DataFrame({"__x__": x_filtered, label: y_filtered})
                    fallback_df = line_df if fallback_df is None else pd.merge(fallback_df, line_df, on="__x__", how="outer")
                    fallback_use_datetime = fallback_use_datetime or line_is_datetime

                if fallback_df is not None and not fallback_df.empty:
                    fallback_df.sort_values("__x__", inplace=True)
                    fallback_df.reset_index(drop=True, inplace=True)
                    if fallback_use_datetime:
                        dt_series = pd.Series(pd.to_datetime(mdates.num2date(fallback_df["__x__"].to_numpy())))
                        try:
                            dt_series = dt_series.dt.tz_localize(None)
                        except (TypeError, AttributeError, ValueError):
                            pass
                        fallback_df[xcol] = dt_series.to_numpy()
                    else:
                        fallback_df[xcol] = fallback_df["__x__"]
                    ordered_cols = [xcol] + [c for c in fallback_df.columns if c not in {"__x__", xcol}]
                    df_view = fallback_df[ordered_cols]
            except Exception:
                pass

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
            tab = self.tabs.tabs[current_tab_id]
            tab.clear()
            try:
                ax = tab.get_axes()
                ax.cla()
                tab.draw()
            except Exception:
                pass
            try:
                self._mount_layer_manager()
            except Exception:
                pass
            self.statusBar().showMessage("ล้างกราฟแล้ว")
        
    def _reset_view(self):
        """Reset view for current tab"""
        current_tab_id = self.tabs.get_current_tab_id()
        if current_tab_id and current_tab_id in self.tabs.tabs:
            tab = self.tabs.tabs[current_tab_id]
            tab.get_axes().set_xlim(auto=True)
            tab.get_axes().set_ylim(auto=True)
            tab.draw()
            
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            session_store.save_session(self)
        except Exception:
            logger.warning('Failed to save session on close', exc_info=True)
        super().closeEvent(event)

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
            
        self._update_3d_controls_state()

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
            self.canvas.fig.savefig(path, dpi=300, bbox_inches="tight")
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







