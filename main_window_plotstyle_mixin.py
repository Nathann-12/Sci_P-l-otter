from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
import logging
from typing import Any, Optional

from core.plot_style import (
    apply_line_style,
    apply_style,
    read_line_style,
    read_style,
)

logger = logging.getLogger(__name__)


@dataclass
class _GraphTextTarget:
    """One authored text object that can be edited directly on a graph."""

    kind: str
    artist: Any
    axes: Any = None
    tab: Any = None
    title_loc: Optional[str] = None
    legend_index: Optional[int] = None
    layer_id: Optional[str] = None
    source_handle: Any = None


class MainWindowPlotStyleMixin:
    """OriginPro-style graph customization ("Plot Details").

    Reads the active graph's axes/figure/curves into a style dict, hands it to
    the tabbed dialog, and applies the edited result back. Live "Apply" redraws
    without closing. The style math lives in core/plot_style.py.
    """

    def _active_graph_edit_tab(self):
        try:
            tab = self._get_current_tab() if hasattr(self, "_get_current_tab") else None
        except Exception:
            tab = None
        if tab is None:
            try:
                tab = self.tabs.currentWidget()
            except Exception:
                tab = None
        return tab if hasattr(tab, "graph_undo_stack") else None

    def _active_annotation_edit_manager(self):
        tab = self._active_graph_edit_tab()
        return getattr(tab, "annotation_manager", None) if tab is not None else None

    @staticmethod
    def _native_text_history_target():
        try:
            from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

            widget = QApplication.focusWidget()
            if widget is None or not widget.isVisible() or not widget.isEnabled():
                return None, None
            if isinstance(widget, QLineEdit):
                return widget, widget
            if isinstance(widget, (QTextEdit, QPlainTextEdit)):
                return widget, widget.document()
        except Exception:
            pass
        return None, None

    @classmethod
    def _native_text_history_available(cls, redo: bool) -> bool:
        _widget, source = cls._native_text_history_target()
        if source is None:
            return False
        try:
            return bool(source.isRedoAvailable() if redo else source.isUndoAvailable())
        except Exception:
            return False

    @classmethod
    def _run_native_text_history(cls, redo: bool) -> bool:
        """Let a focused editor keep normal Ctrl+Z/Ctrl+Y semantics."""
        widget, source = cls._native_text_history_target()
        if widget is None or source is None:
            return False
        try:
            available = source.isRedoAvailable() if redo else source.isUndoAvailable()
            if available:
                widget.redo() if redo else widget.undo()
                return True
        except Exception:
            logger.debug("native text undo/redo routing failed", exc_info=True)
        return False

    def _bind_native_edit_history(self, _old=None, new=None) -> None:
        previous = getattr(self, "_bound_native_history_source", None)
        if previous is not None:
            for name in ("undoAvailable", "redoAvailable"):
                try:
                    getattr(previous, name).disconnect(self._sync_edit_history_actions)
                except Exception:
                    pass
        source = None
        try:
            from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit

            if isinstance(new, QLineEdit):
                source = new
            elif isinstance(new, (QTextEdit, QPlainTextEdit)):
                source = new.document()
        except Exception:
            source = None
        self._bound_native_history_source = source
        if source is not None:
            for name in ("undoAvailable", "redoAvailable"):
                try:
                    getattr(source, name).connect(self._sync_edit_history_actions)
                except Exception:
                    pass
        self._sync_edit_history_actions()

    @staticmethod
    def _graph_history_sequence(stack, *, redo: bool) -> int:
        if stack is None:
            return 0
        try:
            index = stack.index() if redo else stack.index() - 1
            if index < 0 or index >= stack.count():
                return 0
            return int(getattr(stack.command(index), "edit_sequence", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _annotation_history_sequence(manager, *, redo: bool) -> int:
        if manager is None:
            return 0
        values = getattr(
            manager,
            "_redo_sequences" if redo else "_undo_sequences",
            (),
        )
        try:
            return int(values[-1]) if values else 0
        except Exception:
            return 0

    def _history_owner(self, tab, manager, *, redo: bool):
        stack = getattr(tab, "graph_undo_stack", None)
        graph_available = bool(
            stack is not None and (stack.canRedo() if redo else stack.canUndo())
        )
        if redo and bool(getattr(tab, "_graph_redo_invalidated", False)):
            graph_available = False
        annotation_available = bool(
            manager is not None
            and getattr(manager, "_redo" if redo else "_undo", ())
        )
        if not graph_available:
            return "annotation" if annotation_available else None
        if not annotation_available:
            return "graph"

        graph_seq = self._graph_history_sequence(stack, redo=redo)
        annotation_seq = self._annotation_history_sequence(manager, redo=redo)
        if graph_seq and annotation_seq:
            # Undo newest first; redo rebuilds the timeline oldest first.
            if redo:
                return "graph" if graph_seq < annotation_seq else "annotation"
            return "graph" if graph_seq > annotation_seq else "annotation"
        if graph_seq:
            return "graph"
        if annotation_seq:
            return "annotation"
        # Compatibility with annotation managers/snapshots created before the
        # sequence metadata existed.
        return "annotation" if bool(getattr(manager, "enabled", False)) else "graph"

    def _undo_user_edit(self):
        if self._run_native_text_history(False):
            self._sync_edit_history_actions()
            return
        tab = self._active_graph_edit_tab()
        manager = self._active_annotation_edit_manager()
        owner = self._history_owner(tab, manager, redo=False)
        if owner == "graph":
            tab.graph_undo_stack.undo()
        elif owner == "annotation":
            manager.undo()
        self._sync_edit_history_actions()

    def _redo_user_edit(self):
        if self._run_native_text_history(True):
            self._sync_edit_history_actions()
            return
        tab = self._active_graph_edit_tab()
        manager = self._active_annotation_edit_manager()
        owner = self._history_owner(tab, manager, redo=True)
        if owner == "graph":
            tab.graph_undo_stack.redo()
        elif owner == "annotation":
            manager.redo()
        self._sync_edit_history_actions()

    def _bind_active_graph_history(self, *_args) -> None:
        previous = getattr(self, "_bound_graph_undo_stack", None)
        if previous is not None:
            for signal_name in (
                "canUndoChanged", "canRedoChanged", "undoTextChanged",
                "redoTextChanged", "indexChanged",
            ):
                try:
                    getattr(previous, signal_name).disconnect(self._sync_edit_history_actions)
                except Exception:
                    pass
        tab = self._active_graph_edit_tab()
        stack = getattr(tab, "graph_undo_stack", None)
        self._bound_graph_undo_stack = stack
        if stack is not None:
            for signal_name in (
                "canUndoChanged", "canRedoChanged", "undoTextChanged",
                "redoTextChanged", "indexChanged",
            ):
                try:
                    getattr(stack, signal_name).connect(self._sync_edit_history_actions)
                except Exception:
                    pass
        self._sync_edit_history_actions()

    def _sync_edit_history_actions(self, *_args) -> None:
        undo_action = getattr(self, "actUndo", None)
        redo_action = getattr(self, "actRedo", None)
        if undo_action is None or redo_action is None:
            return
        try:
            from shiboken6 import isValid

            if not isValid(undo_action) or not isValid(redo_action):
                return
        except Exception:
            pass
        tab = self._active_graph_edit_tab()
        stack = getattr(tab, "graph_undo_stack", None)
        manager = self._active_annotation_edit_manager()
        ann_undo = bool(manager is not None and getattr(manager, "_undo", ()))
        ann_redo = bool(manager is not None and getattr(manager, "_redo", ()))
        graph_undo = bool(stack is not None and stack.canUndo())
        graph_redo = bool(
            stack is not None and stack.canRedo()
            and not bool(getattr(tab, "_graph_redo_invalidated", False))
        )
        text_undo = self._native_text_history_available(False)
        text_redo = self._native_text_history_available(True)
        undo_owner = self._history_owner(tab, manager, redo=False)
        redo_owner = self._history_owner(tab, manager, redo=True)

        if text_undo:
            undo_text = "Undo Text Edit"
        elif undo_owner == "annotation":
            undo_text = "Undo Annotation"
        elif undo_owner == "graph":
            undo_text = f"Undo {stack.undoText()}" if stack.undoText() else "Undo Graph Edit"
        else:
            undo_text = "Undo"
        if text_redo:
            redo_text = "Redo Text Edit"
        elif redo_owner == "annotation":
            redo_text = "Redo Annotation"
        elif redo_owner == "graph":
            redo_text = f"Redo {stack.redoText()}" if stack.redoText() else "Redo Graph Edit"
        else:
            redo_text = "Redo"
        try:
            undo_action.setText(undo_text)
            redo_action.setText(redo_text)
            undo_action.setEnabled(text_undo or graph_undo or ann_undo)
            redo_action.setEnabled(text_redo or graph_redo or ann_redo)
        except RuntimeError:
            # A queued focusChanged can arrive while the window is closing,
            # after Qt has already deleted its QAction children.
            return

    def bind_graph_dblclick(self, *_):
        """Bind direct text editing and the graph double-click shortcuts.

        Safe to call repeatedly (guards against re-binding the same canvas).
        """
        try:
            tab = self.tabs.currentWidget()
            canvas = getattr(tab, "canvas", None)
            if canvas is None:
                return
            self._ensure_direct_legend_drag(tab)
            if getattr(canvas, "_plotdetails_bound", False):
                return
            canvas.mpl_connect("button_press_event", self._on_canvas_click)
            canvas.mpl_connect("button_release_event", self._on_canvas_release)
            canvas._plotdetails_bound = True
        except Exception:
            logger.debug("graph dblclick bind skipped", exc_info=True)

    def _on_canvas_click(self, event):
        if getattr(event, "dblclick", False):
            # Preserve the established inspector shortcut even when the pointer
            # happens to be over text.
            key = str(getattr(event, "key", "") or "").casefold()
            if "control" in key or "shift" in key:
                opener = getattr(self, "open_graph_data_panel", None)
                if callable(opener):
                    opener()
                    return
            # A double-click on an annotation text belongs to the annotation
            # manager (inline edit) — opening Plot Details on top of the text
            # editor would fight it for the same gesture.
            if self._annotation_dblclick_target(event):
                self._finish_graph_text_editor(commit=True)
                return
            target = self._graph_text_target_at_event(event)
            if target is not None and self._start_graph_text_edit(target, event):
                return
            # Origin behaviour: double-click ANYWHERE on the graph opens Plot
            # Details — no need to aim at a thin line. Landing near a curve
            # (generous 12px radius) preselects it in the Lines tab.
            # Ctrl/Shift+double-click opens the Graph Data inspector instead.
            self.open_plot_details_dialog(
                preselect_line=self._line_index_at_event(event)
            )
            return

        if getattr(event, "button", None) != 1:
            return
        fig = getattr(getattr(event, "canvas", None), "figure", None)
        tab = self._graph_tab_for_figure(fig) if fig is not None else None
        if tab is None:
            return
        try:
            if bool(getattr(getattr(tab, "toolbar", None), "mode", "")):
                return
        except Exception:
            pass
        self._ensure_direct_legend_drag(tab)
        legend = self._legend_at_event(tab, event)
        if legend is not None:
            capture = getattr(tab, "capture_graph_format_state", None)
            if callable(capture):
                try:
                    self._legend_drag_state = (tab, capture())
                except Exception:
                    self._legend_drag_state = None
            return

        manager = getattr(tab, "annotation_manager", None)
        if manager is not None and bool(getattr(manager, "enabled", False)):
            return
        layer_id = self._layer_id_at_event(tab, event)
        layer_manager = getattr(tab, "layer_manager", None)
        selector = getattr(layer_manager, "select_layer_ids", None)
        if not callable(selector):
            return
        key = str(getattr(event, "key", "") or "").casefold()
        current = list(layer_manager.selected_layer_ids())
        if layer_id is None:
            if "control" not in key and "shift" not in key:
                selector([])
            return
        if "control" in key:
            selected = [item for item in current if item != layer_id]
            if layer_id not in current:
                selected.append(layer_id)
        elif "shift" in key:
            selected = current + ([layer_id] if layer_id not in current else [])
        else:
            selected = [layer_id]
        selector(selected)
        info = (getattr(tab, "layers", {}) or {}).get(layer_id, {})
        try:
            self.statusBar().showMessage(
                f"Selected layer: {info.get('label') or layer_id} — use Appearance in the Inspector"
            )
        except Exception:
            pass

    def _on_canvas_release(self, _event) -> None:
        state = getattr(self, "_legend_drag_state", None)
        self._legend_drag_state = None
        if not state:
            return
        tab, before = state
        # Matplotlib's DraggableLegend release callback may run after this
        # application callback. Defer one Qt turn so the captured "after"
        # state contains its finalized _loc.
        from PySide6.QtCore import QTimer

        def record_final_location():
            recorder = getattr(tab, "record_applied_graph_format", None)
            if callable(recorder):
                try:
                    if recorder("Move legend", before):
                        self._sync_edit_history_actions()
                except Exception:
                    logger.debug("legend drag history failed", exc_info=True)

        QTimer.singleShot(0, record_final_location)

    @staticmethod
    def _ensure_direct_legend_drag(tab) -> None:
        try:
            fig = tab.get_figure()
        except Exception:
            return
        for ax in getattr(fig, "axes", ()):
            legend = getattr(ax, "get_legend", lambda: None)()
            if legend is None:
                continue
            try:
                if not hasattr(legend, "_ps_drag_enabled"):
                    legend._ps_drag_enabled = True
                legend.set_draggable(bool(legend._ps_drag_enabled))
            except Exception:
                pass

    @staticmethod
    def _legend_at_event(tab, event):
        try:
            canvas = tab.canvas
            canvas.draw()
            renderer = canvas.get_renderer()
            for ax in reversed(list(getattr(tab.get_figure(), "axes", ()))):
                legend = ax.get_legend()
                if legend is None or not legend.get_visible():
                    continue
                bbox = legend.get_window_extent(renderer=renderer)
                if bbox.contains(float(event.x), float(event.y)):
                    return legend
        except Exception:
            pass
        return None

    @staticmethod
    def _layer_id_at_event(tab, event):
        """Return the topmost logical layer hit by a normal canvas click."""
        candidates = []
        for order, (layer_id, info) in enumerate(
            reversed(list((getattr(tab, "layers", {}) or {}).items()))
        ):
            if not bool(info.get("visible", True)):
                continue
            for artist in reversed(list(info.get("artists", ()))):
                try:
                    if not artist.get_visible():
                        continue
                except Exception:
                    pass
                axes = getattr(artist, "axes", None)
                if getattr(event, "inaxes", None) is not None and axes is not event.inaxes:
                    continue
                old_radius = None
                try:
                    if hasattr(artist, "get_pickradius") and hasattr(artist, "set_pickradius"):
                        old_radius = artist.get_pickradius()
                        artist.set_pickradius(max(8.0, float(old_radius)))
                    hit, _details = artist.contains(event)
                except Exception:
                    hit = False
                finally:
                    if old_radius is not None:
                        try:
                            artist.set_pickradius(old_radius)
                        except Exception:
                            pass
                if hit:
                    try:
                        zorder = float(artist.get_zorder())
                    except Exception:
                        zorder = 0.0
                    candidates.append((zorder, -order, str(layer_id)))
                    break
        return max(candidates)[2] if candidates else None

    def _annotation_dblclick_target(self, event) -> bool:
        """True when the annotation manager owns the text under this click."""
        try:
            fig = getattr(getattr(event, "canvas", None), "figure", None)
            tab = self._graph_tab_for_figure(fig) if fig is not None else None
            if tab is None:
                tab = self.tabs.currentWidget()
            mgr = getattr(tab, "annotation_manager", None)
            if mgr is None:
                return False
            return mgr._nearest_text_index(event) is not None
        except Exception:
            logger.debug("annotation dblclick probe failed", exc_info=True)
            return False

    # --------------------------------------------------------- live graph text

    @staticmethod
    def _artist_axes(artist):
        axes = getattr(artist, "axes", None)
        if axes is not None:
            return axes
        try:
            for child in artist.get_children():
                axes = getattr(child, "axes", None)
                if axes is not None:
                    return axes
        except Exception:
            pass
        return None

    def _legend_binding(self, tab, ax, legend, index):
        """Resolve a legend row to its source handle and logical layer.

        Label occurrence, rather than label text alone, is used as the fallback
        so two series with the same display name can still be edited separately.
        """
        texts = list(legend.get_texts())
        if index < 0 or index >= len(texts):
            return None, None
        wanted = texts[index].get_text()

        handles, labels = ax.get_legend_handles_labels()
        available = [
            (handle, str(label))
            for handle, label in zip(handles, labels)
            if label and not str(label).startswith("_")
        ]
        source_handle = None
        for row in texts[: index + 1]:
            row_label = row.get_text()
            match = next(
                (i for i, (_handle, label) in enumerate(available)
                 if label == row_label),
                None,
            )
            if match is None:
                source_handle = None
                continue
            source_handle = available.pop(match)[0]

        layers = getattr(tab, "layers", {}) if tab is not None else {}
        if not isinstance(layers, dict):
            return source_handle, None

        # Identity is authoritative for ordinary line/scatter/collection
        # handles, and child identity covers containers such as bar/histogram.
        source_children = set()
        try:
            source_children.update(source_handle.get_children())
        except Exception:
            pass
        for layer_id, info in layers.items():
            artists = list(info.get("artists", ()))
            if source_handle in artists or source_children.intersection(artists):
                return source_handle, layer_id

        # Standard legends and Layer Manager preserve insertion order.  Match
        # the Nth duplicate on this axes, never every layer with the same name.
        occurrence = sum(
            1 for text in texts[:index] if text.get_text() == wanted
        )
        candidates = []
        for layer_id, info in layers.items():
            if str(info.get("label", "")) != wanted:
                continue
            artists = list(info.get("artists", ()))
            artist_axes = {
                self._artist_axes(artist) for artist in artists
                if self._artist_axes(artist) is not None
            }
            if artist_axes and ax not in artist_axes:
                continue
            candidates.append(layer_id)
        layer_id = candidates[occurrence] if occurrence < len(candidates) else None
        return source_handle, layer_id

    def _graph_text_targets(self, tab=None):
        """Return semantic text targets for every axes in a graph figure.

        Tick labels, offset notation, and generated value/extrema labels are
        intentionally absent: formatters/configuration own those strings and a
        direct ``Text.set_text`` would be overwritten on the next draw/zoom.
        """
        if isinstance(tab, bool):
            tab = None
        if tab is None:
            try:
                tab = self.tabs.currentWidget()
            except Exception:
                return []
        if tab is None:
            return []
        try:
            fig = tab.get_figure()
        except Exception:
            try:
                fig = tab.get_axes().figure
            except Exception:
                return []

        targets = []
        suptitle = getattr(fig, "_suptitle", None)
        if suptitle is not None:
            targets.append(_GraphTextTarget("figure_title", suptitle, tab=tab))

        for ax in list(getattr(fig, "axes", ())):
            title_specs = (
                ("left", getattr(ax, "_left_title", None)),
                ("center", getattr(ax, "title", None)),
                ("right", getattr(ax, "_right_title", None)),
            )
            seen = set()
            for loc, artist in title_specs:
                if artist is None or id(artist) in seen:
                    continue
                seen.add(id(artist))
                targets.append(_GraphTextTarget(
                    "title", artist, axes=ax, tab=tab, title_loc=loc,
                ))

            for kind, axis_name in (
                ("xlabel", "xaxis"),
                ("ylabel", "yaxis"),
                ("zlabel", "zaxis"),
            ):
                axis = getattr(ax, axis_name, None)
                artist = getattr(axis, "label", None) if axis is not None else None
                if artist is not None:
                    targets.append(_GraphTextTarget(kind, artist, axes=ax, tab=tab))

            legend = ax.get_legend()
            if legend is not None:
                title = legend.get_title()
                if title is not None:
                    targets.append(_GraphTextTarget(
                        "legend_title", title, axes=ax, tab=tab,
                    ))
                for index, artist in enumerate(legend.get_texts()):
                    source_handle, layer_id = self._legend_binding(
                        tab, ax, legend, index
                    )
                    targets.append(_GraphTextTarget(
                        "legend_item",
                        artist,
                        axes=ax,
                        tab=tab,
                        legend_index=index,
                        layer_id=layer_id,
                        source_handle=source_handle,
                    ))

        return targets

    @staticmethod
    def _text_bbox(artist, canvas):
        try:
            renderer = canvas.get_renderer()
            return artist.get_window_extent(renderer=renderer)
        except Exception:
            return None

    def _graph_text_target_at_event(self, event):
        """Return the closest editable rendered text under ``event``."""
        x = getattr(event, "x", None)
        y = getattr(event, "y", None)
        if x is None or y is None:
            return None
        canvas = getattr(event, "canvas", None)
        fig = getattr(canvas, "figure", None)
        tab = self._graph_tab_for_figure(fig) if fig is not None else None
        if tab is None:
            try:
                tab = self.tabs.currentWidget()
                canvas = getattr(tab, "canvas", canvas)
            except Exception:
                return None
        if canvas is None:
            return None

        hits = []
        padding = 7.0
        for order, target in enumerate(self._graph_text_targets(tab)):
            artist = target.artist
            try:
                if not artist.get_visible() or not artist.get_text():
                    continue
            except Exception:
                continue
            bbox = self._text_bbox(artist, canvas)
            if bbox is None:
                continue
            if not (
                bbox.x0 - padding <= x <= bbox.x1 + padding
                and bbox.y0 - padding <= y <= bbox.y1 + padding
            ):
                continue
            cx = (bbox.x0 + bbox.x1) * 0.5
            cy = (bbox.y0 + bbox.y1) * 0.5
            distance = (float(x) - cx) ** 2 + (float(y) - cy) ** 2
            area = max(1.0, float(bbox.width) * float(bbox.height))
            hits.append((distance, area, order, target))
        if not hits:
            return None
        return min(hits, key=lambda item: item[:3])[3]

    def _target_for_graph_text(self, kind, tab=None, ax=None, legend_index=None):
        targets = self._graph_text_targets(tab)
        if ax is not None:
            targets = [target for target in targets if target.axes is ax]
        if kind == "title":
            title_targets = [target for target in targets if target.kind == "title"]
            return next(
                (target for target in title_targets if target.artist.get_text()),
                next((target for target in title_targets
                      if target.title_loc == "center"), None),
            )
        for target in targets:
            if target.kind != kind:
                continue
            if kind == "legend_item" and legend_index is not None:
                if target.legend_index != int(legend_index):
                    continue
            return target
        return None

    def edit_graph_text(self, kind, tab=None, ax=None, legend_index=None):
        """Open the in-canvas editor from a discoverable menu action."""
        target = self._target_for_graph_text(kind, tab, ax, legend_index)
        if target is None and kind == "figure_title":
            try:
                tab = tab or self.tabs.currentWidget()
                fig = tab.get_figure()
                target = _GraphTextTarget(
                    "figure_title", fig.suptitle(""), tab=tab,
                )
            except Exception:
                target = None
        if target is None:
            return False
        return self._start_graph_text_edit(target)

    def _finish_graph_text_editor(self, *, commit=False):
        callback_name = (
            "_graph_text_editor_commit" if commit
            else "_graph_text_editor_cancel"
        )
        callback = getattr(self, callback_name, None)
        if callable(callback):
            callback()

    def _start_graph_text_edit(self, target, event=None):
        """Place a one-line Qt editor over a Matplotlib text artist."""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QWidget
            from annotations import _InlineTextEdit

            tab = target.tab
            canvas = getattr(tab, "canvas", None)
            if canvas is None or not isinstance(canvas, QWidget):
                return False

            # Moving to a second label behaves like focus-out: commit the first
            # edit before starting the next one.
            self._finish_graph_text_editor(commit=True)

            bbox = self._text_bbox(target.artist, canvas)
            canvas_width = max(1, int(canvas.width()))
            canvas_height = max(1, int(canvas.height()))
            if bbox is not None:
                cx = (bbox.x0 + bbox.x1) * 0.5
                cy_qt = canvas_height - (bbox.y0 + bbox.y1) * 0.5
                text_extent = max(float(bbox.width), float(bbox.height))
            else:
                x = getattr(event, "x", canvas_width * 0.5) if event else canvas_width * 0.5
                y = getattr(event, "y", canvas_height * 0.5) if event else canvas_height * 0.5
                cx = float(x)
                cy_qt = canvas_height - float(y)
                text_extent = 120.0

            width = min(max(160, int(text_extent + 48)), max(80, canvas_width - 8))
            height = min(30, max(24, canvas_height - 8))
            qt_x = max(4, min(int(cx - width * 0.5), canvas_width - width - 4))
            qt_y = max(4, min(int(cy_qt - height * 0.5), canvas_height - height - 4))

            edit = _InlineTextEdit(canvas)
            edit.setObjectName("GraphInlineTextEditor")
            edit.setText(str(target.artist.get_text()))
            edit.setGeometry(qt_x, qt_y, width, height)
            edit.setToolTip("Enter: apply  •  Esc: cancel")
            edit.setStyleSheet(
                "QLineEdit#GraphInlineTextEditor {"
                " border: 2px solid #4F9CF9; border-radius: 3px; padding: 2px 6px; }"
            )
            edit.show()
            edit.raise_()
            edit.setFocus(Qt.MouseFocusReason)
            edit.selectAll()

            state = {"done": False}

            def clear_refs():
                if getattr(self, "_graph_text_editor", None) is edit:
                    self._graph_text_editor = None
                    self._graph_text_editor_commit = None
                    self._graph_text_editor_cancel = None

            def commit():
                if state["done"]:
                    return
                state["done"] = True
                self._commit_graph_text(target, edit.text().strip())
                clear_refs()
                edit.deleteLater()

            def cancel():
                if state["done"]:
                    return
                state["done"] = True
                clear_refs()
                edit.deleteLater()

            self._graph_text_editor = edit
            self._graph_text_editor_commit = commit
            self._graph_text_editor_cancel = cancel
            edit.returnPressed.connect(commit)
            edit.editingFinished.connect(commit)
            edit.cancelled.connect(cancel)
            return True
        except Exception:
            logger.debug("graph inline text edit failed", exc_info=True)
            return False

    def _commit_graph_text(self, target, new_text):
        """Commit an edit while keeping legend/layer state consistent."""
        try:
            text = str(new_text)
            old_text = str(target.artist.get_text())
            if text == old_text:
                return False
            tab = target.tab
            transaction = getattr(tab, "graph_format_transaction", None)
            context = (
                transaction("Edit graph text") if callable(transaction) else nullcontext()
            )
            with context:
                if target.kind == "legend_item":
                    if target.layer_id is not None and callable(
                        getattr(tab, "_on_layer_rename", None)
                    ):
                        tab._on_layer_rename(target.layer_id, text)
                    else:
                        if target.source_handle is not None:
                            try:
                                target.source_handle.set_label(text)
                            except Exception:
                                pass
                        target.artist.set_text(text)
                else:
                    target.artist.set_text(text)

            if target.kind != "legend_item" or target.layer_id is None:
                if hasattr(tab, "draw"):
                    tab.draw()
                else:
                    target.artist.figure.canvas.draw_idle()
            notifier = getattr(self, "notify", None)
            if callable(notifier):
                notifier("Graph text updated")
            return True
        except Exception:
            logger.debug("graph text commit failed", exc_info=True)
            return False

    @staticmethod
    def _sync_line_layer_labels(tab, lines):
        """Keep Plot Details label edits in the persistent layer model."""
        layers = getattr(tab, "layers", {}) if tab is not None else {}
        if not isinstance(layers, dict):
            return
        for line in lines:
            for layer_id, info in layers.items():
                if line not in info.get("artists", ()):
                    continue
                try:
                    label = str(line.get_label())
                except Exception:
                    break
                info["label"] = label
                info.setdefault("meta", {})["label"] = label
                manager = getattr(tab, "layer_manager", None)
                updater = getattr(manager, "update_layer_label", None)
                if callable(updater):
                    updater(layer_id, label)
                break

    # ------------------------------------------------------------------ format
    # ``read_style`` contains values seeded for the Plot Details dialog, some
    # of which are deliberately defaults rather than an exact readback.  A
    # dedicated appearance snapshot is therefore used for cross-graph paste.

    def _format_clipboard_tab(self, tab=None):
        if isinstance(tab, bool):  # QAction.triggered(bool)
            tab = None
        if tab is not None:
            return tab
        try:
            return self.tabs.currentWidget()
        except Exception:
            return None

    def copy_graph_format(self, source_tab=None):
        """Copy graph appearance without names, ranges or scientific data."""
        from core.format_clipboard import capture_graph_format

        tab = self._format_clipboard_tab(source_tab)
        if tab is None or not hasattr(tab, "get_axes"):
            self.inform("No graph", "Open or select a graph to copy its format")
            return False
        try:
            self._format_clipboard = capture_graph_format(tab)
            self._refresh_action_states()
            sync_quick = getattr(self, "_sync_quick_format_actions", None)
            if callable(sync_quick):
                sync_quick()
            count = int(self._format_clipboard.get("series_count", 0))
            suffix = f" ({count} series)" if count else ""
            self.notify(
                f"Graph format copied{suffix} — choose another graph and Paste Format"
            )
            return True
        except Exception as e:
            self.error_box("Copy format failed", f"Reason: {e}")
            return False

    def has_format_clipboard(self) -> bool:
        from core.format_clipboard import is_graph_format_snapshot

        return is_graph_format_snapshot(getattr(self, "_format_clipboard", None))

    def paste_graph_format(self, target_tab=None):
        """Paste appearance onto the active or explicitly supplied graph.

        Target titles, labels, scales/ranges, legend content, references,
        annotations, layer visibility and data-mapped colours are preserved.
        """
        from core.format_clipboard import apply_graph_format

        if not self.has_format_clipboard():
            self.inform("Nothing to paste", "Copy a graph's format first")
            return False
        tab = self._format_clipboard_tab(target_tab)
        if tab is None or not hasattr(tab, "get_axes"):
            self.inform("No graph", "Open or select a graph to paste the format onto")
            return False
        try:
            transaction = getattr(tab, "graph_format_transaction", None)
            context = (
                transaction("Paste graph format")
                if callable(transaction) else nullcontext()
            )
            with context:
                applied = apply_graph_format(tab, self._format_clipboard)
            fig = (
                tab.get_figure()
                if hasattr(tab, "get_figure")
                else tab.get_axes().figure
            )
            if hasattr(tab, "draw"):
                tab.draw()
            elif getattr(fig, "canvas", None) is not None:
                fig.canvas.draw_idle()
            suffix = f" to {applied} series" if applied else ""
            self.notify(f"Graph format pasted{suffix} — data and axis ranges kept")
            return True
        except Exception as e:
            self.error_box("Paste format failed", f"Reason: {e}")
            return False

    _PICK_RADIUS_PX = 12.0  # generous hit area — thin lines are hard targets

    def _line_index_at_event(self, event):
        """Index (among the user's curves) of the line under the cursor, or None."""
        try:
            from core.plot_style import list_line_artists

            ax, _fig, _lines = self._active_graph_axes()
            if ax is None:
                return None
            for index, line in enumerate(list_line_artists(ax)):
                old_radius = line.get_pickradius()
                try:
                    line.set_pickradius(self._PICK_RADIUS_PX)
                    hit, _detail = line.contains(event)
                finally:
                    line.set_pickradius(old_radius)
                if hit:
                    return index
        except Exception:
            logger.debug("pick-to-edit hit test failed", exc_info=True)
        return None

    def _active_graph_axes(self):
        """(ax, fig, lines) of the current graph tab, or (None, None, [])."""
        try:
            from core.plot_style import list_line_artists

            tab = self.tabs.currentWidget()
            if tab is None or not hasattr(tab, "get_axes"):
                return None, None, []
            ax = tab.get_axes()
            fig = tab.get_figure() if hasattr(tab, "get_figure") else ax.figure
            # only the user's curves — never our decoration artists
            # (reference lines, error-bar caps) as editable "Lines"
            return ax, fig, list_line_artists(ax)
        except Exception:
            logger.debug("active graph axes lookup failed", exc_info=True)
            return None, None, []

    def open_plot_details_dialog(self, preselect_line=None):
        """Open the Plot Details dialog for the active graph."""
        from dialogs.plot_details_dialog import PlotDetailsDialog
        from core import plot_templates

        # Reject the previous live-preview session before reading the graph.
        # Its finished handler restores the state from when that dialog opened;
        # capturing first would seed the new dialog with a preview that is no
        # longer on the canvas.
        prev = getattr(self, "_plot_details_dlg", None)
        if prev is not None:
            try:
                prev.reject()
            except Exception:
                logger.debug("closing previous plot details failed", exc_info=True)

        target_tab = self.tabs.currentWidget()
        ax, fig, lines = self._active_graph_axes()
        if ax is None:
            self.inform("No graph", "Open or select a graph window first")
            return

        style = read_style(ax, fig)
        line_styles = [read_line_style(ln) for ln in lines]
        history_before = None
        capture_history = getattr(target_tab, "capture_graph_format_state", None)
        if callable(capture_history):
            try:
                history_before = capture_history()
            except Exception:
                logger.debug("plot details history snapshot failed", exc_info=True)
        dlg = PlotDetailsDialog(
            style, line_styles, parent=self,
            template_names=plot_templates.list_templates())

        def _apply():
            self._apply_plot_details(ax, fig, lines, dlg, target_tab=target_tab)

        def _save_template(name):
            self._save_plot_template_from_dialog(dlg, name)

        def _load_template(name):
            self._load_plot_template_into_dialog(
                dlg, name, ax=ax, fig=fig, lines=lines, target_tab=target_tab
            )

        def _delete_template(name):
            self._delete_plot_template_from_dialog(dlg, name)

        dlg.applied.connect(_apply)
        dlg.save_template_requested.connect(_save_template)
        dlg.load_template_requested.connect(_load_template)
        dlg.delete_template_requested.connect(_delete_template)
        if preselect_line is not None:
            dlg.focus_line(int(preselect_line))

        # Non-modal + placed beside the graph so the live preview stays visible.
        # A modal window centred over the graph hid the very thing being
        # formatted, so the user could not see their changes take effect.
        from PySide6.QtWidgets import QDialog

        self._plot_details_dlg = dlg

        def _on_finished(result):
            try:
                if result == QDialog.Accepted:
                    _apply()
                    recorder = getattr(target_tab, "record_applied_graph_format", None)
                    if history_before is not None and callable(recorder):
                        recorder("Format graph", history_before)
                else:
                    # Live preview committed edits as the user typed; Cancel must
                    # put the graph back exactly as it was when the dialog opened.
                    restorer = getattr(target_tab, "restore_graph_format_state", None)
                    if history_before is not None and callable(restorer):
                        restorer(history_before)
                    else:
                        self._restore_plot_details(
                            ax, fig, lines, style, line_styles, target_tab=target_tab
                        )
            finally:
                if getattr(self, "_plot_details_dlg", None) is dlg:
                    self._plot_details_dlg = None

        dlg.finished.connect(_on_finished)
        dlg.setModal(False)
        self._position_plot_details_dialog(dlg, target_tab)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def _plot_details_target_rect(self, target_tab):
        """Global-screen rectangle of the graph being formatted, if resolvable."""
        from PySide6.QtCore import QRect
        try:
            canvas = getattr(target_tab, "canvas", None)
            if canvas is not None and canvas.isVisible():
                tl = canvas.mapToGlobal(canvas.rect().topLeft())
                br = canvas.mapToGlobal(canvas.rect().bottomRight())
                return QRect(tl, br)
        except Exception:
            logger.debug("plot details target rect failed", exc_info=True)
        return None

    def _position_plot_details_dialog(self, dlg, target_tab) -> None:
        """Place Plot Details next to the graph, never on top of it."""
        from PySide6.QtWidgets import QApplication
        try:
            dlg.adjustSize()
            dw, dh = dlg.width(), dlg.height()
            screen = self.screen() if hasattr(self, "screen") else None
            screen = screen or QApplication.primaryScreen()
            avail = screen.availableGeometry()
            graph = self._plot_details_target_rect(target_tab)
            margin = 8
            x = y = None
            if graph is not None:
                if graph.right() + margin + dw <= avail.right():          # right of graph
                    x = graph.right() + margin
                elif avail.left() + dw + margin <= graph.left():          # left of graph
                    x = graph.left() - margin - dw
                if x is not None:
                    y = min(max(graph.top(), avail.top()), avail.bottom() - dh)
            if x is None:
                # No clear side — dock to the right screen edge (over the tool
                # docks, which matter far less than the graph itself).
                x = avail.right() - dw - margin
                y = avail.top() + margin
            x = max(avail.left(), min(int(x), avail.right() - dw))
            y = max(avail.top(), min(int(y), avail.bottom() - dh))
            dlg.move(x, y)
        except Exception:
            logger.debug("plot details positioning failed", exc_info=True)

    def _restore_plot_details(self, ax, fig, lines, style, line_styles, *,
                              target_tab=None) -> None:
        """Reapply the pre-edit snapshot to undo any live-preview changes."""
        try:
            apply_style(ax, style, fig, live=True)
            for ln, d in zip(lines, line_styles):
                apply_line_style(ln, d)
            tab = target_tab or self._graph_tab_for_figure(fig)
            self._sync_line_layer_labels(tab, lines)
            self._relayout_live_figure(fig)
            if hasattr(tab, "draw"):
                tab.draw()
            elif getattr(fig, "canvas", None) is not None:
                fig.canvas.draw_idle()
        except Exception:
            logger.debug("plot details revert failed", exc_info=True)

    def _refresh_plot_template_names(self, dlg) -> None:
        from core import plot_templates

        try:
            dlg.set_template_names(plot_templates.list_templates())
        except Exception:
            logger.debug("template list refresh skipped", exc_info=True)

    def _save_plot_template_from_dialog(self, dlg, name: str) -> None:
        from core import plot_templates

        try:
            plot_templates.save_template(name, dlg.get_style())
            self._refresh_plot_template_names(dlg)
            try:
                dlg.cb_template.setCurrentText(name)
            except Exception:
                logger.debug("template combobox sync skipped", exc_info=True)
            self.notify(f"Saved template: {name}")
        except Exception as e:
            self.error_box("Save template failed", f"Reason: {e}")

    def _load_plot_template_into_dialog(self, dlg, name: str, *, ax, fig, lines, target_tab=None) -> None:
        from core import plot_templates

        try:
            tpl = plot_templates.load_template(name)
            dlg._loading = True
            try:
                dlg.load_style_into_controls(tpl)
            finally:
                dlg._loading = False
            self._apply_plot_details(ax, fig, lines, dlg, target_tab=target_tab)
            self.notify(f"Applied template: {name}")
        except Exception as e:
            self.error_box("Load template failed", f"Reason: {e}")

    def _delete_plot_template_from_dialog(self, dlg, name: str) -> None:
        from core import plot_templates

        try:
            removed = plot_templates.delete_template(name)
            if not removed:
                self.inform("Template not found", f"Template '{name}' no longer exists.")
                self._refresh_plot_template_names(dlg)
                return
            self._refresh_plot_template_names(dlg)
            self.notify(f"Deleted template: {name}")
        except Exception as e:
            self.error_box("Delete template failed", f"Reason: {e}")

    def _draw_active_graph(self, fig=None, tab=None) -> None:
        if tab is None:
            tab = self._graph_tab_for_figure(fig)
        if hasattr(tab, "draw"):
            tab.draw()
        elif fig is not None:
            fig.canvas.draw_idle()

    def _graph_tab_for_figure(self, fig):
        try:
            for tab in getattr(self.tabs, "tabs", {}).values():
                try:
                    if tab.get_figure() is fig:
                        return tab
                except Exception:
                    continue
        except Exception:
            pass
        try:
            return self.tabs.currentWidget()
        except Exception:
            return None

    def _apply_plot_details(self, ax, fig, lines, dlg, *, target_tab=None) -> None:
        from core.plot_style import diff_style

        try:
            style = dlg.get_style()
            line_styles = dlg.get_line_styles()
            # Apply ONLY what changed since the dialog opened / last Apply —
            # untouched controls must never restyle the graph (identity Apply
            # is a visual no-op; a stray seed can't blank the plot).
            baseline = getattr(dlg, "_seed_style", None)
            effective = diff_style(baseline, style) if baseline else style
            apply_style(ax, effective, fig, live=True)   # on-screen: no size/dpi
            base_lines = getattr(dlg, "_seed_line_styles", None)
            lines_changed = False
            for i, (ln, d) in enumerate(zip(lines, line_styles)):
                if (base_lines is not None and i < len(base_lines)
                        and d == base_lines[i]):
                    continue
                apply_line_style(ln, d)
                lines_changed = True
            tab = target_tab or self._graph_tab_for_figure(fig)
            self._sync_line_layer_labels(tab, lines)
            # Scientific palette recolour: a one-shot action, applied only when
            # the user actually changed it since the last Apply (so identity
            # Apply stays a no-op and respects the diff-apply contract).
            palette = style.get("palette") or {}
            base_palette = (baseline or {}).get("palette") or {}
            pal_name = palette.get("name")
            keep = getattr(dlg, "_palette_keep", "— keep colors —")
            if pal_name and pal_name != keep and palette != base_palette:
                from core.plot_style import apply_palette
                apply_palette(ax, pal_name, line_width=palette.get("line_width"))
                lines_changed = True
            # a legend may need rebuilding after labels/colors change
            if ((("legend" in effective) or lines_changed)
                    and style.get("legend", {}).get("visible")):
                apply_style(ax, {"legend": style["legend"]})
            # next Apply diffs against what is now on screen
            try:
                dlg._seed_style = style
                dlg._seed_line_styles = line_styles
            except Exception:
                logger.debug("re-baselining style failed", exc_info=True)
            # remember the chosen print size/dpi for export (not applied live)
            fig_style = style.get("figure", {})
            if tab is not None and (fig_style.get("width_in") or fig_style.get("dpi")):
                tab._print_figure = {
                    "width_in": fig_style.get("width_in"),
                    "height_in": fig_style.get("height_in"),
                    "dpi": fig_style.get("dpi"),
                }
            self._relayout_live_figure(fig)  # re-expand plot area; never resize canvas
            if hasattr(tab, "draw"):
                tab.draw()
            else:
                fig.canvas.draw_idle()
            self.notify("Applied graph formatting")
        except Exception as e:
            self.error_box("Formatting failed", f"Reason: {e}")

    def _relayout_live_figure(self, fig) -> None:
        """Re-expand the plot area to fill the canvas after a style change.

        Deliberately never sets the figure size or DPI. The embedded Qt canvas
        owns those, and forcing them from Qt *logical* pixels renders the figure
        smaller than the widget on any HiDPI display (device pixel ratio > 1,
        i.e. Windows at 125%/150%): that is the "graph shrinks whenever I
        decorate it" bug. ``tight_layout`` maximizes the axes within whatever
        size the canvas currently is, so the plot area stays full every apply.
        """
        if fig is None:
            return
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fig.tight_layout()
            return
        except Exception:
            logger.debug("tight_layout relayout skipped", exc_info=True)
        # fallback: sane fixed margins for a simple single-axes figure
        try:
            axes = [ax for ax in getattr(fig, "axes", []) if ax.get_visible()]
            if len(axes) == 1:
                fig.subplots_adjust(left=0.12, right=0.96, bottom=0.14, top=0.92)
        except Exception:
            logger.debug("axes layout restore skipped", exc_info=True)
