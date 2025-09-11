from __future__ import annotations
from typing import Callable, Tuple, Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QCheckBox, QWidget
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class _MplArea(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas)


class HistogramDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 get_current_data: Callable[[], Tuple[Any, Any]] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Histogram")
        # Non-modal overlay feel
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlag(Qt.Window)
        self.resize(720, 480)
        self.get_current_data = get_current_data

        # Controls
        self.bin_box = QSpinBox()
        self.bin_box.setRange(5, 500)
        self.bin_box.setValue(20)

        self.fit_normal_chk = QCheckBox("Fit normal curve")

        self.run_btn = QPushButton("Plot Histogram")
        self.run_btn.clicked.connect(self._on_run)

        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(6, 6, 6, 6)
        ctrl.setSpacing(10)
        ctrl.addWidget(QLabel("bins"))
        ctrl.addWidget(self.bin_box)
        ctrl.addSpacing(12)
        ctrl.addWidget(self.fit_normal_chk)
        ctrl.addStretch(1)
        ctrl.addWidget(self.run_btn)

        self.mpl = _MplArea(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addLayout(ctrl)
        lay.addWidget(self.mpl)

    def _on_run(self):
        x, y = (self.get_current_data() if self.get_current_data else (None, None))
        data = y if y is not None else x
        if data is None:
            return
        a = np.asarray(data, dtype=float)
        a = a[np.isfinite(a)]
        if a.size == 0:
            return

        self.mpl.fig.clear()
        ax = self.mpl.fig.add_subplot(111)
        n, bins, _ = ax.hist(a, bins=int(self.bin_box.value()), color="#4F9CF9", alpha=0.85)
        ax.set_xlabel("Value"); ax.set_ylabel("Count"); ax.set_title("Histogram")

        if self.fit_normal_chk.isChecked():
            mu = float(np.nanmean(a)); sigma = float(np.nanstd(a)) or 1.0
            xs = np.linspace(float(np.nanmin(a)), float(np.nanmax(a)), 400)
            pdf = 1.0 / (sigma * np.sqrt(2 * np.pi)) * np.exp(-(xs - mu) ** 2 / (2 * sigma ** 2))
            # scale pdf to histogram counts
            binw = (xs.max() - xs.min()) / max(int(self.bin_box.value()), 1)
            ax.plot(xs, pdf * a.size * binw, color="#e36a6a", linewidth=2, label=f"Normal fit mu={mu:.2f}, sigma={sigma:.2f}")
            ax.legend(loc="best")

        try:
            ax.grid(True, alpha=0.3); self.mpl.fig.tight_layout()
        except Exception:
            pass
        self.mpl.canvas.draw()

