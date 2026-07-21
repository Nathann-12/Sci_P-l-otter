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
from core.graph_format_history import GraphFormatHistory
from core.plot_data import (
    axis_uses_dates,
    clamp_date_limits,
    is_invalid_plot_value,
    prepare_plot_data,
    reset_numeric_axis,
    to_sequence_for_plot,
)
from core.render_optimization import (
    apply_line_lod,
    canvas_pixel_width,
    draw_bar_series,
    draw_scatter_series,
)
from toolbar import PlotNavigationToolbar
from widgets.layer_manager import LayerManagerWidget
from widgets.viewport_lod import ViewportLODController


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), dpi=100)
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
        try:
            self.fig.tight_layout()
        except Exception:
            pass

    def draw(self):
        try:
            super().draw()
        except Exception:
            # NOTE: self.fig.canvas IS self, so the old fallback
            # (self.fig.canvas.draw()/draw_idle()) recursed ~1000× and turned a
            # single bad axis into a multi-second hang. Never re-enter draw here;
            # just log. The caller is responsible for not putting invalid state
            # (e.g. a date locator on a numeric axis) on the axes.
            import logging
            logging.getLogger(__name__).debug("PlotCanvas.draw failed", exc_info=True)

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
            self.draw()
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
    renderStatusChanged = Signal(str)

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
        # Formatting history is graph-scoped. Annotation snapshots keep their
        # compact legacy storage, while the main window merges both histories
        # by a shared edit sequence for chronological Ctrl+Z/Ctrl+Y routing.
        self.graph_format_history = GraphFormatHistory(self)
        self.graph_undo_stack = self.graph_format_history.stack
        self.lod_controller = ViewportLODController(self)

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
        self.graph_format_history.clear()
        self.lod_controller.detach_axes()
        try:
            self.annotation_manager.dispose()
        except Exception:
            pass
        self.canvas.clear()
        self.annotation_manager = AnnotationManager(self.canvas.fig, self.canvas.ax, self)
        if self.ctx_menu is not None:
            self.ctx_menu.ann = self.annotation_manager
            try:
                self.ctx_menu._adopt_axes(self.canvas.ax)
            except Exception:
                pass

    def get_axes(self):
        return self.canvas.ax

    def get_figure(self):
        return self.canvas.fig

    def graph_format_transaction(self, label: str):
        """Return a context manager that records one formatting operation."""
        return self.graph_format_history.transaction(label)

    def capture_graph_format_state(self):
        """Capture the current in-memory formatting state for preview/commit."""
        return self.graph_format_history.capture()

    def restore_graph_format_state(self, state) -> None:
        """Restore a captured formatting state without recording recursion."""
        self.graph_format_history.restore(state)

    def record_applied_graph_format(self, label: str, before, after=None) -> bool:
        """Record an edit that the caller has already applied to this graph."""
        return self.graph_format_history.record_applied(label, before, after)

    def draw(self):
        try:
            self.canvas.draw()
        except Exception:
            try:
                self.canvas.fig.canvas.draw()
            except Exception:
                pass

    def export_render(self, pixel_width: int):
        """Return a context manager for resolution-aware export rendering."""
        return self.lod_controller.export_render(pixel_width)

    def closeEvent(self, event):
        try:
            self.lod_controller.shutdown()
        except Exception:
            pass
        try:
            self.annotation_manager.dispose()
        except Exception:
            pass
        super().closeEvent(event)

    def clear_layers(self) -> None:
        self.graph_format_history.clear()
        self.lod_controller.detach_axes()
        from matplotlib.lines import Line2D
        from core.plot_style import remove_line_decorations

        for info in self.layers.values():
            for artist in info.get("artists", []):
                try:
                    if isinstance(artist, Line2D):
                        remove_line_decorations(artist)
                    artist.remove()
                except Exception:
                    pass
        self.layers.clear()
        self.layer_manager.clear_layers()

    def register_layer(self, artists, label: str, style: str, meta: Optional[Dict[str, Any]] = None, kwargs: Optional[Dict[str, Any]] = None):
        if not artists:
            return None
        # A formatting snapshot deliberately excludes plotted x/y arrays.  A
        # topology change therefore starts a fresh, structurally safe history.
        self.graph_format_history.clear()
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
        self.lod_controller.attach_layer(layer_id)
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
                source_x = getattr(artist, "_sciplotter_x_values", None)
                source_y = getattr(artist, "_sciplotter_y_values", None)
                if source_x is not None and source_y is not None:
                    entry["data"] = {
                        "x": self._to_serializable_array(source_x),
                        "y": self._to_serializable_array(source_y),
                    }
                    data.append(entry)
                    continue
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
        parent_manager = None
        candidates = [
            getattr(main_window, "tabs", None),
            getattr(main_window, "mdi", None),
        ]
        try:
            candidates.append(self.parent())
        except Exception:
            pass
        for candidate in candidates:
            if callable(getattr(candidate, "add_series_to_tabs", None)):
                parent_manager = candidate
                break
        # GraphTab is wrapped by an MDI subwindow at runtime, so its immediate
        # parent is not the workspace manager.  Walk upward as a final fallback
        # for lightweight embeds/tests that do not pass a MainWindow.
        node = self
        seen = set()
        while parent_manager is None and node is not None and id(node) not in seen:
            seen.add(id(node))
            try:
                node = node.parent()
            except Exception:
                node = None
            if callable(getattr(node, "add_series_to_tabs", None)):
                parent_manager = node
                break
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
        from matplotlib.lines import Line2D
        from core.plot_style import set_line_decorations_visible

        for artist in info.get("artists", []):
            try:
                artist.set_visible(visible)
                if isinstance(artist, Line2D):
                    set_line_decorations_visible(artist, visible)
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
        legend = ax.get_legend()
        previous = None
        try:
            if legend is not None:
                from core.format_clipboard import _capture_legend

                previous = _capture_legend(ax)
        except Exception:
            previous = None
        try:
            handles, labels = ax.get_legend_handles_labels()

            def logical_handle_visible(handle) -> bool:
                children = set(getattr(handle, "get_children", lambda: ())() or ())
                for info in self.layers.values():
                    artists = set(info.get("artists", ()))
                    if handle in artists or children.intersection(artists):
                        return bool(info.get("visible", True))
                getter = getattr(handle, "get_visible", None)
                if callable(getter):
                    try:
                        return bool(getter())
                    except Exception:
                        pass
                if children:
                    return any(
                        bool(getattr(child, "get_visible", lambda: True)())
                        for child in children
                    )
                return True

            available = [
                (h, lbl) for h, lbl in zip(handles, labels)
                if lbl and not str(lbl).startswith("_") and logical_handle_visible(h)
            ]
            if not available:
                if legend is not None:
                    legend.remove()
                return

            # Keep a custom legend order when possible.  Match each displayed
            # row to one current source handle (duplicates are consumed one at
            # a time), then append genuinely new layers.
            ordered = []
            if legend is not None:
                for text in legend.get_texts():
                    wanted = text.get_text()
                    match = next(
                        (i for i, (_handle, label) in enumerate(available)
                         if str(label) == wanted),
                        None,
                    )
                    if match is not None:
                        ordered.append(available.pop(match))
            ordered.extend(available)
            h, labels_out = zip(*ordered)

            if previous and previous.get("format", {}).get("exists"):
                from core.format_clipboard import _apply_legend

                fmt = dict(previous["format"])
                was_visible = bool(fmt.get("visible", True))
                fmt["exists"] = True
                fmt["visible"] = True
                content = {
                    "exists": True,
                    "handles": list(h),
                    "labels": list(labels_out),
                    "title": previous.get("content", {}).get("title", ""),
                }
                _apply_legend(ax, fmt, content)
                refreshed = ax.get_legend()
                if refreshed is not None:
                    refreshed.set_visible(was_visible)
            else:
                refreshed = ax.legend(h, labels_out, loc="best")
                try:
                    refreshed._ps_drag_enabled = True
                    refreshed.set_draggable(True)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        info = self.layers.get(layer_id)
        label = str(info.get("label", "Layer")) if info else "Layer"
        verb = "Show" if visible else "Hide"
        with self.graph_format_history.transaction(f"{verb} layer: {label}"):
            self._set_layer_visibility(layer_id, visible)

    def _on_layer_rename(self, layer_id: str, new_label: str) -> None:
        info = self.layers.get(layer_id)
        old_label = str(info.get("label", "Layer")) if info else "Layer"
        with self.graph_format_history.transaction(f"Rename layer: {old_label}"):
            self._rename_layer_raw(layer_id, new_label)

    def _rename_layer_raw(self, layer_id: str, new_label: str) -> None:
        """Apply a logical layer rename without creating another undo command."""
        info = self.layers.get(layer_id)
        if not info:
            return
        old_label = str(info.get("label", ""))
        new_label = str(new_label)
        artists = list(info.get("artists", ()))

        # Resolve the one logical legend handle before mutating labels.  Bar
        # and histogram layers store their child patches, while Matplotlib's
        # legend source is the parent container; never label every patch.
        source_handle = None
        target_ax = next(
            (getattr(artist, "axes", None) for artist in artists
             if getattr(artist, "axes", None) is not None),
            self.get_axes(),
        )
        try:
            handles, labels = target_ax.get_legend_handles_labels()
            for handle, label in zip(handles, labels):
                if str(label) != old_label:
                    continue
                if handle in artists:
                    source_handle = handle
                    break
                try:
                    if set(handle.get_children()).intersection(artists):
                        source_handle = handle
                        break
                except Exception:
                    continue
            if source_handle is None:
                same_layers = [
                    lid for lid, layer in self.layers.items()
                    if str(layer.get("label", "")) == old_label
                    and any(getattr(a, "axes", None) is target_ax
                            for a in layer.get("artists", ()))
                ]
                occurrence = same_layers.index(layer_id) if layer_id in same_layers else 0
                matches = [
                    handle for handle, label in zip(handles, labels)
                    if str(label) == old_label
                ]
                if occurrence < len(matches):
                    source_handle = matches[occurrence]
        except Exception:
            source_handle = None

        try:
            if source_handle is not None:
                source_handle.set_label(new_label)
        except Exception:
            pass
        for artist in artists:
            try:
                if str(artist.get_label()) == old_label:
                    artist.set_label(new_label)
            except Exception:
                pass

        # Change the corresponding displayed row before the preserve-format
        # rebuild so duplicate labels keep their own position and identity.
        try:
            legend = target_ax.get_legend()
            if legend is not None:
                same_layers = [
                    lid for lid, layer in self.layers.items()
                    if str(layer.get("label", "")) == old_label
                    and any(getattr(a, "axes", None) is target_ax
                            for a in layer.get("artists", ()))
                ]
                occurrence = same_layers.index(layer_id) if layer_id in same_layers else 0
                rows = [
                    text for text in legend.get_texts()
                    if text.get_text() == old_label
                ]
                if occurrence < len(rows):
                    rows[occurrence].set_text(new_label)
        except Exception:
            pass

        info["label"] = new_label
        info.setdefault("meta", {})
        info["meta"]["label"] = new_label
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
        # Removing a layer changes artist topology; formatting snapshots do not
        # retain scientific data and cannot safely recreate it.
        self.graph_format_history.clear()
        from matplotlib.lines import Line2D
        from core.plot_style import remove_line_decorations

        for artist in info.get("artists", []):
            try:
                if isinstance(artist, Line2D):
                    remove_line_decorations(artist)
                artist.remove()
            except Exception:
                pass
        self.layer_manager.remove_layer(layer_id)
        self._refresh_legend()
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

    def quick_layer_style_summary(self, layer_ids) -> Dict[str, Any]:
        """Return common values plus mixed/unavailable hints for the Inspector."""
        import numpy as np
        from matplotlib.collections import Collection
        from matplotlib.colors import to_hex
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch

        records = []
        unavailable = set()
        layer_mixed = set()

        def same_value(values) -> bool:
            if not values:
                return False
            first = values[0]
            return all(
                bool(np.isclose(value, first))
                if isinstance(value, (int, float)) and isinstance(first, (int, float))
                else value == first
                for value in values[1:]
            )

        for layer_id in layer_ids or ():
            info = self.layers.get(str(layer_id))
            artists = list(info.get("artists", ())) if isinstance(info, dict) else []
            record = {}
            candidates = {"color": [], "alpha": [], "linewidth": [], "marker": []}
            for artist in artists:
                if isinstance(artist, Line2D):
                    try:
                        candidates["color"].append(to_hex(artist.get_color()))
                    except Exception:
                        pass
                    try:
                        candidates["linewidth"].append(float(artist.get_linewidth()))
                    except Exception:
                        pass
                    try:
                        candidates["marker"].append(str(artist.get_marker() or "None"))
                    except Exception:
                        pass
                elif isinstance(artist, Collection):
                    try:
                        if artist.get_array() is not None:
                            unavailable.add("color")
                        else:
                            colors = np.asarray(artist.get_facecolors())
                            if colors.size:
                                rows = colors.reshape(-1, colors.shape[-1])
                                if len(rows) == 1:
                                    candidates["color"].append(to_hex(colors[0]))
                                else:
                                    layer_mixed.add("color")
                    except Exception:
                        pass
                    try:
                        widths = np.asarray(artist.get_linewidths(), dtype=float).ravel()
                        if widths.size:
                            if widths.size == 1:
                                candidates["linewidth"].append(float(widths[0]))
                            else:
                                layer_mixed.add("linewidth")
                    except Exception:
                        pass
                elif isinstance(artist, Patch):
                    try:
                        candidates["color"].append(to_hex(artist.get_facecolor()))
                    except Exception:
                        pass
                    try:
                        candidates["linewidth"].append(float(artist.get_linewidth()))
                    except Exception:
                        pass
                try:
                    alpha = artist.get_alpha()
                    alpha_values = np.asarray(
                        1.0 if alpha is None else alpha, dtype=float,
                    ).ravel()
                    if alpha_values.size == 1:
                        candidates["alpha"].append(float(alpha_values[0]))
                    elif alpha_values.size > 1:
                        layer_mixed.add("alpha")
                except Exception:
                    pass

            for key, values in candidates.items():
                if same_value(values):
                    record[key] = values[0]
                elif values:
                    layer_mixed.add(key)
            records.append(record)

        result: Dict[str, Any] = {"unavailable_fields": sorted(unavailable)}
        mixed = set(layer_mixed)
        for key in ("color", "alpha", "linewidth", "marker"):
            values = [record[key] for record in records if key in record]
            if not values:
                result[key] = None
                continue
            first = values[0]
            equal = all(
                bool(np.isclose(value, first))
                if isinstance(value, (int, float)) and isinstance(first, (int, float))
                else value == first
                for value in values[1:]
            )
            if not equal or len(values) != len(records):
                mixed.add(key)
                result[key] = None
            else:
                result[key] = first
        result["mixed_fields"] = sorted(mixed)
        return result

    def apply_quick_layer_format(self, layer_ids, values: Dict[str, Any]) -> int:
        """Apply common appearance values to logical layers in one undo step."""
        selected = [str(layer_id) for layer_id in layer_ids if str(layer_id) in self.layers]
        values = {
            key: value for key, value in dict(values or {}).items()
            if key in {"color", "alpha", "linewidth", "marker", "palette"}
        }
        if not selected or not values:
            return 0

        from matplotlib.collections import Collection
        from matplotlib.lines import Line2D
        from matplotlib.markers import MarkerStyle
        from matplotlib.patches import Patch
        from core.plot_style import SCIENTIFIC_PALETTES, apply_line_style
        from matplotlib.colors import to_hex

        palette_colors = list(SCIENTIFIC_PALETTES.get(str(values.get("palette", "")), ()))

        changed_layers = 0
        with self.graph_format_history.transaction(
            f"Format {len(selected)} selected layer{'s' if len(selected) != 1 else ''}"
        ):
            for layer_index, layer_id in enumerate(selected):
                info = self.layers.get(layer_id)
                if not isinstance(info, dict):
                    continue
                layer_style = str(info.get("style", ""))
                artists = list(info.get("artists", ()))
                changed = False
                mapped_collection = False
                color_value = values.get("color")
                if palette_colors:
                    color_value = palette_colors[layer_index % len(palette_colors)]
                if layer_style == "scatter":
                    for artist in artists:
                        try:
                            if isinstance(artist, Collection) and artist.get_array() is not None:
                                mapped_collection = True
                                break
                        except Exception:
                            pass

                for artist in artists:
                    old_line_color = None
                    if isinstance(artist, Line2D):
                        try:
                            old_line_color = to_hex(artist.get_color())
                        except Exception:
                            pass
                    if color_value is not None:
                        color = color_value
                        try:
                            if isinstance(artist, Line2D):
                                artist.set_color(color)
                                changed = True
                            elif isinstance(artist, Collection) and not mapped_collection:
                                artist.set_facecolor(color)
                                changed = True
                            elif isinstance(artist, Patch):
                                artist.set_facecolor(color)
                                changed = True
                        except Exception:
                            pass

                    if "alpha" in values:
                        try:
                            artist.set_alpha(float(values["alpha"]))
                            changed = True
                        except Exception:
                            pass

                    if "linewidth" in values:
                        try:
                            artist.set_linewidth(float(values["linewidth"]))
                            changed = True
                        except Exception:
                            pass
                    if "marker" in values:
                        marker = values["marker"]
                        try:
                            if isinstance(artist, Line2D):
                                artist.set_marker("None" if marker in (None, "None", "none") else marker)
                                changed = True
                            elif layer_style == "scatter" and hasattr(artist, "set_paths"):
                                marker_style = MarkerStyle(marker)
                                path = marker_style.get_path().transformed(marker_style.get_transform())
                                artist.set_paths([path])
                                changed = True
                        except Exception:
                            pass

                    if isinstance(artist, Line2D) and changed:
                        # Generated fill/error/value-label/extrema artists are
                        # dependents of the curve. Rebuild them so auto colors,
                        # line-width-derived strokes and visibility stay in
                        # sync with the base line after Quick Format.
                        semantic = {}
                        effects = dict(getattr(artist, "_ps_effects", None) or {})
                        if effects and color_value is not None:
                            glow_color = effects.get("glow_color")
                            if not glow_color or (
                                old_line_color is not None
                                and to_hex(glow_color) == old_line_color
                            ):
                                effects["glow_color"] = color_value
                        semantic.update(effects)
                        semantic.update(dict(getattr(artist, "_ps_deco", None) or {}))
                        if semantic:
                            try:
                                apply_line_style(artist, semantic)
                            except Exception:
                                pass

                if not changed:
                    continue
                changed_layers += 1
                kwargs = info.setdefault("kwargs", {})
                meta = info.setdefault("meta", {})
                style_kwargs = dict(meta.get("style_kwargs", {}))
                if color_value is not None and not mapped_collection:
                    color_key = "color" if layer_style in {"line", "scatter"} else "facecolor"
                    kwargs[color_key] = color_value
                    style_kwargs[color_key] = color_value
                if "alpha" in values:
                    kwargs["alpha"] = float(values["alpha"])
                    style_kwargs["alpha"] = float(values["alpha"])
                if "linewidth" in values:
                    width_key = "linewidths" if layer_style == "scatter" else "linewidth"
                    kwargs[width_key] = float(values["linewidth"])
                    style_kwargs[width_key] = float(values["linewidth"])
                if "marker" in values and layer_style in {"line", "scatter"}:
                    kwargs["marker"] = values["marker"]
                    style_kwargs["marker"] = values["marker"]
                meta["style_kwargs"] = style_kwargs

            if changed_layers:
                self._refresh_legend()
                try:
                    self.canvas.draw_idle()
                except Exception:
                    pass
        return changed_layers

    def _on_layer_style_request(self, layer_id: str) -> None:
        selected = self.layer_manager.selected_layer_ids()
        if len(selected) > 1:
            color = self.layer_manager.prompt_color("Selected Layer Color")
            if not color or not getattr(color, "isValid", lambda: False)():
                return
            self.apply_quick_layer_format(selected, {"color": color.name()})
            return
        info = self.layers.get(layer_id)
        if not info:
            return
        label = str(info.get("label", "Layer"))
        with self.graph_format_history.transaction(f"Style layer: {label}"):
            style = info.get("style")
            if style == "line":
                self._style_line_layer(info)
            elif style in {"scatter", "bar", "histogram"}:
                self._style_filled_layer(info)

    def _style_line_layer(self, info: Dict[str, Any]) -> None:
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

    def _style_filled_layer(self, info: Dict[str, Any]) -> None:
        artists = list(info.get("artists", []))
        if not artists:
            return
        info.setdefault("kwargs", {})
        info.setdefault("meta", {})
        style_meta = dict(info["meta"].get("style_kwargs", {}))

        color = self.layer_manager.prompt_color()
        if color and getattr(color, "isValid", lambda: False)():
            color_name = color.name()
            for artist in artists:
                self._set_artist_fill_color(artist, color_name)
            if info.get("style") == "scatter":
                info["kwargs"]["color"] = color_name
                style_meta["color"] = color_name
            else:
                info["kwargs"]["facecolor"] = color_name
                style_meta["facecolor"] = color_name

        current_alpha = 1.0
        for artist in artists:
            try:
                alpha = artist.get_alpha()
            except Exception:
                alpha = None
            if alpha is not None:
                current_alpha = float(alpha)
                break
        alpha, ok = QInputDialog.getDouble(
            self, "Layer Opacity", "Opacity:", float(current_alpha), 0.0, 1.0, 2
        )
        if ok:
            for artist in artists:
                try:
                    artist.set_alpha(alpha)
                except Exception:
                    pass
            info["kwargs"]["alpha"] = float(alpha)
            style_meta["alpha"] = float(alpha)

        if style_meta:
            info["meta"]["style_kwargs"] = style_meta
        self._refresh_legend()
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

    @staticmethod
    def _set_artist_fill_color(artist, color_name: str) -> None:
        for setter in ("set_facecolor", "set_color"):
            try:
                getattr(artist, setter)(color_name)
                return
            except Exception:
                continue


class TabManager(QTabWidget):
    tabCreated = Signal(str)
    tabRemoved = Signal(str)
    renderStatusChanged = Signal(str)

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
        graph_tab.renderStatusChanged.connect(self.renderStatusChanged.emit)
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
            render_info = None
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
                        for artist in artists:
                            artist._sciplotter_x_values = list(x_vals)
                            artist._sciplotter_y_values = list(y_vals)
                    elif style == "scatter":
                        artists, render_info = draw_scatter_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    elif style == "bar":
                        artists, render_info = draw_bar_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if style == "line" and artists:
                    render_info = apply_line_lod(
                        ax, artists[0], pixel_width=canvas_pixel_width(ax)
                    )
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
                if render_info is not None:
                    layer_meta["render"] = dict(render_info)
                layer_id = tab.register_layer(artists, auto_label or label or "", style, meta=layer_meta, kwargs=local_kwargs)
                if layer_id:
                    created.append((tab_id, layer_id))
                    if hasattr(tab, "_refresh_legend"):
                        tab._refresh_legend()
            except Exception:
                pass
        return created

    def add_series_to_tabs(
        self,
        tab_ids,
        x,
        y,
        label: str = "",
        style: str = "line",
        meta: Optional[Dict[str, Any]] = None,
        *,
        defer_draw: bool = False,
        **kwargs,
    ):
        """Add a series, optionally deferring expensive legend/layout/draw work.

        ``defer_draw`` is used by multi-column plotting so N columns cause one
        final layout and canvas draw instead of N complete redraw cycles.
        """
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
            render_info = None
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
                        for artist in artists:
                            artist._sciplotter_x_values = list(x_vals)
                            artist._sciplotter_y_values = list(y_vals)
                    elif style == "scatter":
                        artists, render_info = draw_scatter_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    elif style == "bar":
                        artists, render_info = draw_bar_series(
                            ax, x_vals, y_vals, label=auto_label, **local_kwargs
                        )
                    else:
                        artists = list(ax.plot(x_vals, y_vals, label=auto_label, **local_kwargs))
                ax.relim()
                ax.autoscale_view()
                if style == "line" and artists:
                    render_info = apply_line_lod(
                        ax, artists[0], pixel_width=canvas_pixel_width(ax)
                    )
                if not x_is_datetime and axis_uses_dates(ax.xaxis):
                    reset_numeric_axis(ax)
                if x_is_datetime and len(x_vals) >= 2:
                    ax.set_xlim(min(x_vals), max(x_vals))
                clamp_date_limits(ax)
                if not defer_draw:
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
                if render_info is not None:
                    layer_meta["render"] = dict(render_info)
                layer_id = tab.register_layer(artists, auto_label or label or "", style, meta=layer_meta, kwargs=local_kwargs)
                if layer_id:
                    created.append((tab_id, layer_id))
                    if not defer_draw and hasattr(tab, "_refresh_legend"):
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
