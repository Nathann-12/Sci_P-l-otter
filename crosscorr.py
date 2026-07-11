from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List, Tuple

import json
import logging
import numpy as np
from PySide6 import QtCore
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QPushButton, QHBoxLayout, QTextEdit, QLabel
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


@dataclass
class CrossCorrOptions:
    detrend: str = "none"           # none|linear
    normalize: str = "zscore"       # zscore|minmax|none
    resample_dt: float = 0.0         # 0 = infer
    max_lag: float = 5.0             # seconds (if x is time-like) or samples
    step: float = 0.0                # 0 = 1 sample or infer by dt
    link_axes: bool = False


class CrossCorrManager(QObject):
    changed = Signal()

    def __init__(self, mw: QObject):
        super().__init__(mw)
        self.mw = mw  # MainWindow
        self.enabled = False
        self.opt = CrossCorrOptions()
        self._vlines = []  # vertical lines for multi-cursor
        self._event_ids: List[int] = []

    # ---- UI wiring ----
    def set_enabled(self, on: bool):
        self.enabled = bool(on)
        self._ensure_event_hooks()
        self.changed.emit()

    def set_link_axes(self, on: bool):
        self.opt.link_axes = bool(on)
        self._sync_axes_once()
        self.changed.emit()

    def _axes_list(self):
        axes = []
        try:
            tabs = getattr(self.mw, 'tabs')
            for _, tab in getattr(tabs, 'tabs', {}).items():
                ax = tab.get_axes()
                if ax: axes.append(ax)
        except Exception:
            pass
        return axes

    def _current_fig(self):
        try:
            tab = self.mw.tabs.currentWidget()
            return tab.get_figure()
        except Exception:
            return None

    def _ensure_event_hooks(self):
        fig = self._current_fig()
        if fig is None:
            return
        if self._event_ids:
            for cid in self._event_ids:
                try:
                    fig.canvas.mpl_disconnect(cid)
                except Exception:
                    logging.getLogger(__name__).debug("mpl_disconnect failed", exc_info=True)
            self._event_ids.clear()
        self._event_ids.append(fig.canvas.mpl_connect('motion_notify_event', self._on_motion))
        self._event_ids.append(fig.canvas.mpl_connect('draw_event', self._on_draw))

    # ---- multi-cursor ----
    def _on_draw(self, _ev):
        # clear cached lines after redraw
        self._clear_vlines()

    def _clear_vlines(self):
        for ln in self._vlines:
            try:
                ln.remove()
            except Exception:
                logging.getLogger(__name__).debug("vline remove failed", exc_info=True)
        self._vlines.clear()

    def _on_motion(self, ev):
        if not self.enabled or ev.xdata is None:
            return
        xs = ev.xdata
        self._clear_vlines()
        for ax in self._axes_list():
            try:
                ln = ax.axvline(xs, color='#3498db', alpha=0.6, lw=1.0, zorder=50)
                self._vlines.append(ln)
            except Exception:
                continue
        fig = self._current_fig()
        if fig: fig.canvas.draw_idle()
        if self.opt.link_axes:
            self._sync_axes_to_x(xs)

    def _sync_axes_to_x(self, x):
        # keep current view; only ensures the same center x if link enabled
        try:
            for ax in self._axes_list():
                x0, x1 = ax.get_xlim()
                cx = (x0 + x1) * 0.5
                dx = x - cx
                ax.set_xlim(x0 + dx, x1 + dx)
        except Exception:
            pass

    def _sync_axes_once(self):
        axes = self._axes_list()
        if not axes:
            return
        try:
            base = axes[0].get_xlim()
            for ax in axes[1:]:
                ax.set_xlim(*base)
            fig = self._current_fig()
            if fig: fig.canvas.draw_idle()
        except Exception:
            pass

    # ---- compute cross-correlation ----
    def compute_crosscorr(self, x1: np.ndarray, y1: np.ndarray, x2: np.ndarray, y2: np.ndarray,
                           max_lag: float, step: float, detrend: str, normalize: str) -> Dict[str, Any]:
        # align to common grid
        x1 = np.asarray(x1, float); y1 = np.asarray(y1, float)
        x2 = np.asarray(x2, float); y2 = np.asarray(y2, float)
        # infer dt
        dt1 = np.median(np.diff(x1)) if len(x1) > 1 else 1.0
        dt2 = np.median(np.diff(x2)) if len(x2) > 1 else 1.0
        dt = np.nanmedian([dt1, dt2]) if step <= 0 else step
        start = max(x1.min(), x2.min()); end = min(x1.max(), x2.max())
        if end <= start: raise ValueError('no overlap range')
        grid = np.arange(start, end, dt)
        if grid.size < 20: raise ValueError('insufficient samples after align')
        y1i = np.interp(grid, x1, y1)
        y2i = np.interp(grid, x2, y2)
        # detrend
        if detrend == 'linear':
            for arr in (y1i, y2i):
                t = np.arange(arr.size)
                A = np.vstack((t, np.ones_like(t))).T
                m, c = np.linalg.lstsq(A, arr, rcond=None)[0]
                arr -= (m * t + c)
        # normalize
        def _norm(a: np.ndarray):
            if normalize == 'zscore':
                m, s = np.nanmean(a), np.nanstd(a)
                return (a - m) / (s + 1e-12)
            if normalize == 'minmax':
                lo, hi = np.nanmin(a), np.nanmax(a)
                return (a - lo) / (hi - lo + 1e-12)
            return a
        y1n = _norm(y1i); y2n = _norm(y2i)
        # lags in samples
        max_k = int(abs(max_lag) / dt)
        lags_k = np.arange(-max_k, max_k + 1, 1)
        corr = np.empty_like(lags_k, dtype=float)
        for i, k in enumerate(lags_k):
            if k >= 0:
                a = y1n[k:]; b = y2n[:y2n.size - k]
            else:
                a = y1n[:y1n.size + k]; b = y2n[-k:]
            if a.size < 5: corr[i] = np.nan; continue
            corr[i] = np.corrcoef(a, b)[0, 1]
        best_idx = int(np.nanargmax(np.abs(corr)))
        best_lag_k = int(lags_k[best_idx])
        best_lag = best_lag_k * dt
        best_r = float(corr[best_idx])
        # Spearman (optional)
        try:
            from scipy.stats import spearmanr
            # use 0-lag approx for quick report
            rho, pval = spearmanr(y1n, y2n)
        except Exception:
            # rank correlation fallback
            rho = np.corrcoef(np.argsort(np.argsort(y1n)), np.argsort(np.argsort(y2n)))[0, 1]
            pval = np.nan
        return {
            'dt': dt, 'lags': lags_k * dt, 'corr': corr,
            'best_lag': best_lag, 'best_r': best_r, 'rho': float(rho), 'pval': float(pval) if np.isfinite(pval) else None
        }

    # ---- persistence ----
    def to_json(self) -> str:
        d = asdict(self.opt); d['enabled'] = self.enabled
        return json.dumps(d)

    def from_json(self, s: str):
        try:
            d = json.loads(s)
            self.enabled = bool(d.get('enabled', False))
            self.opt = CrossCorrOptions(**{k: d.get(k, getattr(self.opt, k)) for k in asdict(self.opt).keys()})
            self._ensure_event_hooks()
        except Exception:
            pass


class CrossCorrDock(QDockWidget):
    request_compute = Signal(dict)  # emits options dict

    def __init__(self, parent=None):
        super().__init__("Cross-Correlation Panel", parent)
        self.setObjectName("CrossCorrDock")
        w = QWidget(); self.setWidget(w)
        form = QFormLayout(w)

        # Series selectors (populated from MainWindow when shown)
        self.cbX = QComboBox(); self.cbY1 = QComboBox(); self.cbY2 = QComboBox()
        form.addRow("X (time):", self.cbX)
        form.addRow("Y A:", self.cbY1)
        form.addRow("Y B:", self.cbY2)

        # Options
        self.cbDetrend = QComboBox(); self.cbDetrend.addItems(["none", "linear"])
        self.cbNorm = QComboBox(); self.cbNorm.addItems(["zscore", "minmax", "none"])
        self.spinDt = QDoubleSpinBox(); self.spinDt.setRange(0.0, 1e6); self.spinDt.setDecimals(6); self.spinDt.setValue(0.0)
        self.spinMaxLag = QDoubleSpinBox(); self.spinMaxLag.setRange(0.0, 1e6); self.spinMaxLag.setValue(5.0)
        form.addRow("Detrend:", self.cbDetrend)
        form.addRow("Normalize:", self.cbNorm)
        form.addRow("Resample Δt (0=auto):", self.spinDt)
        form.addRow("Max lag (sec):", self.spinMaxLag)

        # Buttons and output
        hb = QHBoxLayout();
        self.btnCompute = QPushButton("Compute in Range")
        self.btnCopy = QPushButton("Copy Summary")
        self.btnClear = QPushButton("Clear")
        hb.addWidget(self.btnCompute); hb.addWidget(self.btnCopy); hb.addWidget(self.btnClear)
        actions_widget = QWidget(); actions_widget.setLayout(hb)
        form.addRow("Actions:", actions_widget)
        form.addRow("", QWidget())
        # summary text
        self.txt = QTextEdit(); self.txt.setReadOnly(True); form.addRow(QLabel("Summary:"), self.txt)
        # small plot
        self.fig = Figure(figsize=(3, 2), dpi=100); self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig); form.addRow(QLabel("r(lag) plot:"), self.canvas)

        self.btnCompute.clicked.connect(self._emit_compute)
        self.btnClear.clicked.connect(lambda: (self.txt.clear(), self.ax.cla(), self.canvas.draw_idle()))

    # populate column combos from df
    def populate_columns(self, cols: List[str]):
        for cb in (self.cbX, self.cbY1, self.cbY2):
            cb.clear(); cb.addItems(cols)

    def _emit_compute(self):
        self.request_compute.emit({
            'x': self.cbX.currentText(),
            'y1': self.cbY1.currentText(),
            'y2': self.cbY2.currentText(),
            'detrend': self.cbDetrend.currentText(),
            'normalize': self.cbNorm.currentText(),
            'dt': float(self.spinDt.value()),
            'max_lag': float(self.spinMaxLag.value()),
        })

    def show_result(self, res: Dict[str, Any]):
        self.txt.setPlainText(
            f"best r: {res['best_r']:.4f}\n"
            f"best lag: {res['best_lag']:.6g} s\n"
            f"Spearman ρ: {res['rho']:.4f}\n"
            f"p-value (approx): {res.get('pval', None)}"
        )
        self.ax.cla(); self.ax.plot(res['lags'], res['corr'], color='#4F9CF9'); self.ax.axvline(res['best_lag'], color='#e67e22', ls='--')
        self.ax.set_xlabel('lag (s)'); self.ax.set_ylabel('corr')
        self.ax.grid(True, alpha=0.3)
        self.canvas.draw_idle()
