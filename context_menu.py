from __future__ import annotations
"""
Context menu manager for Matplotlib axes embedded in PySide6 Qt apps.
Provides view controls, zoom/pan, analysis hooks, annotations, and export
without adding toolbar clutter.
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List

import numpy as np
from PySide6 import QtCore, QtGui
from PySide6.QtCore import QObject, QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QApplication, QInputDialog, QMessageBox, QFileDialog

from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates


@dataclass
class _ZoomState:
    xlim: Tuple[float, float]
    ylim: Tuple[float, float]


class ContextMenuManager(QObject):
    """Attach a right‑click context menu to a Matplotlib canvas/axes.

    The manager keeps lightweight per-axes state (zoom history, overlays) and
    routes actions to existing app managers when provided (annotation/peaks/x-corr).
    """

    def __init__(self, canvas, axes: Axes,
                 main: Optional[QObject] = None,
                 annotation_mgr: Optional[QObject] = None,
                 peak_mgr: Optional[QObject] = None,
                 xcorr_mgr: Optional[QObject] = None) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.ax = axes
        self.main = main
        # managers (optional)
        self.ann = annotation_mgr
        self.peaks = peak_mgr
        self.xcorr = xcorr_mgr

        self._press: Optional[Tuple[float, float]] = None
        self._measure_first: Optional[Tuple[float, float]] = None
        self._zoom_hist: List[_ZoomState] = []
        self._overlays: List[Any] = []
        self._box_patch: Optional[Rectangle] = None
        self._grid_on: bool = False
        self._legend_visible: bool = False
        self._minor_on: bool = False
        self._max_zoom_hist: int = 32

        self._adopt_axes(axes)

        # mpl event hookup
        self._cid_press = self.canvas.mpl_connect('button_press_event', self._on_mpl_press)
        self._cid_release = self.canvas.mpl_connect('button_release_event', self._on_mpl_release)
        self._cid_motion = self.canvas.mpl_connect('motion_notify_event', self._on_mpl_motion)

    def _adopt_axes(self, axes: Axes) -> None:
        """Adopt the provided axes and refresh cached state."""
        self.ax = axes
        self._zoom_hist = [_ZoomState(self.ax.get_xlim(), self.ax.get_ylim())]
        self._grid_on = self._compute_grid_state(self.ax)
        self._legend_visible = self._legend_is_visible(self.ax)
        self._minor_on = self._minor_ticks_active(self.ax)

    def _compute_grid_state(self, axes: Axes) -> bool:
        try:
            return any(line.get_visible() for line in axes.xaxis.get_gridlines()) or any(line.get_visible() for line in axes.yaxis.get_gridlines())
        except Exception:
            return False

    def _minor_ticks_active(self, axes: Axes) -> bool:
        try:
            return any(line.get_visible() for line in axes.xaxis.get_minorticklines()) or any(line.get_visible() for line in axes.yaxis.get_minorticklines())
        except Exception:
            return False

    def _legend_is_visible(self, axes: Axes) -> bool:
        leg = axes.get_legend()
        return bool(leg and leg.get_visible())

    def _refresh_axis_state(self) -> None:
        self._grid_on = self._compute_grid_state(self.ax)
        self._legend_visible = self._legend_is_visible(self.ax)
        self._minor_on = self._minor_ticks_active(self.ax)

    # ---------- event plumbing ----------
    def _on_mpl_press(self, ev):
        # Accept clicks on any axes inside this figure; keep current axes updated
        if ev.inaxes is None:
            return
        if ev.inaxes is not self.ax:
            self._adopt_axes(ev.inaxes)
        else:
            self._refresh_axis_state()
        if ev.button == 3:  # right-click
            self._show_menu(QtGui.QCursor.pos(), ev)
        elif ev.button == 1 and self._box_patch is not None:
            # start box zoom drag
            self._press = (ev.xdata, ev.ydata)
        elif ev.button == 1 and self._measure_first is not None:
            # second point for measurement
            p1 = self._measure_first; p2 = (ev.xdata, ev.ydata)
            self._draw_measure(p1, p2)
            self._measure_first = None

    def _on_mpl_motion(self, ev):
        if self._box_patch is not None and self._press and ev.inaxes is not None:
            if ev.inaxes is not self.ax:
                self._adopt_axes(ev.inaxes)
            else:
                self._refresh_axis_state()
            x0, y0 = self._press; x1, y1 = ev.xdata, ev.ydata
            self._update_box(x0, y0, x1, y1)
            self.canvas.draw_idle()

    def _on_mpl_release(self, ev):
        if self._box_patch is not None and self._press and ev.inaxes is not None:
            if ev.inaxes is not self.ax:
                self._adopt_axes(ev.inaxes)
            else:
                self._refresh_axis_state()
            x0, y0 = self._press; x1, y1 = ev.xdata, ev.ydata
            self._apply_box_zoom(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1))
            self._remove_box()
            self._press = None

    # ---------- menu build ----------
    def _show_menu(self, global_pos: QPoint, ev) -> None:
        menu = QMenu()
        self._refresh_axis_state()

        # A) View
        view = menu.addMenu("View")
        view.addAction("Reset View	(Home)", self._on_reset_view)
        view.addAction("Autoscale (tight)", self._on_autoscale)
        view.addAction("Toggle Grid", self._on_toggle_grid)
        view.addAction("Toggle Minor Ticks", self._on_toggle_minor)
        view.addAction("Toggle Legend", self._on_toggle_legend)

        # B) Zoom & Pan
        zp = menu.addMenu("Zoom & Pan")
        zp.addAction("Zoom In (x2)", lambda: self._on_zoom_at(ev, 0.5))
        zp.addAction("Zoom Out (÷2)", lambda: self._on_zoom_at(ev, 2.0))
        zp.addAction("Box Zoom (B)", self._on_box_zoom)
        zp.addAction("Pan Mode (P)", self._on_pan_mode)
        zp.addAction("Zoom Back", self._on_zoom_back)

        # C) Axes & Scales
        axm = menu.addMenu("Axes & Scales")
        axm.addAction("Set Axis Limits…", self._on_set_axis_limits)
        xlin = axm.addAction("X Scale: Linear"); xlin.setCheckable(True)
        xlog = axm.addAction("X Scale: Log10"); xlog.setCheckable(True)
        ylin = axm.addAction("Y Scale: Linear"); ylin.setCheckable(True)
        ylog = axm.addAction("Y Scale: Log10"); ylog.setCheckable(True)
        xlin.setChecked(self.ax.get_xscale() == 'linear'); xlog.setChecked(self.ax.get_xscale() == 'log')
        ylin.setChecked(self.ax.get_yscale() == 'linear'); ylog.setChecked(self.ax.get_yscale() == 'log')
        xlin.triggered.connect(lambda: self._on_scale_change('x', 'linear'))
        xlog.triggered.connect(lambda: self._on_scale_change('x', 'log'))
        ylin.triggered.connect(lambda: self._on_scale_change('y', 'linear'))
        ylog.triggered.connect(lambda: self._on_scale_change('y', 'log'))
        axm.addAction("Invert X", self._on_invert_x)
        axm.addAction("Invert Y", self._on_invert_y)

        # D) Cursors & Measures
        curm = menu.addMenu("Cursors & Measures")
        curm.addAction("Add Vertical Line @ x", lambda: self._add_vline(ev))
        curm.addAction("Add Horizontal Line @ y", lambda: self._add_hline(ev))
        curm.addAction("Measure Distance", self._on_measure)
        curm.addAction("Copy Coordinates (Ctrl+Shift+C)", lambda: self._copy_coords(ev))
        if self.xcorr is not None:
            act = curm.addAction("Multi-Cursor Sync")
            act.setCheckable(True); act.setChecked(getattr(self.xcorr, 'enabled', False))
            act.toggled.connect(lambda on: self.xcorr.set_enabled(on))

        # E) Annotation (if any)
        if self.ann is not None:
            annm = menu.addMenu("Annotation")
            actEn = annm.addAction("Enable Annotation Mode")
            actEn.setCheckable(True); actEn.setChecked(getattr(self.ann, 'enabled', False))
            actEn.toggled.connect(lambda on: self.ann.set_enabled(on))
            annm.addAction("Add Text…", lambda: (self.ann.set_enabled(True), self.ann.set_mode('text')))
            annm.addAction("Add Arrow", lambda: (self.ann.set_enabled(True), self.ann.set_mode('arrow')))
            annm.addAction("Add Rectangle", lambda: (self.ann.set_enabled(True), self.ann.set_mode('rect')))
            annm.addAction("Add Ellipse", lambda: (self.ann.set_enabled(True), self.ann.set_mode('ellipse')))
            if getattr(self.main, 'annStyleDock', None) is not None:
                annm.addAction("Style Dock…", lambda: self.main.annStyleDock.show())

        # F) Analysis
        anm = menu.addMenu("Analysis (Visible Range)")
        if self.peaks is not None:
            pkm = anm.addMenu("Peak Detection")
            pkm.addAction("Detect in Visible Range", self._pk_detect_range)
            actAnnot = pkm.addAction("Annotate Peaks"); actAnnot.setCheckable(True)
            actAnnot.setChecked(getattr(getattr(self.peaks, 'params', None), 'annotate', True))
            actAnnot.toggled.connect(lambda on: self._pk_annotate_toggle(on))
            if getattr(self.main, 'pkDock', None) is not None:
                pkm.addAction("Settings…", lambda: self.main.pkDock.show())
            pkm.addAction("Clear Peaks", lambda: self.peaks.clear())

        if self.xcorr is not None:
            xcm = anm.addMenu("Cross-Correlation")
            xcm.addAction("Compute A vs B in Visible Range", self._cc_compute_range)
            actLink = xcm.addAction("Link Axes by X-Time"); actLink.setCheckable(True)
            actLink.setChecked(getattr(getattr(self.xcorr, 'opt', None), 'link_axes', False))
            actLink.toggled.connect(lambda on: self.xcorr.set_link_axes(on))
            if getattr(self.main, 'ccDock', None) is not None:
                xcm.addAction("Open Cross-Correlation Panel", lambda: self.main.ccDock.show())

        # G) Export / Copy
        exm = menu.addMenu("Export / Copy")
        exm.addAction("Save Figure as PNG…", self._save_png)
        exm.addAction("Copy Figure to Clipboard", self._copy_figure)
        exm.addAction("Export Visible Range to CSV…", self._export_visible_csv)

        # H) Utilities
        utm = menu.addMenu("Utilities")
        utm.addAction("Snapshot This View", self._snapshot_view)
        recall = utm.addMenu("Recall Snapshot")
        for idx, st in enumerate(self._zoom_hist[-5:]):
            recall.addAction(f"#{idx+1} x={st.xlim} y={st.ylim}", lambda s=st: self._apply_state(s))
        utm.addAction("Clear Temporary Overlays", self._clear_overlays)

        menu.exec(global_pos)

    # ---------- view handlers ----------
    def _push_state(self):
        state = _ZoomState(self.ax.get_xlim(), self.ax.get_ylim())
        if self._zoom_hist and state == self._zoom_hist[-1]:
            return
        self._zoom_hist.append(state)
        if len(self._zoom_hist) > self._max_zoom_hist:
            self._zoom_hist.pop(0)

    def _apply_state(self, st: _ZoomState):
        self.ax.set_xlim(*st.xlim); self.ax.set_ylim(*st.ylim)
        self.canvas.draw_idle()

    def _on_reset_view(self):
        # "Reset View" = show all data (like Origin's Rescale to Show All).
        # Autoscaling from the axes' data limits is robust; the old code restored
        # a stored _zoom_hist[0] snapshot which can be stale — e.g. captured
        # while the axes was still empty at (0,1) before the data was plotted —
        # so a reset pushed the data off-screen and the graph "disappeared".
        # set_xlim/ylim only change the *view* limits, so dataLim still holds the
        # full extent of every artist (lines AND scatter/collections).
        try:
            self.ax.autoscale(enable=True, axis="both", tight=False)
            self.ax.autoscale_view()
        except Exception:
            if self._zoom_hist:
                self._apply_state(self._zoom_hist[0])
        # re-baseline "home" to the true full-data view
        self._zoom_hist = [_ZoomState(self.ax.get_xlim(), self.ax.get_ylim())]
        self.canvas.draw_idle()

    def _on_autoscale(self):
        self._push_state(); self.ax.relim(); self.ax.autoscale()
        self.canvas.draw_idle()

    def _on_toggle_grid(self):
        self._grid_on = not self._grid_on
        if self._grid_on:
            self.ax.grid(True, which='both', alpha=0.3)
        else:
            self.ax.grid(False, which='both')
        self.canvas.draw_idle()

    def _on_toggle_minor(self):
        try:
            if not self._minor_on:
                self.ax.minorticks_on()
            else:
                self.ax.minorticks_off()
        except Exception:
            pass
        self._minor_on = self._minor_ticks_active(self.ax)
        self.canvas.draw_idle()

    def _on_toggle_legend(self):
        leg = self.ax.get_legend()
        if self._legend_visible and leg:
            leg.set_visible(False)
            self._legend_visible = False
        else:
            leg = self.ax.legend()
            if leg is not None:
                leg.set_visible(True)
                self._legend_visible = True
            else:
                self._legend_visible = False
        self.canvas.draw_idle()

    # ---------- zoom/pan ----------
    def _on_zoom_at(self, ev, scale: float):
        self._push_state()
        x0, x1 = self.ax.get_xlim(); y0, y1 = self.ax.get_ylim()
        cx = ev.xdata if ev.xdata is not None else (x0 + x1) * 0.5
        cy = ev.ydata if ev.ydata is not None else (y0 + y1) * 0.5
        nx = (x1 - x0) * scale * 0.5
        ny = (y1 - y0) * scale * 0.5
        self.ax.set_xlim(cx - nx, cx + nx); self.ax.set_ylim(cy - ny, cy + ny)
        self.canvas.draw_idle()

    def _on_box_zoom(self):
        if self._box_patch is None:
            self._box_patch = Rectangle((0, 0), 0, 0, fill=False, linestyle='--', linewidth=1.0, edgecolor='#e67e22')
            self.ax.add_patch(self._box_patch)

    def _update_box(self, x0, y0, x1, y1):
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        self._box_patch.set_xy((x, y)); self._box_patch.set_width(w); self._box_patch.set_height(h)

    def _apply_box_zoom(self, x0, x1, y0, y1):
        self._push_state(); self.ax.set_xlim(x0, x1); self.ax.set_ylim(y0, y1); self.canvas.draw_idle()

    def _remove_box(self):
        try:
            if self._box_patch is not None:
                self._box_patch.remove()
        except Exception:
            pass
        finally:
            self._box_patch = None

    def _on_pan_mode(self):
        # lightweight pan: store current center on press handled in _on_mpl_press
        self._push_state()

    def _on_zoom_back(self):
        if len(self._zoom_hist) >= 2:
            self._zoom_hist.pop()  # drop current
            prev = self._zoom_hist.pop()
            self._apply_state(prev)
            self._zoom_hist.append(prev)

    # ---------- axes/scales ----------
    def _on_set_axis_limits(self):
        def ask(prompt: str, val: float) -> Optional[float]:
            txt, ok = QInputDialog.getText(None, 'Set Axis Limit', f'{prompt} =', text=f'{val:.6g}')
            if not ok: return None
            try: return float(txt)
            except ValueError: QMessageBox.warning(None, 'Invalid', 'Please enter a number.'); return None
        x0, x1 = self.ax.get_xlim(); y0, y1 = self.ax.get_ylim()
        nx0 = ask('Xmin', x0);   
        if nx0 is None: return
        nx1 = ask('Xmax', x1);   
        if nx1 is None: return
        ny0 = ask('Ymin', y0);   
        if ny0 is None: return
        ny1 = ask('Ymax', y1);
        if ny1 is None: return
        self.ax.set_xlim(nx0, nx1); self.ax.set_ylim(ny0, ny1); self.canvas.draw_idle()

    def _on_scale_change(self, axis: str, scale: str):
        if axis == 'x': self.ax.set_xscale(scale)
        else: self.ax.set_yscale(scale)
        self.canvas.draw_idle()

    def _on_invert_x(self):
        self.ax.invert_xaxis(); self.canvas.draw_idle()

    def _on_invert_y(self):
        self.ax.invert_yaxis(); self.canvas.draw_idle()

    # ---------- overlays / cursors ----------
    def _add_vline(self, ev):
        if ev.xdata is None: return
        ln = self.ax.axvline(ev.xdata, color='#95a5a6', ls='--', lw=1.0, zorder=40)
        self._overlays.append(ln); self.canvas.draw_idle()

    def _add_hline(self, ev):
        if ev.ydata is None: return
        ln = self.ax.axhline(ev.ydata, color='#95a5a6', ls='--', lw=1.0, zorder=40)
        self._overlays.append(ln); self.canvas.draw_idle()

    def _on_measure(self):
        self._measure_first = (np.nan, np.nan)  # mark waiting first
        QMessageBox.information(None, 'Measure', 'Click first point, then second point to measure. ESC to cancel.')

    def _draw_measure(self, p1, p2):
        x1, y1 = p1; x2, y2 = p2
        ln = Line2D([x1, x2], [y1, y2], color='#e67e22', lw=1.2, zorder=45)
        self.ax.add_line(ln); self._overlays.append(ln)
        dx, dy = (x2 - x1), (y2 - y1); dist = (dx*dx + dy*dy) ** 0.5
        xm, ym = (x1 + dx * 0.5, y1 + dy * 0.5)
        txt = self.ax.text(xm, ym, f"Δx={dx:.4g}\nΔy={dy:.4g}\n|Δ|={dist:.4g}", color='#e6e6e6', fontsize=9, zorder=46)
        self._overlays.append(txt); self.canvas.draw_idle()

    def _copy_coords(self, ev):
        if ev.xdata is None or ev.ydata is None: return
        QApplication.clipboard().setText(f"{ev.xdata:.6g}, {ev.ydata:.6g}")

    # ---------- analysis shortcuts ----------
    def _pk_detect_range(self):
        if self.main and getattr(self.main, '_on_pk_detect', None) and getattr(self.main, 'pkDock', None):
            self.main._on_pk_detect(self.main._collect_pk_params_from_menu())

    def _pk_annotate_toggle(self, on: bool):
        if self.main and getattr(self.main, '_on_pk_annotate', None):
            self.main._on_pk_annotate(on)

    def _cc_compute_range(self):
        if self.main and getattr(self.main, 'ccDock', None):
            self.main.ccDock._emit_compute()

    # ---------- export ----------
    def _save_png(self):
        fn, _ = QFileDialog.getSaveFileName(None, 'Save Figure', 'figure.png', 'PNG (*.png)')
        if not fn: return
        try:
            self.canvas.figure.savefig(fn, dpi=300, bbox_inches='tight')
            QMessageBox.information(None, 'Saved', f'Saved to {fn}')
        except Exception as e:
            QMessageBox.critical(None, 'Error', str(e))

    def _copy_figure(self):
        try:
            img = self.canvas.grab().toImage()
            QApplication.clipboard().setImage(img)
        except Exception as e:
            QMessageBox.critical(None, 'Error', str(e))

    def _export_visible_csv(self):
        fn, _ = QFileDialog.getSaveFileName(None, 'Export Visible Range', 'visible.csv', 'CSV (*.csv)')
        if not fn: return
        try:
            xlim = self.ax.get_xlim()
            rows: Dict[str, List[float]] = {'x': []}
            labels: List[str] = []
            for i, ln in enumerate(self.ax.get_lines()):
                x = ln.get_xdata(orig=False); y = ln.get_ydata(orig=False)
                m = (x >= min(xlim)) & (x <= max(xlim))
                if not rows['x']:
                    rows['x'] = list(x[m])
                lab = ln.get_label() if ln.get_label() and not ln.get_label().startswith('_') else f'y{i+1}'
                rows[lab] = list(y[m]); labels.append(lab)
            import csv
            with open(fn, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['x'] + labels)
                for r in range(len(rows['x'])):
                    w.writerow([rows['x'][r]] + [rows[l][r] for l in labels])
            QMessageBox.information(None, 'Export', f'Saved to {fn}')
        except Exception as e:
            QMessageBox.critical(None, 'Error', str(e))

    # ---------- snapshots / overlays ----------
    def _snapshot_view(self):
        self._push_state(); QMessageBox.information(None, 'Snapshot', 'Snapshot saved (use Recall Snapshot to restore).')

    def _clear_overlays(self):
        for a in list(self._overlays):
            try: a.remove()
            except Exception: pass
        self._overlays.clear(); self.canvas.draw_idle()
