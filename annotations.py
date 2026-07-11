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
    QListWidget, QListWidgetItem, QDialogButtonBox, QInputDialog
)

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle, Ellipse, FancyArrow


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
        # Default annotation font to current Matplotlib family (ensures Thai if configured)
        try:
            import matplotlib
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

    # -------- public API --------
    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        self.changed.emit()

    def set_mode(self, mode: Optional[str]) -> None:
        self.mode = mode
        self.changed.emit()

    def set_style(self, style: AnnotationStyle) -> None:
        self._style = style
        self.selection_changed.emit()

    def get_style(self) -> AnnotationStyle:
        return self._style

    def clear(self) -> None:
        for a in list(self.artists):
            try:
                a.remove()
            except Exception:
                pass
        self.items.clear(); self.artists.clear()
        self.fig.canvas.draw_idle(); self.changed.emit()

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
        self.fig.canvas.draw_idle(); self.changed.emit()

    # --- undo/redo ---
    def _snapshot(self) -> None:
        self._undo.append(self.to_json()); self._redo.clear()

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
    def _on_press(self, ev):
        # Accept clicks on whatever axes is under the cursor; axes can be recreated during plotting
        if not self.enabled or ev.inaxes is None:
            return
        # Update target axes dynamically in case canvas recreated the axes
        if ev.inaxes is not self.ax:
            self.ax = ev.inaxes

        # Double-click near text → edit content
        if getattr(ev, 'dblclick', False):
            idx = self._nearest_text_index(ev)
            if idx is not None:
                current = self.items[idx].props.get('s', 'Text')
                try:
                    parent = self.parent() if hasattr(self, 'parent') else None
                except Exception:
                    parent = None
                text, ok = QInputDialog.getText(parent, "Edit Text", "Content:", text=current)
                if ok:
                    self.items[idx].props['s'] = text
                    try:
                        self.artists[idx].set_text(text)
                    except Exception:
                        pass
                    self.fig.canvas.draw_idle()
                return
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
            # placeholder artist created on press, resized on drag
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
            else:  # arrow / callout
                a = FancyArrow(ev.xdata, ev.ydata, 1e-6, 1e-6,
                               width=0.001, head_width=0.02, head_length=0.03,
                               color=self._style.stroke, linewidth=self._style.lw,
                               alpha=self._style.alpha, zorder=self._style.zorder)
                self.ax.add_patch(a)
                it = AnnotationItem('arrow', {'x1': ev.xdata, 'y1': ev.ydata, 'x2': ev.xdata, 'y2': ev.ydata}, self._style)
            self.items.append(it); self.artists.append(a); self._current_artist = a
            self.fig.canvas.draw_idle()

    def _on_motion(self, ev):
        if not self.enabled or not self._press_pt or ev.inaxes is None or self._current_artist is None:
            return
        x0, y0 = self._press_pt
        x1, y1 = ev.xdata, ev.ydata
        if hasattr(self._current_artist, 'set_width') and hasattr(self._current_artist, 'set_height'):
            # Rectangle
            try:
                self._current_artist.set_width(x1 - x0)
                self._current_artist.set_height(y1 - y0)
            except Exception:
                pass
        elif hasattr(self._current_artist, 'center') and hasattr(self._current_artist, 'width'):
            # Ellipse
            self._current_artist.width = abs(x1 - x0)
            self._current_artist.height = abs(y1 - y0)
            self._current_artist.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        elif isinstance(self._current_artist, FancyArrow):
            # Arrow: recreate to update geometry
            try:
                self._current_artist.remove()
            except Exception:
                pass
            a = FancyArrow(x0, y0, x1 - x0, y1 - y0, width=0.001, head_width=0.02, head_length=0.03,
                           color=self._style.stroke, linewidth=self._style.lw,
                           alpha=self._style.alpha, zorder=self._style.zorder)
            self.ax.add_patch(a)
            self.artists[-1] = a
            self._current_artist = a
        else:
            # Line2D (from ax.plot)
            try:
                from matplotlib.lines import Line2D
                if isinstance(self._current_artist, Line2D):
                    self._current_artist.set_data([x0, x1], [y0, y1])
                else:
                    # Fallback: do nothing
                    pass
            except Exception:
                pass
        self.fig.canvas.draw_idle()

    def _on_release(self, ev):
        if not self.enabled:
            return
        self._press_pt = None
        self._current_artist = None

    # --- rebuild artists from items ---
    def _create_artist_from_item(self, it: AnnotationItem):
        st = it.style
        if it.kind == 'text':
            # Use resolved Thai-capable FontProperties
            a = self.ax.text(it.props['x'], it.props['y'], it.props.get('s','Text'),
                             **self._text_kwargs())
            self.artists.append(a)
        elif it.kind == 'rect':
            a = Rectangle((it.props['x'], it.props['y']), it.props.get('w',0.0), it.props.get('h',0.0),
                          linewidth=st.lw, edgecolor=st.stroke, facecolor=st.fill, alpha=st.alpha, zorder=st.zorder)
            self.ax.add_patch(a); self.artists.append(a)
        elif it.kind == 'ellipse':
            a = Ellipse((it.props['x'], it.props['y']), it.props.get('w',0.0), it.props.get('h',0.0),
                        linewidth=st.lw, edgecolor=st.stroke, facecolor=st.fill, alpha=st.alpha, zorder=st.zorder)
            self.ax.add_patch(a); self.artists.append(a)
        elif it.kind == 'line':
            a = self.ax.plot([it.props['x1'], it.props['x2']], [it.props['y1'], it.props['y2']],
                             color=st.stroke, linewidth=st.lw, alpha=st.alpha, zorder=st.zorder)[0]
            self.artists.append(a)
        elif it.kind == 'arrow':
            a = FancyArrow(it.props['x1'], it.props['y1'], it.props['x2']-it.props['x1'], it.props['y2']-it.props['y1'],
                           width=0.001, head_width=0.02, head_length=0.03,
                           color=st.stroke, linewidth=st.lw, alpha=st.alpha, zorder=st.zorder)
            self.ax.add_patch(a); self.artists.append(a)

    # --- helpers ---
    def _text_kwargs(self) -> Dict[str, Any]:
        """Build kwargs for ax.text ensuring Thai-capable font."""
        from matplotlib.font_manager import FontProperties, findfont
        import os
        # Base style
        st = self._style
        kw: Dict[str, Any] = {
            'fontsize': st.fontsize,
            'fontweight': 'bold' if st.bold else 'normal',
            'fontstyle': 'italic' if st.italic else 'normal',
            'color': st.stroke,
            'zorder': st.zorder,
        }
        # Resolve font: prefer explicit style font; then bundled Thai fonts; then common system fonts
        families: List[str] = []
        if st.font:
            families.append(st.font)
        base = os.path.dirname(__file__)
        asset_ttf = os.path.join(base, 'assets', 'fonts', 'THSarabunNew.ttf')
        families += [
            'Noto Sans Thai', 'TH Sarabun New', 'Sarabun', 'Tahoma', 'Segoe UI', 'Arial Unicode MS', 'Arial'
        ]
        # Pick the first available by family name (prefer explicit style first)
        for fam in families:
            try:
                path = findfont(FontProperties(family=fam), fallback_to_default=False)
                if path:
                    kw['fontproperties'] = FontProperties(family=fam)
                    return kw
            except Exception:
                continue
        # If style family not resolved, try bundled Sarabun as direct file
        if os.path.isfile(asset_ttf):
            try:
                kw['fontproperties'] = FontProperties(fname=asset_ttf)
                return kw
            except Exception:
                pass
        # Fallback to default rcParams
        return kw

    def _nearest_text_index(self, ev, max_px: int = 12) -> Optional[int]:
        """Find nearest Text artist to the mouse event position (in pixels)."""
        best = None; best_d = float('inf')
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
                    best_d = d; best = i
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
        w = QWidget(); self.setWidget(w)
        lay = QFormLayout(w)

        # Stroke & fill
        self.btnStroke = QPushButton("Stroke…"); self.btnFill = QPushButton("Fill…")
        self._stroke = QColor("#ffffff"); self._fill = QColor(0,0,0,0)
        self.btnStroke.clicked.connect(lambda: self._pick_color(True))
        self.btnFill.clicked.connect(lambda: self._pick_color(False))
        lay.addRow("Colors:", self._hbox(self.btnStroke, self.btnFill))

        # Width, alpha
        self.spinLW = QSpinBox(); self.spinLW.setRange(1, 20); self.spinLW.setValue(2)
        self.spinAlpha = QSpinBox(); self.spinAlpha.setRange(0, 100); self.spinAlpha.setValue(100)
        lay.addRow("Line Width:", self.spinLW)
        lay.addRow("Alpha (%):", self.spinAlpha)

        # Font
        self.cbFont = QComboBox()
        self.cbFont.addItems(["", "Noto Sans Thai", "TH Sarabun New", "Sarabun", "Tahoma", "Segoe UI", "Arial", "DejaVu Sans"])
        self.spinFS = QSpinBox(); self.spinFS.setRange(6, 72); self.spinFS.setValue(11)
        self.chkBold = QCheckBox("Bold"); self.chkItalic = QCheckBox("Italic")
        lay.addRow("Font Family:", self.cbFont)
        lay.addRow("Font Size:", self.spinFS)
        lay.addRow("Weight:", self._hbox(self.chkBold, self.chkItalic))

        # Arrow style & zorder
        self.cbArrow = QComboBox(); self.cbArrow.addItems(["-|>", "->", "<->", "fancy"])
        self.spinZ = QSpinBox(); self.spinZ.setRange(0, 50); self.spinZ.setValue(3)
        lay.addRow("Arrow:", self.cbArrow)
        lay.addRow("Z-Order:", self.spinZ)

        # Apply / Reset
        btns = QHBoxLayout();
        self.btnApply = QPushButton("Apply")
        self.btnReset = QPushButton("Reset")
        btns.addWidget(self.btnApply); btns.addWidget(self.btnReset)
        lay.addRow("", self._wrap(btns))

        self.btnApply.clicked.connect(self._emit)
        self.btnReset.clicked.connect(self._reset)

    def _hbox(self, *w):
        box = QHBoxLayout();
        cont = QWidget(); cont.setLayout(box)
        for ww in w: box.addWidget(ww)
        box.addStretch(1)
        return cont

    def _wrap(self, layout):
        cont = QWidget(); cont.setLayout(layout); return cont

    def _pick_color(self, stroke: bool):
        c = QColorDialog.getColor(self._stroke if stroke else self._fill, self)
        if c.isValid():
            if stroke: self._stroke = c
            else: self._fill = c

    def _reset(self):
        self._stroke = QColor("#ffffff"); self._fill = QColor(0,0,0,0)
        self.spinLW.setValue(2); self.spinAlpha.setValue(100)
        self.cbFont.setCurrentText(""); self.spinFS.setValue(11)
        self.chkBold.setChecked(False); self.chkItalic.setChecked(False)
        self.cbArrow.setCurrentText("-|>"); self.spinZ.setValue(3)

    def _emit(self):
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
        self.list = QListWidget(); lay.addWidget(self.list)
        self._reload()
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btnDel = QPushButton("Delete"); btns.addButton(btnDel, QDialogButtonBox.ActionRole)
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
            del self.mgr.items[row]; del self.mgr.artists[row]
            self.mgr.fig.canvas.draw_idle(); self._reload()
