from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from annotations import AnnotationManager
from context_menu import ContextMenuManager
from core.plot_data import (
    axis_uses_dates,
    clamp_date_limits,
    is_invalid_plot_value,
    prepare_plot_data,
    reset_numeric_axis,
    to_sequence_for_plot,
)
from toolbar import PlotNavigationToolbar
from widgets.layer_manager import LayerManagerWidget


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        # Tight layout applied by the draw itself (deferred layout engine) so
        # we don't pay a separate full render for tight_layout() on every plot.
        try:
            self.fig.set_layout_engine("tight")
        except Exception:
            pass
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        try:
            import matplotlib as mpl

            fig_fc = mpl.rcParams.get("figure.facecolor", "#1e2126") or "#1e2126"
            ax_fc = mpl.rcParams.get("axes.facecolor", "#1e2126") or "#1e2126"
            grid_col = mpl.rcParams.get("grid.color", "#3a3f44") or "#3a3f44"
            grid_alpha = float(mpl.rcParams.get("grid.alpha", 0.3))
            grid_ls = mpl.rcParams.get("grid.linestyle", "-") or "-"
            text_col = mpl.rcParams.get("text.color", "#e6e6e6") or "#e6e6e6"

            self.fig.patch.set_facecolor(fig_fc)
            self.ax.set_facecolor(ax_fc)
            for sp in self.ax.spines.values():
                sp.set_color(mpl.rcParams.get("axes.edgecolor", "#3a3f44"))
            self.ax.tick_params(colors=text_col)
            self.ax.yaxis.label.set_color(text_col)
            self.ax.xaxis.label.set_color(text_col)
            if bool(mpl.rcParams.get("axes.grid", True)):
                self.ax.grid(True, alpha=grid_alpha, linestyle=grid_ls, color=grid_col)
        except Exception:
            pass
        # layout handled by the 'tight' layout engine at draw time

    def draw(self):
        try:
            super().draw()
        except Exception:
            try:
                self.fig.canvas.draw()
            except Exception:
                try:
                    self.fig.canvas.draw_idle()
                except Exception:
                    import traceback
                    traceback.print_exc()

    def clear(self):
        try:
            import matplotlib

            current_facecolor = matplotlib.rcParams.get("figure.facecolor", "#1e2126")
            current_axes_facecolor = matplotlib.rcParams.get("axes.facecolor", "#1e2126")
            self.fig.clf()
            self.ax = self.fig.add_subplot(111)
            self.fig.patch.set_facecolor(current_facecolor)
            self.ax.set_facecolor(current_axes_facecolor)
            self.fig.tight_layout()
            try:
                self.draw()
            except Exception:
                self.fig.canvas.draw()
        except Exception:
            try:
                import matplotlib

                self.fig = Figure(figsize=(6, 4), dpi=100)
                self.ax = self.fig.add_subplot(111)
                self.fig.patch.set_facecolor(matplotlib.rcParams.get("figure.facecolor", "#1e2126"))
                self.ax.set_facecolor(matplotlib.rcParams.get("axes.facecolor", "#1e2126"))
                self.fig.tight_layout()
                self.draw()
            except Exception:
                pass


class GraphTab(QWidget):
    def __init__(self, tab_id, name="Graph", parent=None):
        super().__init__(parent)
        self.tab_id = tab_id
        self.name = name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.canvas = PlotCanvas(self)
        self.toolbar = PlotNavigationToolbar(self.canvas, self)
        layout.addWidget(self.canvas)
        layout.addWidget(self.toolbar)
        try:
            self.toolbar.setVisible(False)
        except Exception:
            pass
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.annotation_manager = AnnotationManager(self.canvas.fig, self.canvas.ax, self)
        self.layer_manager = LayerManagerWidget(self)
        self.layer_manager.layerVisibilityChanged.connect(self._on_layer_visibility_changed)
        self.layer_manager.layerRenameRequested.connect(self._on_layer_rename)
        self.layer_manager.layerRemoveRequested.connect(self._on_layer_remove)
        self.layer_manager.layerStyleRequested.connect(self._on_layer_style_request)
        self.layers: Dict[str, Dict[str, Any]] = {}
        self._layer_id_seq = itertools.count(1)

        try:
            mw = self.parent().parent() if hasattr(self.parent(), "parent") else None
            self.ctx_menu = ContextMenuManager(
                self.canvas,
                self.canvas.ax,
                main=mw,
                annotation_mgr=self.annotation_manager,
                peak_mgr=getattr(mw, "peaks", None) if mw else None,
                xcorr_mgr=getattr(mw, "crosscorr", None) if mw else None,
            )
        except Exception:
            self.ctx_menu = None

    def clear(self):
        self.canvas.clear()
        self.annotation_manager = AnnotationManager(self.canvas.fig, self.canvas.ax, self)

    def get_axes(self):
        return self.canvas.ax

    def get_figure(self):
        return self.canvas.fig

    def draw(self):
        try:
            self.canvas.draw()
        except Exception:
            try:
                self.canvas.fig.canvas.draw()
            except Exception:
                pass

    def clear_layers(self) -> None:
        for info in self.layers.values():
            for artist in info.get("artists", []):
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
            "artists": list(artists),
            "label": label,
            "style": style,
            "meta": dict(meta or {}),
            "kwargs": dict(kwargs or {}),
            "visible": visible,
        }
        self.layers[layer_id] = info
        self.layer_manager.add_layer(layer_id, label, style, visible=visible)
        return layer_id

    def serialize_layers(self) -> List[Dict[str, Any]]:
        data = []
        for layer_id, info in self.layers.items():
            entry = {
                "id": layer_id,
                "label": info.get("label", ""),
                "style": info.get("style", "line"),
                "visible": info.get("visible", True),
                "meta": info.get("meta", {}),
                "kwargs": info.get("kwargs", {}),
                "data": {},
            }
            artists = info.get("artists", [])
            if artists:
                artist = artists[0]
                try:
                    entry["data"] = {
                        "x": self._to_serializable_array(artist.get_xdata()),
                        "y": self._to_serializable_array(artist.get_ydata()),
                    }
                except Exception:
                    try:
                        offsets = artist.get_offsets()
                        entry["data"] = {
                            "x": self._to_serializable_array([pt[0] for pt in offsets]),
                            "y": self._to_serializable_array([pt[1] for pt in offsets]),
                        }
                    except Exception:
                        entry["data"] = {}
            data.append(entry)
        return data

    def restore_layers(self, layers: List[Dict[str, Any]], main_window) -> None:
        try:
            parent_manager = self.parent()
        except Exception:
            parent_manager = None
        if not parent_manager or not hasattr(parent_manager, "add_series_to_tabs"):
            return
        self.clear()
        self.clear_layers()
        for layer in layers:
            label = layer.get("label", "")
            style = layer.get("style", "line")
            kwargs = dict(layer.get("kwargs", {}))
            meta = dict(layer.get("meta", {}))
            data = layer.get("data", {}) or {}
            x = data.get("x")
            y = data.get("y")
            if (not x or not y) and main_window is not None:
                df = main_window.get_dataframe_for_layer(meta)
                if df is not None:
                    x_col = meta.get("x_column")
                    y_col = meta.get("y_column")
                    if x_col in df.columns and y_col in df.columns:
                        x = df[x_col].tolist()
                        y = df[y_col].tolist()
            if x is None or y is None:
                continue
            created = parent_manager.add_series_to_tabs([self.tab_id], x, y, label=label, style=style, meta=meta, **kwargs)
            if not layer.get("visible", True) and created:
                for tab_id, new_id in created:
                    if tab_id == self.tab_id and new_id:
                        self.layer_manager.update_layer_visibility(new_id, False)
                        self._set_layer_visibility(new_id, False, refresh=False)
        self.canvas.draw_idle()

    @staticmethod
    def _to_serializable_array(data):
        try:
            import numpy as np

            arr = np.asarray(data)
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
        for artist in info.get("artists", []):
            try:
                artist.set_visible(visible)
            except Exception:
                pass
        info["visible"] = visible
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
                if lbl and not str(lbl).startswith("_") and getattr(h, "get_visible", lambda: True)()
            ]
            if pairs:
                h, l = zip(*pairs)
                ax.legend(h, l, loc="best")
        except Exception:
            pass

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        self._set_layer_visibility(layer_id, visible)

    def _on_layer_rename(self, layer_id: str, new_label: str) -> None:
        info = self.layers.get(layer_id)
        if not info:
            return
        info["label"] = new_label
        info.setdefault("meta", {})
        info["meta"]["label"] = new_label
        for artist in info.get("artists", []):
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
        for artist in info.get("artists", []):
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
        if not info or info.get("style") != "line":
            return
        artists = [a for a in info.get("artists", []) if hasattr(a, "set_color")]
        if not artists:
            return
        info.setdefault("kwargs", {})
        info.setdefault("meta", {})
        style_meta = dict(info["meta"].get("style_kwargs", {}))
        color = self.layer_manager.prompt_color()
        if color and getattr(color, "isValid", lambda: False)():
            color_name = color.name()
            for artist in artists:
                try:
                    artist.set_color(color_name)
                except Exception:
                    pass
            info["kwargs"]["color"] = color_name
            style_meta["color"] = color_name
        current_width = artists[0].get_linewidth() if artists else 1.0
        width, ok = QInputDialog.getDouble(self, "Line Width", "Width:", float(current_width), 0.1, 50.0, 2)
        if ok:
            for artist in artists:
                try:
                    artist.set_linewidth(width)
                except Exception:
                    pass
            info["kwargs"]["linewidth"] = float(width)
            style_meta["linewidth"] = float(width)
        if style_meta:
            info["meta"]["style_kwargs"] = style_meta
        self._refresh_legend()
        try:
            self.canvas.draw_idle()
        except Exception:
            pass


class TabManager(QTabWidget):
    tabCreated = Signal(str)
    tabRemoved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab_counter = 0
        self.tabs = {}
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setAcceptDrops(False)
        try:
            self.setUsesScrollButtons(True)
            self.setDocumentMode(True)
            tb = self.tabBar()
            tb.setElideMode(Qt.ElideRight)
            tb.setExpanding(False)
        except Exception:
            pass
        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabBar().tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.add_tab("Graph 1")

    def add_tab(self, name=None):
        self.tab_counter += 1
        if name is None:
            name = f"Graph {self.tab_counter}"
        tab_id = f"tab_{self.tab_counter}"
        graph_tab = GraphTab(tab_id, name, self)
        index = self.addTab(graph_tab, name)
        self.tabs[tab_id] = graph_tab
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
        if self.count() <= 1:
            return
        tab_widget = self.widget(index)
        tab_id = None
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
        self._rename_tab(index)

    def _on_context_menu(self, position):
        tab_bar = self.tabBar()
        index = tab_bar.tabAt(position)
        if index >= 0:
            menu = QMenu(self)
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self._rename_tab(index))
            menu.exec(self.mapToGlobal(position))

    def _rename_tab(self, index):
        current_name = self.tabText(index)
        new_name, ok = QInputDialog.getText(self, "Rename Tab", "Enter new tab name:", text=current_name)
        if ok and new_name.strip():
            self.setTabText(index, new_name.strip())
            tab_widget = self.widget(index)
            if hasattr(tab_widget, "name"):
                tab_widget.name = new_name.strip()

    def get_current_tab_id(self):
        current_widget = self.currentWidget()
        for tab_id, tab in self.tabs.items():
            if tab == current_widget:
                return tab_id
        return None

    def get_open_tabs(self):
        result = []
        for i in range(self.count()):
            tab_widget = self.widget(i)
            tab_name = self.tabText(i)
            for tab_id, tab in self.tabs.items():
                if tab == tab_widget:
                    result.append((tab_id, tab_name))
                    break
        return result

    def plot_to_tabs(self, tab_ids, x, y, label="", style="line", meta: Optional[Dict[str, Any]] = None, **kwargs):
        created = []
        base_kwargs = dict(kwargs)
        for tab_id in tab_ids:
            if tab_id not in self.tabs:
                continue
            tab = self.tabs[tab_id]
            ax = tab.get_axes()
            try:
                mw = self.parent() if hasattr(self, "parent") else None
                mode = getattr(mw, "plot_mode", None)
            except Exception:
                mode = None
            overlay_mode = mode is not None and not str(mode).endswith("REPLACE")
            if overlay_mode:
                created.extend(self.add_series_to_tabs([tab_id], x, y, label=label, style=style, meta=meta, **kwargs))
                continue
            tab.clear_layers()
            ax.clear()
            local_kwargs = dict(base_kwargs)
            artists = []
            auto_label = label
            if not auto_label:
                try:
                    auto_label = getattr(tab, "name", "Series")
                except Exception:
                    auto_label = "Series"
            x_vals, y_vals, x_is_datetime = prepare_plot_data(x, y)
            try:
                if style == "histogram":
                    hist_source = []
                    for val in to_sequence_for_plot(y):
                        if is_invalid_plot_value(val):
                            continue
                        try:
                            hist_source.append(float(val))
                        except Exception:
                            continue
                    if not hist_source:
                        continue
                    y_vals = hist_source
                    x_vals = list(range(len(y_vals)))
                    x_is_datetime = False
                    hist = ax.hist(y_vals, label=auto_label, **local_kwargs)
                    artists = list(hist[2]) if len(hist) >= 3 else []
                else:
                    if not x_vals or not y_vals:
                        continue
                    if style == "line":
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                    elif style == "scatter":
                        artists = [ax.scatter(x_vals, y_vals, label=auto_label, **local_kwargs)]
                    elif style == "bar":
                        container = ax.bar(range(len(x_vals)), y_vals, label=auto_label, **local_kwargs)
                        artists = list(container)
                        ax.set_xticks(range(len(x_vals)))
                        try:
                            ax.set_xticklabels(list(map(str, x_vals)), rotation=45, ha="right")
                        except Exception:
                            pass
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if not x_is_datetime and axis_uses_dates(ax.xaxis):
                    reset_numeric_axis(ax)
                if x_is_datetime and len(x_vals) >= 2:
                    ax.set_xlim(min(x_vals), max(x_vals))
                clamp_date_limits(ax)
                ax.grid(True, alpha=0.3)
                if auto_label:
                    try:
                        ax.legend(loc="best")
                    except Exception:
                        pass
                try:
                    from processors import beautify_axes

                    beautify_axes(ax, x_is_datetime=x_is_datetime)
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    tab.canvas.fig.tight_layout()
                except Exception:
                    pass
                clamp_date_limits(ax)
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
                layer_meta.setdefault("style", style)
                layer_meta.setdefault("label", auto_label)
                layer_id = tab.register_layer(artists, auto_label or label or "", style, meta=layer_meta, kwargs=local_kwargs)
                if layer_id:
                    created.append((tab_id, layer_id))
                    if hasattr(tab, "_refresh_legend"):
                        tab._refresh_legend()
            except Exception:
                pass
        return created

    def add_series_to_tabs(self, tab_ids, x, y, label: str = "", style: str = "line", meta: Optional[Dict[str, Any]] = None, **kwargs):
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
            x_vals, y_vals, x_is_datetime = prepare_plot_data(x, y)
            try:
                if style == "histogram":
                    hist_source = []
                    for val in to_sequence_for_plot(y):
                        if is_invalid_plot_value(val):
                            continue
                        try:
                            hist_source.append(float(val))
                        except Exception:
                            continue
                    if not hist_source:
                        continue
                    y_vals = hist_source
                    x_vals = list(range(len(y_vals)))
                    x_is_datetime = False
                    hist = ax.hist(y_vals, label=auto_label, **local_kwargs)
                    artists = list(hist[2]) if len(hist) >= 3 else []
                else:
                    if not x_vals or not y_vals:
                        continue
                    if style == "line":
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                    elif style == "scatter":
                        artists = [ax.scatter(x_vals, y_vals, label=auto_label, **local_kwargs)]
                    elif style == "bar":
                        container = ax.bar(range(len(x_vals)), y_vals, label=auto_label, **local_kwargs)
                        artists = list(container)
                        ax.set_xticks(range(len(x_vals)))
                        try:
                            ax.set_xticklabels(list(map(str, x_vals)), rotation=45, ha="right")
                        except Exception:
                            pass
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if not x_is_datetime and axis_uses_dates(ax.xaxis):
                    reset_numeric_axis(ax)
                if x_is_datetime and len(x_vals) >= 2:
                    ax.set_xlim(min(x_vals), max(x_vals))
                clamp_date_limits(ax)
                try:
                    handles, labels = ax.get_legend_handles_labels()
                    if any(lbl and not lbl.startswith("_") for lbl in labels):
                        ax.legend(loc="best")
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    from processors import beautify_axes

                    beautify_axes(ax, x_is_datetime=x_is_datetime)
                except Exception:
                    pass
                clamp_date_limits(ax)
                try:
                    tab.canvas.fig.tight_layout()
                except Exception:
                    pass
                clamp_date_limits(ax)
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
                layer_meta.setdefault("style", style)
                layer_meta.setdefault("label", auto_label)
                layer_id = tab.register_layer(artists, auto_label or label or "", style, meta=layer_meta, kwargs=local_kwargs)
                if layer_id:
                    created.append((tab_id, layer_id))
                    if hasattr(tab, "_refresh_legend"):
                        tab._refresh_legend()
            except Exception:
                pass
        return created

    def add_series_to_current_tab(self, x, y, label: str = "", style: str = "line", meta: Optional[Dict[str, Any]] = None, **kwargs):
        current_tab_id = self.get_current_tab_id()
        if not current_tab_id:
            return []
        return self.add_series_to_tabs([current_tab_id], x, y, label=label, style=style, meta=meta, **kwargs)


class CompactPlotPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlotPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self.btnLoadCols = QPushButton("Load Columns from Data")
        self.btnLoadCols.setMinimumHeight(32)
        self.btnLoadCols.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer.addWidget(self.btnLoadCols)

        # Narrow-panel friendly (lives in the left workflow card ②): labels sit
        # ABOVE full-width fields. The old QFormLayout squeezed label+combo
        # side-by-side, and fixed 28px heights clipped Thai vowels/tone marks.
        self.cbo_x = QComboBox()
        self.cbo_y = QComboBox()
        for cb in (self.cbo_x, self.cbo_y):
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(8)
            cb.setMinimumHeight(30)
            cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        outer.addWidget(QLabel("X axis"))
        outer.addWidget(self.cbo_x)
        outer.addWidget(QLabel("Y axis"))
        outer.addWidget(self.cbo_y)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 10)
        self.spin_width.setValue(2)
        self.spin_width.setMinimumHeight(30)
        self.spin_width.setMinimumWidth(64)

        width_row = QHBoxLayout()
        width_row.setContentsMargins(0, 0, 0, 0)
        width_row.setSpacing(6)
        width_row.addWidget(QLabel("Line width"))
        width_row.addWidget(self.spin_width)
        width_row.addStretch(1)
        outer.addLayout(width_row)

        self.chk_points = QCheckBox("Show markers")
        self.chk_points.setMinimumHeight(26)
        outer.addWidget(self.chk_points)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.btn_line = QPushButton("Line")
        self.btn_scatter = QPushButton("Scatter")
        self.btn_clear = QPushButton("Clear")
        self.btn_fit = QPushButton("Curve Fit…")
        for button in (self.btn_line, self.btn_scatter, self.btn_clear, self.btn_fit):
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid.addWidget(self.btn_line, 0, 0)
        grid.addWidget(self.btn_scatter, 0, 1)
        grid.addWidget(self.btn_clear, 1, 0)
        grid.addWidget(self.btn_fit, 1, 1)
        outer.addLayout(grid)

        self.setMaximumWidth(420)
        self.setStyleSheet(
            """
            QWidget#PlotPanel QComboBox, QWidget#PlotPanel QSpinBox {
                padding: 3px 8px; min-height: 26px; border-radius: 6px;
            }
            QWidget#PlotPanel QPushButton {
                padding: 5px 10px; min-height: 30px; border-radius: 8px;
            }
            QWidget#PlotPanel QLabel {
                padding-top: 2px;
            }
            QWidget#PlotPanel QPushButton#PlotPrimary {
                background: #4F9CF9; color: #ffffff; border: 1px solid #4F9CF9;
                font-weight: 600;
            }
            QWidget#PlotPanel QPushButton#PlotPrimary:hover {
                background: #5fa8fb; border-color: #5fa8fb;
            }
            """
        )
        # เน้นปุ่มพล็อตหลักให้เด่น (ขั้น ② ของ workflow)
        self.btn_line.setObjectName("PlotPrimary")
