from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple

import json
import logging
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QColorDialog, QSpinBox, QComboBox, QCheckBox, QFormLayout, QDialog,
    QListWidget, QListWidgetItem, QDialogButtonBox, QInputDialog, QLineEdit
)

import matplotlib
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle, Ellipse, FancyArrowPatch


class _InlineTextEdit(QLineEdit):
    """In-canvas text editor: Enter commits, Escape cancels."""
    cancelled = Signal()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(ev)


@dataclass
class AnnotationStyle:
    stroke: str = "#ffffff"
    fill: str = "#00000000"  # transparent
    lw: float = 1.5
    alpha: float = 1.0
    font: str = ""
    fontsize: int = 11
    bold: bool = False
    italic: bool = False
    arrowstyle: str = "-|>"
    zorder: int = 3


@dataclass
class AnnotationItem:
    kind: str
    props: Dict[str, Any]
    style: AnnotationStyle


class AnnotationManager(QObject):
    changed = Signal()
    selection_changed = Signal()

    def __init__(self, fig: Figure, ax: Axes, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.fig = fig
        self.ax = ax
        self.enabled: bool = False
        self.mode: Optional[str] = None  # text|arrow|line|rect|ellipse|callout
        self.items: List[AnnotationItem] = []
        self.artists: List[Any] = []  # matplotlib artists in same order
        self._press_pt: Optional[Tuple[float, float]] = None
        self._current_artist: Optional[Any] = None
        self._style = AnnotationStyle()

        # Selection state
        self.selected_index: Optional[int] = None
        self._is_dragging: bool = False
        self._drag_start_pt: Optional[Tuple[float, float]] = None
        self._drag_orig_props: Optional[Dict[str, Any]] = None
        self._selector_artist: Optional[Rectangle] = None
        self._handle_artist: Optional[Any] = None

        # Resize (grab a handle on the selected item)
        self._resize_handle: Optional[str] = None
        self._resize_orig: Optional[Dict[str, Any]] = None
        self._resize_snapshot_pending: bool = False

        # Clipboard for copy/paste + constrained-draw bookkeeping
        self._clipboard: Optional[Dict[str, Any]] = None
        self._last_draw_pt: Optional[Tuple[float, float]] = None
        self._last_nudge_ts: float = 0.0

        # Default annotation font to current Matplotlib family (ensures Thai if configured)
        try:
            fam = matplotlib.rcParams.get("font.family")
            fam0 = fam[0] if isinstance(fam, (list, tuple)) and fam else (fam if isinstance(fam, str) else "")
            if fam0:
                self._style.font = fam0
        except Exception:
            pass
        self._undo: List[str] = []  # JSON snapshots
        self._redo: List[str] = []

        # Connect mpl events
        self.cid_press = self.fig.canvas.mpl_connect('button_press_event', self._on_press)
        self.cid_release = self.fig.canvas.mpl_connect('button_release_event', self._on_release)
        self.cid_motion = self.fig.canvas.mpl_connect('motion_notify_event', self._on_motion)
        self.cid_key = self.fig.canvas.mpl_connect('key_press_event', self._on_key)
        # Let other canvas consumers (graph context menu, Plot Details dblclick)
        # discover this manager and yield gestures that land on an annotation.
        try:
            self.fig.canvas._annotation_manager = self
        except Exception:
            pass

    # -------- public API --------
    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        if not self.enabled:
            self.mode = None
            self.clear_selection()
        self._update_cursor()
        self.changed.emit()

    def set_mode(self, mode: Optional[str]) -> None:
        self.mode = mode
        if self.mode is not None:
            self.clear_selection()
        self._update_cursor()
        self.changed.emit()

    def clear_selection(self) -> None:
        self.selected_index = None
        for attr in ('_selector_artist', '_handle_artist'):
            artist = getattr(self, attr, None)
            if artist is not None:
                try:
                    artist.remove()
                except Exception:
                    pass
                setattr(self, attr, None)
        self.selection_changed.emit()
        self.fig.canvas.draw_idle()

    def delete_selected(self) -> None:
        if self.selected_index is not None and self.selected_index < len(self.items):
            self._snapshot()
            idx = self.selected_index
            self.selected_index = None
            if self._selector_artist:
                try:
                    self._selector_artist.remove()
                except Exception:
                    pass
                self._selector_artist = None
            try:
                self.artists[idx].remove()
            except Exception:
                pass
            del self.items[idx]
            del self.artists[idx]
            self.fig.canvas.draw_idle()
            self.changed.emit()
            self.selection_changed.emit()

    # -------- clipboard / duplicate / arrange (PowerPoint-style ops) --------
    def duplicate_selected(self) -> Optional[int]:
        """Clone the selected annotation slightly offset and select the clone."""
        if self.selected_index is None or self.selected_index >= len(self.items):
            return None
        return self._paste_payload(self._item_payload(self.items[self.selected_index]))

    def copy_selected(self) -> bool:
        if self.selected_index is None or self.selected_index >= len(self.items):
            return False
        self._clipboard = self._item_payload(self.items[self.selected_index])
        return True

    def paste_clipboard(self) -> Optional[int]:
        if not self._clipboard:
            return None
        return self._paste_payload(self._clipboard)

    def _item_payload(self, it: AnnotationItem) -> Dict[str, Any]:
        return {'kind': it.kind, 'props': dict(it.props), 'style': asdict(it.style)}

    def _paste_payload(self, payload: Dict[str, Any]) -> Optional[int]:
        try:
            self._snapshot()
            props = dict(payload['props'])
            # Nudge the clone by ~3% of the visible range so it lands beside
            # the original, never invisibly on top of it.
            x_lim = self.ax.get_xlim()
            y_lim = self.ax.get_ylim()
            dx = (x_lim[1] - x_lim[0]) * 0.03
            dy = -(y_lim[1] - y_lim[0]) * 0.03
            for kx in ('x', 'x1', 'x2', 'tx'):
                if kx in props:
                    props[kx] += dx
            for ky in ('y', 'y1', 'y2', 'ty'):
                if ky in props:
                    props[ky] += dy
            it = AnnotationItem(kind=payload['kind'], props=props,
                                style=AnnotationStyle(**payload['style']))
            self._create_artist_from_item(it)
            self.items.append(it)
            new_idx = len(self.items) - 1
            self.selected_index = new_idx
            self._update_selector()
            self.fig.canvas.draw_idle()
            self.changed.emit()
            self.selection_changed.emit()
            return new_idx
        except Exception:
            logging.getLogger(__name__).debug("annotation paste failed", exc_info=True)
            return None

    def bring_to_front(self, idx: Optional[int] = None) -> None:
        self._restack(idx, front=True)

    def send_to_back(self, idx: Optional[int] = None) -> None:
        self._restack(idx, front=False)

    def _restack(self, idx: Optional[int], *, front: bool) -> None:
        if idx is None:
            idx = self.selected_index
        if idx is None or idx >= len(self.items):
            return
        zs = [it.style.zorder for it in self.items] or [3]
        new_z = (max(zs) + 1) if front else max(0, min(zs) - 1)
        if self.items[idx].style.zorder == new_z:
            return
        self._snapshot()
        # Styles may be shared between items (the manager hands out the same
        # AnnotationStyle instance) — replace instead of mutating in place.
        st = asdict(self.items[idx].style)
        st['zorder'] = new_z
        self.items[idx].style = AnnotationStyle(**st)
        try:
            self.artists[idx].set_zorder(new_z)
        except Exception:
            pass
        self.fig.canvas.draw_idle()
        self.changed.emit()

    def nudge_selected(self, dx_frac: float, dy_frac: float) -> None:
        """Move the selected item by a fraction of the visible axis range."""
        if self.selected_index is None or self.selected_index >= len(self.items):
            return
        import time
        now = time.monotonic()
        # Coalesce a burst of key-repeats into one undo entry.
        if now - self._last_nudge_ts > 1.5:
            self._snapshot()
        self._last_nudge_ts = now
        x_lim = self.ax.get_xlim()
        y_lim = self.ax.get_ylim()
        dx = (x_lim[1] - x_lim[0]) * dx_frac
        dy = (y_lim[1] - y_lim[0]) * dy_frac
        idx = self.selected_index
        self._move_item(idx, dx, dy, dict(self.items[idx].props))
        self._update_selector()
        self.fig.canvas.draw_idle()
        self.changed.emit()

    def consumes_right_click(self, ev) -> bool:
        """True when a right-click lands on an annotation this manager owns —
        the graph context menu should yield to the annotation menu then."""
        try:
            return bool(self.enabled) and self._hit_test(ev) is not None
        except Exception:
            return False

    def _move_item(self, idx: int, dx: float, dy: float,
                   orig: Dict[str, Any]) -> None:
        """Apply a translation from ``orig`` props to item ``idx``."""
        item = self.items[idx]
        a = self.artists[idx]
        if item.kind == 'text':
            item.props['x'] = orig['x'] + dx
            item.props['y'] = orig['y'] + dy
            a.set_position((item.props['x'], item.props['y']))
        elif item.kind in ('rect', 'ellipse'):
            item.props['x'] = orig['x'] + dx
            item.props['y'] = orig['y'] + dy
            if item.kind == 'rect':
                a.set_xy((item.props['x'], item.props['y']))
            else:
                a.center = (item.props['x'], item.props['y'])
        elif item.kind in ('line', 'arrow'):
            item.props['x1'] = orig['x1'] + dx
            item.props['y1'] = orig['y1'] + dy
            item.props['x2'] = orig['x2'] + dx
            item.props['y2'] = orig['y2'] + dy
            if item.kind == 'line':
                a.set_data([item.props['x1'], item.props['x2']],
                           [item.props['y1'], item.props['y2']])
            else:
                a.set_positions((item.props['x1'], item.props['y1']),
                                (item.props['x2'], item.props['y2']))
        elif item.kind == 'callout':
            item.props['x'] = orig['x'] + dx
            item.props['y'] = orig['y'] + dy
            item.props['tx'] = orig['tx'] + dx
            item.props['ty'] = orig['ty'] + dy
            a.xy = (item.props['x'], item.props['y'])
            a.set_position((item.props['tx'], item.props['ty']))

    def _update_cursor(self) -> None:
        """Give the canvas a tool cursor so the user can see the tool is armed.

        Without this, picking Text/Arrow/Rect looked like a no-op — the pointer
        stayed a plain arrow even though clicks now place annotations.
        """
        try:
            from PySide6.QtGui import QCursor
            canvas = self.fig.canvas
            if not self.enabled or not self.mode:
                canvas.unsetCursor()
                return
            shape = Qt.IBeamCursor if self.mode == 'text' else Qt.CrossCursor
            canvas.setCursor(QCursor(shape))
        except Exception:
            logging.getLogger(__name__).debug("annotation cursor update failed", exc_info=True)

    def set_style(self, style: AnnotationStyle) -> None:
        self._style = style
        if self.selected_index is not None and self.selected_index < len(self.items):
            self._snapshot()
            self.items[self.selected_index].style = style
            self._update_artist_style(self.selected_index)
        self.selection_changed.emit()

    def get_style(self) -> AnnotationStyle:
        return self._style

    def clear(self) -> None:
        self.clear_selection()
        for a in list(self.artists):
            try:
                a.remove()
            except Exception:
                pass
        self.items.clear()
        self.artists.clear()
        self.fig.canvas.draw_idle()
        self.changed.emit()

    # --- persistence ---
    def to_json(self) -> str:
        data = [
            {
                'kind': it.kind,
                'props': it.props,
                'style': asdict(it.style),
            }
            for it in self.items
        ]
        return json.dumps(data, ensure_ascii=False)

    def from_json(self, s: str) -> None:
        try:
            data = json.loads(s) if s else []
        except Exception:
            data = []
        self.clear()
        for d in data:
            style = AnnotationStyle(**d.get('style', {}))
            it = AnnotationItem(kind=d.get('kind','text'), props=d.get('props', {}), style=style)
            self._create_artist_from_item(it)
            self.items.append(it)
        self.fig.canvas.draw_idle()
        self.changed.emit()

    # --- undo/redo ---
    def _snapshot(self) -> None:
        self._undo.append(self.to_json())
        self._redo.clear()

    def undo(self) -> None:
        if not self._undo:
            return
        cur = self.to_json()
        last = self._undo.pop()
        self._redo.append(cur)
        self.from_json(last)

    def redo(self) -> None:
        if not self._redo:
            return
        cur = self.to_json()
        nxt = self._redo.pop()
        self._undo.append(cur)
        self.from_json(nxt)

    # -------- event handlers --------
    def _on_key(self, ev):
        if not self.enabled:
            return
        key = str(ev.key or '')
        if key in ('delete', 'backspace'):
            if self.selected_index is not None:
                self.delete_selected()
        elif key == 'escape':
            # First Esc: drop the draw tool (enter Select mode); second Esc:
            # clear the current selection.
            if self.mode is not None:
                self.set_mode(None)
            else:
                self.clear_selection()
        elif key in ('left', 'right', 'up', 'down',
                     'shift+left', 'shift+right', 'shift+up', 'shift+down'):
            # Arrow keys nudge the selection (Shift = coarse step)
            step = 0.05 if key.startswith('shift+') else 0.01
            direction = key.split('+')[-1]
            dx = {'left': -step, 'right': step}.get(direction, 0.0)
            dy = {'down': -step, 'up': step}.get(direction, 0.0)
            self.nudge_selected(dx, dy)
        elif key == 'ctrl+d':
            self.duplicate_selected()
        elif key == 'ctrl+c':
            self.copy_selected()
        elif key == 'ctrl+v':
            self.paste_clipboard()
        elif key == 'pageup':
            self.bring_to_front()
        elif key == 'pagedown':
            self.send_to_back()

    def _on_press(self, ev):
        # Accept clicks on whatever axes is under the cursor; axes can be recreated during plotting
        if not self.enabled or ev.inaxes is None:
            return
        # Update target axes dynamically in case canvas recreated the axes
        if ev.inaxes is not self.ax:
            self.ax = ev.inaxes

        # Double-click near text → edit content inline
        if getattr(ev, 'dblclick', False):
            idx = self._nearest_text_index(ev)
            if idx is not None:
                self._start_inline_edit(idx)
                return

        # Right-click on an item → select it and show the annotation context
        # menu (works from any tool, like PowerPoint). A miss falls through to
        # the normal graph context menu, which yields via consumes_right_click.
        if getattr(ev, 'button', 1) == 3:
            idx = self._hit_test(ev)
            if idx is not None:
                self.selected_index = idx
                self._update_selector()
                self.selection_changed.emit()
                self._show_context_menu(idx)
            return

        # If in Selection Mode (mode is None), select the clicked item
        if self.mode is None:
            # A handle on the selected item wins over body hits → resize
            handle = self._handle_at(ev)
            if handle is not None and self.selected_index is not None:
                self._resize_handle = handle
                self._resize_orig = dict(self.items[self.selected_index].props)
                self._resize_snapshot_pending = True
                try:
                    from PySide6.QtGui import QCursor
                    self.fig.canvas.setCursor(QCursor(Qt.CrossCursor))
                except Exception:
                    pass
                return
            idx = self._hit_test(ev)
            if idx is not None:
                self.selected_index = idx
                self._is_dragging = True
                self._drag_start_pt = (ev.xdata, ev.ydata)
                self._drag_orig_props = dict(self.items[idx].props)
                # Undo must restore the PRE-move position, so the snapshot is
                # taken lazily on the first real motion (a plain click-select
                # then adds no junk undo entry).
                self._drag_snapshot_pending = True
                try:
                    from PySide6.QtGui import QCursor
                    self.fig.canvas.setCursor(QCursor(Qt.SizeAllCursor))
                except Exception:
                    pass
                self._update_selector()
                self.selection_changed.emit()
            else:
                self.clear_selection()
            return

        # Drawing Mode: Create a new annotation
        self._snapshot()
        self._press_pt = (ev.xdata, ev.ydata)
        if self.mode == 'text':
            it = AnnotationItem('text', {'x': ev.xdata, 'y': ev.ydata, 's': 'Text'}, self._style)
            self.items.append(it)
            a = self.ax.text(it.props['x'], it.props['y'], it.props['s'],
                             **self._text_kwargs())
            self.artists.append(a)
            self._current_artist = a
            self.fig.canvas.draw_idle()
        elif self.mode in ('rect','ellipse','line','arrow','callout'):
            if self.mode == 'rect':
                a = Rectangle((ev.xdata, ev.ydata), 1e-6, 1e-6,
                              linewidth=self._style.lw, edgecolor=self._style.stroke,
                              facecolor=self._style.fill, alpha=self._style.alpha,
                              zorder=self._style.zorder)
                self.ax.add_patch(a)
                it = AnnotationItem('rect', {'x': ev.xdata, 'y': ev.ydata, 'w': 0.0, 'h': 0.0}, self._style)
            elif self.mode == 'ellipse':
                a = Ellipse((ev.xdata, ev.ydata), 1e-6, 1e-6,
                            linewidth=self._style.lw, edgecolor=self._style.stroke,
                            facecolor=self._style.fill, alpha=self._style.alpha,
                            zorder=self._style.zorder)
                self.ax.add_patch(a)
                it = AnnotationItem('ellipse', {'x': ev.xdata, 'y': ev.ydata, 'w': 0.0, 'h': 0.0}, self._style)
            elif self.mode == 'line':
                a = self.ax.plot([ev.xdata, ev.xdata], [ev.ydata, ev.ydata],
                                 color=self._style.stroke, linewidth=self._style.lw, alpha=self._style.alpha,
                                 zorder=self._style.zorder)[0]
                it = AnnotationItem('line', {'x1': ev.xdata, 'y1': ev.ydata, 'x2': ev.xdata, 'y2': ev.ydata}, self._style)
            elif self.mode == 'arrow':
                a = FancyArrowPatch(posA=(ev.xdata, ev.ydata), posB=(ev.xdata, ev.ydata),
                                    arrowstyle=self._style.arrowstyle if self._style.arrowstyle else '-|>',
                                    mutation_scale=15, linewidth=self._style.lw,
                                    edgecolor=self._style.stroke, facecolor=self._style.stroke,
                                    alpha=self._style.alpha, zorder=self._style.zorder)
                self.ax.add_patch(a)
                it = AnnotationItem('arrow', {'x1': ev.xdata, 'y1': ev.ydata, 'x2': ev.xdata, 'y2': ev.ydata}, self._style)
            elif self.mode == 'callout':
                it = AnnotationItem('callout', {'x': ev.xdata, 'y': ev.ydata, 'tx': ev.xdata, 'ty': ev.ydata, 's': 'Callout'}, self._style)
                st = self._style
                a = self.ax.annotate(
                    it.props['s'],
                    xy=(it.props['x'], it.props['y']),
                    xytext=(it.props['tx'], it.props['ty']),
                    arrowprops=dict(
                        arrowstyle=st.arrowstyle if st.arrowstyle else '-|>',
                        color=st.stroke,
                        lw=st.lw,
                        alpha=st.alpha
                    ),
                    color=st.stroke,
                    fontsize=st.fontsize,
                    fontweight='bold' if st.bold else 'normal',
                    fontstyle='italic' if st.italic else 'normal',
                    zorder=st.zorder,
                    bbox=dict(
                        boxstyle="round,pad=0.3",
                        edgecolor=st.stroke,
                        facecolor=st.fill,
                        lw=st.lw,
                        alpha=st.alpha
                    ) if st.fill != "#00000000" else None
                )
            
            self.items.append(it)
            self.artists.append(a)
            self._current_artist = a
            self.fig.canvas.draw_idle()

    def _on_motion(self, ev):
        if not self.enabled or ev.inaxes is None:
            return

        # 1. Resizing via a grabbed handle on the selected item
        if self._resize_handle is not None and self.selected_index is not None:
            if self._resize_snapshot_pending:
                # First motion: props still hold pre-resize coordinates.
                self._snapshot()
                self._resize_snapshot_pending = False
            self._apply_resize(self._resize_handle, ev.xdata, ev.ydata)
            self._update_selector()
            self.fig.canvas.draw_idle()
            return

        # 2. Moving selected items
        if self._is_dragging and self.selected_index is not None:
            if self._drag_start_pt is None or self._drag_orig_props is None:
                return
            if getattr(self, '_drag_snapshot_pending', False):
                # First motion of this drag: items still hold the pre-move
                # coordinates, so the snapshot recorded here is what Undo
                # restores.
                self._snapshot()
                self._drag_snapshot_pending = False
            x0, y0 = self._drag_start_pt
            dx = ev.xdata - x0
            dy = ev.ydata - y0
            self._move_item(self.selected_index, dx, dy, self._drag_orig_props)
            self._update_selector()
            self.fig.canvas.draw_idle()
            return

        # 2. Hover feedback in Select mode: crosshair over a resize handle,
        # open-hand over a draggable item body
        if self.mode is None and not self._is_dragging and self._press_pt is None:
            try:
                from PySide6.QtGui import QCursor
                if self._handle_at(ev) is not None:
                    self.fig.canvas.setCursor(QCursor(Qt.CrossCursor))
                elif self._hit_test(ev) is not None:
                    self.fig.canvas.setCursor(QCursor(Qt.OpenHandCursor))
                else:
                    self.fig.canvas.unsetCursor()
            except Exception:
                pass
            return

        # 3. Resizing/Updating new items during creation drag
        if not self._press_pt or self._current_artist is None:
            return
        x0, y0 = self._press_pt
        x1, y1 = self._constrain_creation(ev, x0, y0, ev.xdata, ev.ydata)
        self._last_draw_pt = (x1, y1)
        a = self._current_artist

        if hasattr(a, 'set_width') and hasattr(a, 'set_height'):
            # Rectangle
            try:
                a.set_width(x1 - x0)
                a.set_height(y1 - y0)
            except Exception:
                pass
        elif hasattr(a, 'center') and hasattr(a, 'width') and not isinstance(a, Rectangle):
            # Ellipse
            a.width = abs(x1 - x0)
            a.height = abs(y1 - y0)
            a.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        elif isinstance(a, FancyArrowPatch):
            # Arrow (lag-free update)
            try:
                a.set_positions((x0, y0), (x1, y1))
            except Exception:
                pass
        elif isinstance(a, matplotlib.text.Annotation):
            # Callout (Annotate)
            try:
                a.set_position((x1, y1))
            except Exception:
                pass
        else:
            # Line2D
            try:
                from matplotlib.lines import Line2D
                if isinstance(a, Line2D):
                    a.set_data([x0, x1], [y0, y1])
            except Exception:
                pass
        self.fig.canvas.draw_idle()

    def _on_release(self, ev):
        if not self.enabled:
            return

        # Finalize a handle resize
        if self._resize_handle is not None:
            self._resize_handle = None
            self._resize_orig = None
            self._resize_snapshot_pending = False
            self._update_selector()
            self._update_cursor()
            self.changed.emit()
            return

        # If drag-moving existing item, finalize it (the undo snapshot was
        # already taken at the first motion — snapshotting here would record
        # the post-move state and make Undo a no-op)
        if self._is_dragging:
            self._is_dragging = False
            self._drag_start_pt = None
            self._drag_orig_props = None
            self._drag_snapshot_pending = False
            self._update_selector()
            self._update_cursor()
            self.changed.emit()
            return

        # Finalizing new drawn item
        if self._press_pt and self._current_artist is not None and len(self.items) > 0:
            x0, y0 = self._press_pt
            x1 = ev.xdata if ev.xdata is not None else x0
            y1 = ev.ydata if ev.ydata is not None else y0
            # Honor the Shift constraint the preview showed during the drag
            x1, y1 = self._constrain_creation(ev, x0, y0, x1, y1)
            self._last_draw_pt = None

            # Calculate pixel distance to filter accidental micro-clicks
            try:
                px0, py0 = self.ax.transData.transform((x0, y0))
                px1, py1 = self.ax.transData.transform((x1, y1))
                dist = ((px1 - px0)**2 + (py1 - py0)**2)**0.5
            except Exception:
                dist = 999.0

            it = self.items[-1]
            if it.kind != 'text' and dist < 5.0:
                # Accidental shape, discard it immediately
                try:
                    self._current_artist.remove()
                except Exception:
                    pass
                self.items.pop()
                self.artists.pop()
                if self._undo:
                    self._undo.pop()
                self._press_pt = None
                self._current_artist = None
                self.fig.canvas.draw_idle()
                return

            # Save coordinates
            if it.kind == 'rect':
                it.props['w'] = x1 - x0
                it.props['h'] = y1 - y0
            elif it.kind == 'ellipse':
                it.props['w'] = abs(x1 - x0)
                it.props['h'] = abs(y1 - y0)
                it.props['x'] = (x0 + x1) / 2
                it.props['y'] = (y0 + y1) / 2
            elif it.kind == 'line':
                it.props['x2'] = x1
                it.props['y2'] = y1
            elif it.kind == 'arrow':
                it.props['x2'] = x1
                it.props['y2'] = y1
            elif it.kind == 'callout':
                it.props['tx'] = x1
                it.props['ty'] = y1

            self.changed.emit()

            # Draw-once: hand the finished shape straight to Select mode and
            # select it, so the very next click drags it instead of stacking
            # another copy (PowerPoint/Origin behaviour). Re-click the tool
            # button to draw again.
            new_idx = len(self.items) - 1
            self._press_pt = None
            self._current_artist = None
            self.mode = None
            self.selected_index = new_idx
            self._update_selector()
            self._update_cursor()
            self.selection_changed.emit()
            if it.kind == 'text':
                # Let the user type immediately instead of leaving a literal
                # "Text" that needs a separate double-click to edit.
                self._begin_text_entry(new_idx)
            return

        self._press_pt = None
        self._current_artist = None

    # --- rebuild artists from items ---
    def _create_artist_from_item(self, it: AnnotationItem):
        st = it.style
        if it.kind == 'text':
            a = self.ax.text(it.props['x'], it.props['y'], it.props.get('s','Text'),
                             **self._text_kwargs())
            self.artists.append(a)
        elif it.kind == 'rect':
            a = Rectangle((it.props['x'], it.props['y']), it.props.get('w',0.0), it.props.get('h',0.0),
                          linewidth=st.lw, edgecolor=st.stroke, facecolor=st.fill, alpha=st.alpha, zorder=st.zorder)
            self.ax.add_patch(a)
            self.artists.append(a)
        elif it.kind == 'ellipse':
            a = Ellipse((it.props['x'], it.props['y']), it.props.get('w',0.0), it.props.get('h',0.0),
                        linewidth=st.lw, edgecolor=st.stroke, facecolor=st.fill, alpha=st.alpha, zorder=st.zorder)
            self.ax.add_patch(a)
            self.artists.append(a)
        elif it.kind == 'line':
            a = self.ax.plot([it.props['x1'], it.props['x2']], [it.props['y1'], it.props['y2']],
                             color=st.stroke, linewidth=st.lw, alpha=st.alpha, zorder=st.zorder)[0]
            self.artists.append(a)
        elif it.kind == 'arrow':
            a = FancyArrowPatch(posA=(it.props['x1'], it.props['y1']),
                                posB=(it.props['x2'], it.props['y2']),
                                arrowstyle=st.arrowstyle if st.arrowstyle else '-|>',
                                mutation_scale=15, linewidth=st.lw,
                                edgecolor=st.stroke, facecolor=st.stroke,
                                alpha=st.alpha, zorder=st.zorder)
            self.ax.add_patch(a)
            self.artists.append(a)
        elif it.kind == 'callout':
            a = self.ax.annotate(
                it.props.get('s', 'Callout'),
                xy=(it.props['x'], it.props['y']),
                xytext=(it.props['tx'], it.props['ty']),
                arrowprops=dict(
                    arrowstyle=st.arrowstyle if st.arrowstyle else '-|>',
                    color=st.stroke,
                    lw=st.lw,
                    alpha=st.alpha
                ),
                color=st.stroke,
                fontsize=st.fontsize,
                fontweight='bold' if st.bold else 'normal',
                fontstyle='italic' if st.italic else 'normal',
                zorder=st.zorder,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    edgecolor=st.stroke,
                    facecolor=st.fill,
                    lw=st.lw,
                    alpha=st.alpha
                ) if st.fill != "#00000000" else None
            )
            self.artists.append(a)

    # --- selection helpers ---
    def _point_to_segment_distance(self, px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return ((px - x1)**2 + (py - y1)**2)**0.5
        t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)
        t = max(0.0, min(1.0, t))
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return ((px - closest_x)**2 + (py - closest_y)**2)**0.5

    def _hit_test(self, ev) -> Optional[int]:
        if ev.x is None or ev.y is None or not self.artists:
            return None
        
        best_idx = None
        best_dist = float('inf')
        tolerance_px = 15.0
        
        # Iterate backward to select top-most elements first
        for i in reversed(range(len(self.artists))):
            item = self.items[i]
            try:
                # 1. Text Check
                if item.kind == 'text':
                    x = item.props['x']
                    y = item.props['y']
                    px, py = self.ax.transData.transform((x, y))
                    dist = ((ev.x - px)**2 + (ev.y - py)**2)**0.5
                    if dist <= tolerance_px and dist < best_dist:
                        best_dist = dist
                        best_idx = i
                    continue

                # 2. Rectangle Check
                elif item.kind == 'rect':
                    x = item.props['x']
                    y = item.props['y']
                    w = item.props.get('w', 0.0)
                    h = item.props.get('h', 0.0)
                    p0 = self.ax.transData.transform((x, y))
                    p1 = self.ax.transData.transform((x + w, y + h))
                    xmin, xmax = min(p0[0], p1[0]), max(p0[0], p1[0])
                    ymin, ymax = min(p0[1], p1[1]), max(p0[1], p1[1])
                    if xmin - 5 <= ev.x <= xmax + 5 and ymin - 5 <= ev.y <= ymax + 5:
                        best_dist = 0.0
                        best_idx = i
                        break
                    else:
                        dx = max(xmin - ev.x, 0.0, ev.x - xmax)
                        dy = max(ymin - ev.y, 0.0, ev.y - ymax)
                        dist = (dx**2 + dy**2)**0.5
                        if dist <= tolerance_px and dist < best_dist:
                            best_dist = dist
                            best_idx = i
                    continue

                # 3. Ellipse Check
                elif item.kind == 'ellipse':
                    x = item.props['x']
                    y = item.props['y']
                    w = item.props.get('w', 0.0)
                    h = item.props.get('h', 0.0)
                    p0 = self.ax.transData.transform((x - w/2, y - h/2))
                    p1 = self.ax.transData.transform((x + w/2, y + h/2))
                    xmin, xmax = min(p0[0], p1[0]), max(p0[0], p1[0])
                    ymin, ymax = min(p0[1], p1[1]), max(p0[1], p1[1])
                    if xmin - 5 <= ev.x <= xmax + 5 and ymin - 5 <= ev.y <= ymax + 5:
                        best_dist = 0.0
                        best_idx = i
                        break
                    else:
                        dx = max(xmin - ev.x, 0.0, ev.x - xmax)
                        dy = max(ymin - ev.y, 0.0, ev.y - ymax)
                        dist = (dx**2 + dy**2)**0.5
                        if dist <= tolerance_px and dist < best_dist:
                            best_dist = dist
                            best_idx = i
                    continue

                # 4. Line / Arrow Check
                elif item.kind in ('line', 'arrow'):
                    x1 = item.props['x1']
                    y1 = item.props['y1']
                    x2 = item.props['x2']
                    y2 = item.props['y2']
                    p0 = self.ax.transData.transform((x1, y1))
                    p1 = self.ax.transData.transform((x2, y2))
                    dist = self._point_to_segment_distance(ev.x, ev.y, p0[0], p0[1], p1[0], p1[1])
                    if dist <= tolerance_px and dist < best_dist:
                        best_dist = dist
                        best_idx = i
                    continue

                # 5. Callout Check
                elif item.kind == 'callout':
                    x = item.props['x']
                    y = item.props['y']
                    tx = item.props['tx']
                    ty = item.props['ty']
                    p0 = self.ax.transData.transform((x, y))
                    p1 = self.ax.transData.transform((tx, ty))
                    dist = self._point_to_segment_distance(ev.x, ev.y, p0[0], p0[1], p1[0], p1[1])
                    if dist <= tolerance_px and dist < best_dist:
                        best_dist = dist
                        best_idx = i
                    continue
            except Exception:
                continue
        return best_idx

    # --- resize handles ---
    def _handle_points(self, item: AnnotationItem) -> List[Tuple[str, float, float]]:
        """(name, x, y) grab points for resizing ``item`` (data coords)."""
        p = item.props
        if item.kind in ('line', 'arrow'):
            return [('p1', p['x1'], p['y1']), ('p2', p['x2'], p['y2'])]
        if item.kind == 'rect':
            x, y = p['x'], p['y']
            w, h = p.get('w', 0.0), p.get('h', 0.0)
            return [('c00', x, y), ('c10', x + w, y),
                    ('c01', x, y + h), ('c11', x + w, y + h)]
        if item.kind == 'ellipse':
            x, y = p['x'], p['y']
            w, h = p.get('w', 0.0), p.get('h', 0.0)
            return [('c00', x - w / 2, y - h / 2), ('c10', x + w / 2, y - h / 2),
                    ('c01', x - w / 2, y + h / 2), ('c11', x + w / 2, y + h / 2)]
        if item.kind == 'callout':
            return [('tip', p['x'], p['y']), ('text', p['tx'], p['ty'])]
        return []  # text resizes via font size, not handles

    def _handle_at(self, ev, tolerance_px: float = 8.0) -> Optional[str]:
        """Name of the selected item's handle under the cursor, if any."""
        if (self.selected_index is None
                or self.selected_index >= len(self.items)
                or ev.x is None or ev.y is None):
            return None
        try:
            for name, hx, hy in self._handle_points(self.items[self.selected_index]):
                px, py = self.ax.transData.transform((hx, hy))
                if ((ev.x - px) ** 2 + (ev.y - py) ** 2) ** 0.5 <= tolerance_px:
                    return name
        except Exception:
            pass
        return None

    def _apply_resize(self, handle: str, mx, my) -> None:
        """Recompute the selected item's geometry with ``handle`` at (mx, my)."""
        if mx is None or my is None or self._resize_orig is None:
            return
        idx = self.selected_index
        if idx is None or idx >= len(self.items):
            return
        item = self.items[idx]
        a = self.artists[idx]
        o = self._resize_orig
        try:
            if item.kind in ('line', 'arrow'):
                if handle == 'p1':
                    item.props['x1'], item.props['y1'] = mx, my
                else:
                    item.props['x2'], item.props['y2'] = mx, my
                if item.kind == 'line':
                    a.set_data([item.props['x1'], item.props['x2']],
                               [item.props['y1'], item.props['y2']])
                else:
                    a.set_positions((item.props['x1'], item.props['y1']),
                                    (item.props['x2'], item.props['y2']))
            elif item.kind == 'rect':
                # The dragged corner follows the mouse; the opposite corner
                # stays anchored.
                anchors = {
                    'c00': (o['x'] + o['w'], o['y'] + o['h']),
                    'c10': (o['x'], o['y'] + o['h']),
                    'c01': (o['x'] + o['w'], o['y']),
                    'c11': (o['x'], o['y']),
                }
                ax_, ay_ = anchors[handle]
                item.props['x'], item.props['y'] = ax_, ay_
                item.props['w'], item.props['h'] = mx - ax_, my - ay_
                a.set_xy((ax_, ay_))
                a.set_width(item.props['w'])
                a.set_height(item.props['h'])
            elif item.kind == 'ellipse':
                anchors = {
                    'c00': (o['x'] + o['w'] / 2, o['y'] + o['h'] / 2),
                    'c10': (o['x'] - o['w'] / 2, o['y'] + o['h'] / 2),
                    'c01': (o['x'] + o['w'] / 2, o['y'] - o['h'] / 2),
                    'c11': (o['x'] - o['w'] / 2, o['y'] - o['h'] / 2),
                }
                ax_, ay_ = anchors[handle]
                item.props['x'] = (ax_ + mx) / 2
                item.props['y'] = (ay_ + my) / 2
                item.props['w'] = abs(mx - ax_)
                item.props['h'] = abs(my - ay_)
                a.center = (item.props['x'], item.props['y'])
                a.width = item.props['w']
                a.height = item.props['h']
            elif item.kind == 'callout':
                if handle == 'tip':
                    item.props['x'], item.props['y'] = mx, my
                    a.xy = (mx, my)
                else:
                    item.props['tx'], item.props['ty'] = mx, my
                    a.set_position((mx, my))
        except Exception:
            logging.getLogger(__name__).debug("annotation resize failed", exc_info=True)

    def _constrain_creation(self, ev, x0, y0, x1, y1):
        """Shift while drawing: lines/arrows snap to 45° steps, rect/ellipse
        become square/circular — computed in display space so it looks right
        regardless of the data aspect ratio."""
        key = str(getattr(ev, 'key', '') or '')
        if 'shift' not in key or x1 is None or y1 is None:
            return x1, y1
        if self.mode not in ('line', 'arrow', 'rect', 'ellipse'):
            return x1, y1
        try:
            import math
            p0x, p0y = self.ax.transData.transform((x0, y0))
            p1x, p1y = self.ax.transData.transform((x1, y1))
            dx, dy = p1x - p0x, p1y - p0y
            if self.mode in ('line', 'arrow'):
                angle = math.atan2(dy, dx)
                snapped = round(angle / (math.pi / 4)) * (math.pi / 4)
                r = math.hypot(dx, dy)
                dx, dy = r * math.cos(snapped), r * math.sin(snapped)
            else:  # rect/ellipse → square/circle on screen
                m = max(abs(dx), abs(dy))
                dx = math.copysign(m, dx if dx != 0 else 1.0)
                dy = math.copysign(m, dy if dy != 0 else 1.0)
            inv = self.ax.transData.inverted()
            cx, cy = inv.transform((p0x + dx, p0y + dy))
            return float(cx), float(cy)
        except Exception:
            return x1, y1

    # --- context menu (right-click on an item) ---
    def _build_context_menu(self, idx: int) -> "QMenu":
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        it = self.items[idx] if idx < len(self.items) else None
        if it is not None and it.kind in ('text', 'callout'):
            menu.addAction("Edit Text…", lambda: self._start_inline_edit(idx))
            menu.addSeparator()
        menu.addAction("Duplicate\tCtrl+D", lambda: self.duplicate_selected())
        menu.addSeparator()
        menu.addAction("Bring to Front\tPgUp", lambda: self.bring_to_front(idx))
        menu.addAction("Send to Back\tPgDn", lambda: self.send_to_back(idx))
        menu.addSeparator()
        menu.addAction("Delete\tDel", lambda: self.delete_selected())
        return menu

    def _show_context_menu(self, idx: int) -> None:
        try:
            if not isinstance(self.fig.canvas, QWidget):
                return  # headless canvas — nothing to pop up
            from PySide6.QtGui import QCursor
            menu = self._build_context_menu(idx)
            menu.exec(QCursor.pos())
        except Exception:
            logging.getLogger(__name__).debug("annotation context menu failed", exc_info=True)

    def _update_selector(self) -> None:
        for attr in ('_selector_artist', '_handle_artist'):
            artist = getattr(self, attr, None)
            if artist is not None:
                try:
                    artist.remove()
                except Exception:
                    pass
                setattr(self, attr, None)

        if self.selected_index is not None and self.selected_index < len(self.items):
            item = self.items[self.selected_index]
            try:
                if item.kind == 'rect':
                    x = item.props['x']
                    y = item.props['y']
                    w = item.props['w']
                    h = item.props['h']
                    p0 = (x, y)
                elif item.kind == 'ellipse':
                    w = item.props['w']
                    h = item.props['h']
                    x = item.props['x']
                    y = item.props['y']
                    p0 = (x - w/2, y - h/2)
                elif item.kind in ('line', 'arrow'):
                    x1 = item.props['x1']
                    y1 = item.props['y1']
                    x2 = item.props['x2']
                    y2 = item.props['y2']
                    x = min(x1, x2)
                    y = min(y1, y2)
                    w = abs(x2 - x1)
                    h = abs(y2 - y1)
                    p0 = (x, y)
                elif item.kind == 'callout':
                    x = item.props['x']
                    y = item.props['y']
                    tx = item.props['tx']
                    ty = item.props['ty']
                    px = min(x, tx)
                    py = min(y, ty)
                    w = abs(tx - x)
                    h = abs(ty - y)
                    p0 = (px, py)
                else:  # text — hug the rendered glyphs, not a % of the axes
                    try:
                        a = self.artists[self.selected_index]
                        bbox = a.get_window_extent(self.fig.canvas.get_renderer())
                        inv = self.ax.transData.inverted()
                        x0d, y0d = inv.transform((bbox.xmin - 4, bbox.ymin - 4))
                        x1d, y1d = inv.transform((bbox.xmax + 4, bbox.ymax + 4))
                        p0 = (min(x0d, x1d), min(y0d, y1d))
                        w = abs(x1d - x0d)
                        h = abs(y1d - y0d)
                    except Exception:
                        x = item.props['x']
                        y = item.props['y']
                        x_lim = self.ax.get_xlim()
                        y_lim = self.ax.get_ylim()
                        w = (x_lim[1] - x_lim[0]) * 0.1
                        h = (y_lim[1] - y_lim[0]) * 0.05
                        p0 = (x - w*0.1, y - h*0.5)

                self._selector_artist = Rectangle(p0, w, h, fill=False, edgecolor='#4F9CF9',
                                                  linestyle='--', linewidth=1.5, zorder=99)
                self.ax.add_patch(self._selector_artist)
            except Exception:
                pass
            # Grab handles (small squares) so the shape can be resized, not
            # just moved — endpoints for lines/arrows, corners for boxes.
            try:
                points = self._handle_points(item)
                if points:
                    from matplotlib.lines import Line2D
                    xs = [hp[1] for hp in points]
                    ys = [hp[2] for hp in points]
                    self._handle_artist = Line2D(
                        xs, ys, linestyle='None', marker='s', markersize=6,
                        markerfacecolor='#4F9CF9', markeredgecolor='white',
                        markeredgewidth=1.0, zorder=100)
                    self.ax.add_line(self._handle_artist)
            except Exception:
                pass
        self.fig.canvas.draw_idle()

    def _begin_text_entry(self, idx: int) -> None:
        """Open the inline editor for a freshly placed text (Qt canvases only).

        Headless/Agg canvases (tests, export) skip this silently — no modal
        fallback, so nothing can hang without a display.
        """
        try:
            if isinstance(self.fig.canvas, QWidget):
                self._start_inline_edit(idx)
        except Exception:
            logging.getLogger(__name__).debug("auto text entry skipped", exc_info=True)

    def _start_inline_edit(self, idx: int) -> None:
        if idx >= len(self.artists):
            return
        a = self.artists[idx]
        it = self.items[idx]

        from matplotlib.text import Text as MplText
        if not isinstance(a, MplText):
            return

        try:
            h_canvas = self.fig.canvas.height()

            try:
                bbox = a.get_window_extent(self.fig.canvas.get_renderer())
                qt_x = bbox.xmin
                qt_y = h_canvas - bbox.ymax
                qt_w = bbox.width
                qt_h = bbox.height
            except Exception:
                tx, ty = a.get_position()
                px, py = self.ax.transData.transform((tx, ty))
                qt_x = px
                qt_y = h_canvas - py
                qt_w = 80
                qt_h = 20

            edit = _InlineTextEdit(self.fig.canvas)
            edit.setText(it.props.get('s', 'Text'))
            edit.setGeometry(int(qt_x - 5), int(qt_y - 2), int(max(qt_w + 20, 100)), int(max(qt_h + 6, 25)))
            edit.setFont(self.fig.canvas.font())
            edit.show()
            edit.setFocus()
            edit.selectAll()

            # Enter fires returnPressed AND the subsequent focus-out fires
            # editingFinished — guard so the edit commits exactly once.
            state = {'done': False}

            def commit():
                if state['done']:
                    return
                state['done'] = True
                text = edit.text().strip()
                if text and text != it.props.get('s'):
                    self._snapshot()
                    it.props['s'] = text
                    a.set_text(text)
                    self._update_selector()
                    self.fig.canvas.draw_idle()
                    self.changed.emit()
                edit.deleteLater()

            def cancel():
                if state['done']:
                    return
                state['done'] = True
                edit.deleteLater()

            edit.returnPressed.connect(commit)
            edit.editingFinished.connect(commit)
            edit.cancelled.connect(cancel)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Inline edit failed, fallback to input dialog: {e}", exc_info=True)
            current = it.props.get('s', 'Text')
            parent = self.parent() if hasattr(self, 'parent') else None
            text, ok = QInputDialog.getText(parent, "Edit Text", "Content:", text=current)
            if ok:
                self._snapshot()
                it.props['s'] = text
                a.set_text(text)
                self.fig.canvas.draw_idle()
                self.changed.emit()

    def _update_artist_style(self, idx: int) -> None:
        if idx >= len(self.artists):
            return
        it = self.items[idx]
        st = it.style
        a = self.artists[idx]
        try:
            if hasattr(a, 'set_edgecolor'):
                a.set_edgecolor(st.stroke)
            if hasattr(a, 'set_facecolor'):
                a.set_facecolor(st.fill)
            if hasattr(a, 'set_linewidth'):
                a.set_linewidth(st.lw)
            if hasattr(a, 'set_alpha'):
                a.set_alpha(st.alpha)
            if hasattr(a, 'set_zorder'):
                a.set_zorder(st.zorder)
                
            from matplotlib.text import Text as MplText
            from matplotlib.text import Annotation as MplAnnotation
            
            if isinstance(a, MplAnnotation):
                a.set_color(st.stroke)
                a.set_fontsize(st.fontsize)
                kw = self._text_kwargs_for_style(st)
                if 'fontproperties' in kw:
                    a.set_fontproperties(kw['fontproperties'])
                if a.get_bbox_patch():
                    bbox_patch = a.get_bbox_patch()
                    if st.fill != "#00000000":
                        bbox_patch.set_facecolor(st.fill)
                        bbox_patch.set_edgecolor(st.stroke)
                        bbox_patch.set_linewidth(st.lw)
                        bbox_patch.set_alpha(st.alpha)
                    else:
                        bbox_patch.set_alpha(0.0)
            elif isinstance(a, MplText):
                a.set_color(st.stroke)
                a.set_fontsize(st.fontsize)
                kw = self._text_kwargs_for_style(st)
                if 'fontproperties' in kw:
                    a.set_fontproperties(kw['fontproperties'])
                    
            if isinstance(a, FancyArrowPatch):
                a.set_edgecolor(st.stroke)
                a.set_facecolor(st.stroke)
                a.set_linewidth(st.lw)
                
            from matplotlib.lines import Line2D
            if isinstance(a, Line2D):
                a.set_color(st.stroke)
                a.set_linewidth(st.lw)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Update artist style failed: {e}", exc_info=True)
        self.fig.canvas.draw_idle()

    # --- helpers ---
    def _text_kwargs(self) -> Dict[str, Any]:
        """Build kwargs for ax.text ensuring Thai-capable font."""
        return self._text_kwargs_for_style(self._style)

    def _text_kwargs_for_style(self, st: AnnotationStyle) -> Dict[str, Any]:
        from matplotlib.font_manager import FontProperties, findfont
        import os
        kw: Dict[str, Any] = {
            'fontsize': st.fontsize,
            'fontweight': 'bold' if st.bold else 'normal',
            'fontstyle': 'italic' if st.italic else 'normal',
            'color': st.stroke,
            'zorder': st.zorder,
        }
        families: List[str] = []
        if st.font:
            families.append(st.font)
        base = os.path.dirname(__file__)
        asset_ttf = os.path.join(base, 'assets', 'fonts', 'THSarabunNew.ttf')
        families += [
            'Noto Sans Thai', 'TH Sarabun New', 'Sarabun', 'Tahoma', 'Segoe UI', 'Arial Unicode MS', 'Arial'
        ]
        for fam in families:
            try:
                path = findfont(FontProperties(family=fam), fallback_to_default=False)
                if path:
                    kw['fontproperties'] = FontProperties(family=fam)
                    return kw
            except Exception:
                continue
        if os.path.isfile(asset_ttf):
            try:
                kw['fontproperties'] = FontProperties(fname=asset_ttf)
                return kw
            except Exception:
                pass
        return kw

    def _nearest_text_index(self, ev, max_px: int = 12) -> Optional[int]:
        """Find nearest Text artist to the mouse event position (in pixels)."""
        best = None
        best_d = float('inf')
        try:
            from matplotlib.text import Text as MplText
        except Exception:
            return None
        for i, a in enumerate(self.artists):
            try:
                if not isinstance(a, MplText):
                    continue
                ax = a.axes
                x, y = a.get_position()
                px, py = ax.transData.transform((x, y))
                dx, dy = (ev.x - px), (ev.y - py)
                d = (dx*dx + dy*dy) ** 0.5
                if d < best_d:
                    best_d = d
                    best = i
            except Exception:
                continue
        if best is not None and best_d <= max_px:
            return best
        return None


class AnnotationStyleDock(QDockWidget):
    style_applied = Signal(AnnotationStyle)

    def __init__(self, parent=None):
        super().__init__("Annotation Style", parent)
        self.setObjectName("AnnotationStyleDock")
        self._loading = False
        
        w = QWidget()
        self.setWidget(w)
        lay = QFormLayout(w)

        # Stroke & fill
        self.btnStroke = QPushButton("Stroke…")
        self.btnFill = QPushButton("Fill…")
        self._stroke = QColor("#ffffff")
        self._fill = QColor(0,0,0,0)
        self.btnStroke.clicked.connect(lambda: self._pick_color(True))
        self.btnFill.clicked.connect(lambda: self._pick_color(False))
        lay.addRow("Colors:", self._hbox(self.btnStroke, self.btnFill))

        # Width, alpha
        self.spinLW = QSpinBox()
        self.spinLW.setRange(1, 20)
        self.spinLW.setValue(2)
        self.spinAlpha = QSpinBox()
        self.spinAlpha.setRange(0, 100)
        self.spinAlpha.setValue(100)
        lay.addRow("Line Width:", self.spinLW)
        lay.addRow("Alpha (%):", self.spinAlpha)

        # Font
        self.cbFont = QComboBox()
        self.cbFont.addItems(["", "Noto Sans Thai", "TH Sarabun New", "Sarabun", "Tahoma", "Segoe UI", "Arial", "DejaVu Sans"])
        self.spinFS = QSpinBox()
        self.spinFS.setRange(6, 72)
        self.spinFS.setValue(11)
        self.chkBold = QCheckBox("Bold")
        self.chkItalic = QCheckBox("Italic")
        lay.addRow("Font Family:", self.cbFont)
        lay.addRow("Font Size:", self.spinFS)
        lay.addRow("Weight:", self._hbox(self.chkBold, self.chkItalic))

        # Arrow style & zorder
        self.cbArrow = QComboBox()
        self.cbArrow.addItems(["-|>", "->", "<->", "fancy"])
        self.spinZ = QSpinBox()
        self.spinZ.setRange(0, 50)
        self.spinZ.setValue(3)
        lay.addRow("Arrow:", self.cbArrow)
        lay.addRow("Z-Order:", self.spinZ)

        # Connect controls for live updates
        self.spinLW.valueChanged.connect(self._emit)
        self.spinAlpha.valueChanged.connect(self._emit)
        self.cbFont.currentTextChanged.connect(self._emit)
        self.spinFS.valueChanged.connect(self._emit)
        self.chkBold.stateChanged.connect(self._emit)
        self.chkItalic.stateChanged.connect(self._emit)
        self.cbArrow.currentTextChanged.connect(self._emit)
        self.spinZ.valueChanged.connect(self._emit)

        # Apply / Reset (Retained for manual override/backwards compatibility)
        btns = QHBoxLayout()
        self.btnApply = QPushButton("Apply")
        self.btnReset = QPushButton("Reset")
        btns.addWidget(self.btnApply)
        btns.addWidget(self.btnReset)
        lay.addRow("", self._wrap(btns))

        self.btnApply.clicked.connect(self._emit)
        self.btnReset.clicked.connect(self._reset)

    def _hbox(self, *w):
        box = QHBoxLayout()
        cont = QWidget()
        cont.setLayout(box)
        for ww in w: 
            box.addWidget(ww)
        box.addStretch(1)
        return cont

    def _wrap(self, layout):
        cont = QWidget()
        cont.setLayout(layout)
        return cont

    def _pick_color(self, stroke: bool):
        c = QColorDialog.getColor(self._stroke if stroke else self._fill, self)
        if c.isValid():
            if stroke: 
                self._stroke = c
            else: 
                self._fill = c
            self._emit()

    def set_style_values(self, st: AnnotationStyle) -> None:
        self._loading = True
        try:
            self._stroke = QColor(st.stroke)
            self._fill = QColor(st.fill)
            self.spinLW.setValue(int(st.lw))
            self.spinAlpha.setValue(int(st.alpha * 100))
            self.cbFont.setCurrentText(st.font)
            self.spinFS.setValue(st.fontsize)
            self.chkBold.setChecked(st.bold)
            self.chkItalic.setChecked(st.italic)
            self.cbArrow.setCurrentText(st.arrowstyle)
            self.spinZ.setValue(st.zorder)
        finally:
            self._loading = False

    def _reset(self):
        self._loading = True
        try:
            self._stroke = QColor("#ffffff")
            self._fill = QColor(0,0,0,0)
            self.spinLW.setValue(2)
            self.spinAlpha.setValue(100)
            self.cbFont.setCurrentText("")
            self.spinFS.setValue(11)
            self.chkBold.setChecked(False)
            self.chkItalic.setChecked(False)
            self.cbArrow.setCurrentText("-|>")
            self.spinZ.setValue(3)
        finally:
            self._loading = False
        self._emit()

    def _emit(self):
        if self._loading:
            return
        st = AnnotationStyle(
            stroke=self._stroke.name(QColor.HexArgb) if self._stroke.alpha() < 255 else self._stroke.name(),
            fill=self._fill.name(QColor.HexArgb) if self._fill.alpha() < 255 else self._fill.name(),
            lw=float(self.spinLW.value()),
            alpha=float(self.spinAlpha.value())/100.0,
            font=self.cbFont.currentText(),
            fontsize=int(self.spinFS.value()),
            bold=self.chkBold.isChecked(),
            italic=self.chkItalic.isChecked(),
            arrowstyle=self.cbArrow.currentText(),
            zorder=int(self.spinZ.value())
        )
        self.style_applied.emit(st)


class AnnotationListDialog(QDialog):
    def __init__(self, mgr: AnnotationManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Annotations")
        self.mgr = mgr
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        lay.addWidget(self.list)
        self._reload()
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btnDel = QPushButton("Delete")
        btns.addButton(btnDel, QDialogButtonBox.ActionRole)
        lay.addWidget(btns)
        btns.rejected.connect(self.reject)
        btnDel.clicked.connect(self._delete)

    def _reload(self):
        self.list.clear()
        for i, it in enumerate(self.mgr.items):
            txt = f"{i+1}. {it.kind}"
            self.list.addItem(QListWidgetItem(txt))

    def _delete(self):
        row = self.list.currentRow()
        if row >= 0 and row < len(self.mgr.artists):
            try:
                self.mgr.artists[row].remove()
            except Exception:
                logging.getLogger(__name__).debug("annotation artist remove failed", exc_info=True)
            del self.mgr.items[row]
            del self.mgr.artists[row]
            self.mgr.clear_selection()
            self.mgr.fig.canvas.draw_idle()
            self._reload()
