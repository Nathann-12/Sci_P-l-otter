from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List

import json
import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QPushButton, QHBoxLayout, QTableWidget, QTableWidgetItem, QFileDialog
)


@dataclass
class PeakParams:
    polarity: str = 'peaks'           # peaks|troughs|both
    prominence: float = 0.0
    height: float = 0.0
    min_distance: int = 1
    min_width: int = 1
    smooth_window: int = 0
    annotate: bool = True


class PeakDetectorManager(QObject):
    changed = Signal()

    def __init__(self, mw: QObject):
        super().__init__(mw)
        self.mw = mw
        self.enabled = False
        self.params = PeakParams()
        self._artists: List[Any] = []
        self._last_results: Optional[Dict[str, Any]] = None

    def set_enabled(self, on: bool):
        self.enabled = bool(on); self.changed.emit()

    def clear(self):
        for a in list(self._artists):
            try: a.remove()
            except Exception: pass
        self._artists.clear(); self._last_results = None
        try:
            tab = self.mw.tabs.currentWidget(); tab.get_figure().canvas.draw_idle()
        except Exception:
            pass

    # --- detection ---
    def _smooth(self, y: np.ndarray, w: int) -> np.ndarray:
        arr = np.asarray(y, float)
        if arr.size == 0:
            return arr
        if w and w > 1 and arr.size > 0:
            k = int(w)
            kernel = np.ones(k) / k
            return np.convolve(arr, kernel, mode='same')
        return arr


    def detect(self, x: np.ndarray, y: np.ndarray, params: PeakParams) -> Dict[str, Any]:
        x = np.asarray(x, float).reshape(-1)
        y = np.asarray(y, float).reshape(-1)
        if x.shape != y.shape:
            n = min(x.size, y.size)
            x = x[:n]
            y = y[:n]
        y = self._smooth(y, params.smooth_window)
        if x.size == 0 or y.size == 0:
            res = {'index': [], 'x_peak': [], 'y_peak': [], 'kind': []}
            self._last_results = res
            return res
        findings: List[tuple[int, str]] = []

        def _collect(indices: np.ndarray, label: str):
            if indices is None:
                return
            arr = np.asarray(indices, dtype=int)
            if arr.size == 0:
                return
            for idx in arr:
                findings.append((int(idx), label))

        if params.polarity == 'both':
            _collect(self._find_peaks_numpy(y, params), 'peak')
            _collect(self._find_peaks_numpy(-y, params), 'trough')
        else:
            label = 'peak' if params.polarity != 'troughs' else 'trough'
            series = y if label == 'peak' else -y
            _collect(self._find_peaks_numpy(series, params), label)

        deduped: Dict[int, str] = {}
        for idx, kind in findings:
            if idx not in deduped:
                deduped[idx] = kind

        if deduped:
            indices = np.array(sorted(deduped.keys()), dtype=int)
            kinds = [deduped[i] for i in indices]
            x_vals = x[indices]
            y_vals = y[indices]
        else:
            indices = np.array([], dtype=int)
            kinds = []
            x_vals = np.asarray([], dtype=float)
            y_vals = np.asarray([], dtype=float)

        res = {
            'index': indices.tolist(),
            'x_peak': x_vals.tolist(),
            'y_peak': y_vals.tolist(),
            'kind': kinds,
        }
        self._last_results = res
        return res


    def _find_peaks_numpy(self, y: np.ndarray, p: PeakParams) -> np.ndarray:
        arr = np.asarray(y, float)
        n = arr.size
        if n == 0:
            return np.array([], dtype=int)
        # simple local maxima with min distance and height/prominence approx
        dy1 = np.r_[True, arr[1:] > arr[:-1]]
        dy2 = np.r_[arr[:-1] > arr[1:], True]
        cand = np.where(dy1 & dy2)[0]
        if p.height > 0:
            cand = cand[arr[cand] >= p.height]
        # crude prominence: value - min(neighborhood)
        if p.prominence > 0 and cand.size:
            win = max(p.min_distance, 3)
            keep = []
            for idx in cand:
                l = max(0, idx - win)
                r = min(n, idx + win)
                prom = arr[idx] - arr[l:r].min()
                if prom >= p.prominence:
                    keep.append(idx)
            cand = np.array(keep, dtype=int)
        # enforce min distance
        if p.min_distance > 1 and cand.size:
            cand = cand[np.argsort(-arr[cand])]  # sort by height desc
            keep = []
            selected = np.zeros(n, dtype=bool)
            for idx in cand:
                lo = max(0, idx - p.min_distance)
                hi = min(n, idx + p.min_distance + 1)
                if not selected[lo:hi].any():
                    keep.append(idx)
                    selected[idx] = True
            cand = np.sort(np.array(keep, dtype=int))
        return cand


    def annotate(self, x: np.ndarray, y: np.ndarray, res: Dict[str, Any]):
        try:
            tab = self.mw.tabs.currentWidget(); ax = tab.get_axes(); fig = tab.get_figure()
        except Exception:
            return
        # clear previous
        self.clear()
        idx = np.array(res.get('index', []), dtype=int)
        if idx.size == 0:
            return
        xp = np.asarray(res.get('x_peak', []), float); yp = np.asarray(res.get('y_peak', []), float)
        if xp.size == 0 or yp.size == 0:
            return
        kinds = res.get('kind') or ['peak'] * idx.size
        if len(kinds) != idx.size:
            kinds = ['peak'] * idx.size
        kinds_arr = np.array([str(k).lower() for k in kinds])
        colors = ['#e74c3c' if kind != 'trough' else '#3498db' for kind in kinds_arr]
        try:
            sc = ax.scatter(xp, yp, s=30, color=colors, zorder=30)
            self._artists.append(sc)
            counts: Dict[str, int] = {}
            for xx, yy, kind in zip(xp, yp, kinds_arr):
                counts[kind] = counts.get(kind, 0) + 1
                prefix = 'Tr' if kind == 'trough' else 'Pk'
                label = f"{prefix}{counts[kind]}"
                t = ax.text(xx, yy, label, color='#e6e6e6', fontsize=9, zorder=31)
                self._artists.append(t)
            fig.canvas.draw_idle()
        except Exception:
            pass

    # --- persistence ---
    def to_json(self) -> str:
        d = asdict(self.params); d['enabled'] = self.enabled; d['annotate'] = self.params.annotate
        return json.dumps(d)

    def from_json(self, s: str):
        try:
            d = json.loads(s)
            self.enabled = bool(d.get('enabled', False))
            self.params = PeakParams(**{k: d.get(k, getattr(self.params, k)) for k in asdict(self.params).keys()})
        except Exception:
            pass


class PeakDetectionDock(QDockWidget):
    request_detect = Signal(dict)  # columns + params
    request_annotate = Signal(bool)
    request_clear = Signal()
    request_export = Signal()

    def __init__(self, parent=None):
        super().__init__("Peak Detection Panel", parent)
        self.setObjectName("PeakDetectionDock")
        w = QWidget(); self.setWidget(w)
        form = QFormLayout(w)

        # selectors
        self.cbX = QComboBox(); self.cbY = QComboBox()
        form.addRow("X (time):", self.cbX)
        form.addRow("Y:", self.cbY)

        # params
        self.cbPolarity = QComboBox(); self.cbPolarity.addItems(["peaks", "troughs", "both"])
        self.spinProm = QDoubleSpinBox(); self.spinProm.setRange(0.0, 1e12); self.spinProm.setDecimals(6)
        self.spinHeight = QDoubleSpinBox(); self.spinHeight.setRange(0.0, 1e12); self.spinHeight.setDecimals(6)
        self.spinMinDist = QSpinBox(); self.spinMinDist.setRange(1, 10**7); self.spinMinDist.setValue(5)
        self.spinMinWidth = QSpinBox(); self.spinMinWidth.setRange(1, 10**7); self.spinMinWidth.setValue(1)
        self.spinSmooth = QSpinBox(); self.spinSmooth.setRange(0, 10**6); self.spinSmooth.setValue(0)
        self.chkAnnotate = QCheckBox("Annotate Peaks")
        self.chkAnnotate.setChecked(True)

        form.addRow("Polarity:", self.cbPolarity)
        form.addRow("Prominence >=:", self.spinProm)
        form.addRow("Height >=:", self.spinHeight)
        form.addRow("Min distance (samples):", self.spinMinDist)
        form.addRow("Min width (samples):", self.spinMinWidth)
        form.addRow("Smoothing window:", self.spinSmooth)
        form.addRow("", self.chkAnnotate)

        # buttons
        hb = QHBoxLayout()
        self.btnDetect = QPushButton("Detect")
        self.btnAnnotate = QPushButton("Annotate")
        self.btnClear = QPushButton("Clear")
        self.btnExport = QPushButton("Export…")
        hb.addWidget(self.btnDetect); hb.addWidget(self.btnAnnotate); hb.addWidget(self.btnClear); hb.addWidget(self.btnExport)
        actions_widget = QWidget(); actions_widget.setLayout(hb)
        form.addRow("Actions:", actions_widget)
        # result table
        self.table = QTableWidget(0, 0)
        form.addRow(self.table)

        self.btnDetect.clicked.connect(self._emit_detect)
        self.btnAnnotate.clicked.connect(lambda: self.request_annotate.emit(True))
        self.btnClear.clicked.connect(lambda: self.request_clear.emit())
        self.btnExport.clicked.connect(lambda: self.request_export.emit())

    def populate_columns(self, cols: List[str]):
        for cb in (self.cbX, self.cbY):
            cb.clear(); cb.addItems(cols)

    def _emit_detect(self):
        self.request_detect.emit({
            'x': self.cbX.currentText(),
            'y': self.cbY.currentText(),
            'polarity': self.cbPolarity.currentText(),
            'prominence': float(self.spinProm.value()),
            'height': float(self.spinHeight.value()),
            'min_distance': int(self.spinMinDist.value()),
            'min_width': int(self.spinMinWidth.value()),
            'smooth_window': int(self.spinSmooth.value()),
            'annotate': self.chkAnnotate.isChecked(),
        })

    def show_results(self, res: Dict[str, Any]):
        xs = res.get('x_peak', []) or []
        ys = res.get('y_peak', []) or []
        idx = res.get('index', []) or []
        kinds = res.get('kind', []) or []
        has_kind = bool(kinds)
        headers = ["x_peak", "y_peak", "index"] + (["type"] if has_kind else [])
        self.table.setColumnCount(len(headers))
        header_labels = [h if h != 'type' else 'Type' for h in headers]
        self.table.setHorizontalHeaderLabels(header_labels)
        rows = min(len(xs), len(ys), len(idx))
        if has_kind:
            rows = min(rows, len(kinds))
        self.table.setRowCount(rows)
        for r in range(rows):
            x = xs[r]
            y = ys[r]
            i = idx[r]
            try:
                x_val = f"{float(x):.6g}"
            except Exception:
                x_val = str(x)
            try:
                y_val = f"{float(y):.6g}"
            except Exception:
                y_val = str(y)
            self.table.setItem(r, 0, QTableWidgetItem(x_val))
            self.table.setItem(r, 1, QTableWidgetItem(y_val))
            self.table.setItem(r, 2, QTableWidgetItem(str(i)))
            if has_kind:
                kind_val = str(kinds[r]).strip()
                self.table.setItem(r, 3, QTableWidgetItem(kind_val.capitalize()))
