from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Tuple, Any, Optional

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QAction, QIcon, QCursor
from PySide6.QtWidgets import (
    QMenu, QWidget, QGridLayout, QToolButton, QWidgetAction,
    QFrame, QVBoxLayout, QLabel
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  # enable 3D projection


# ---------- Utility: pick axes & downsample ----------
TIME_KEYS = ("time", "t", "timestamp", "datetime")


def _numeric_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _guess_x_col(df: pd.DataFrame) -> Optional[str]:
    cols = [c for c in df.columns if any(k in str(c).lower() for k in TIME_KEYS)]
    if cols:
        return cols[0]
    nums = _numeric_cols(df)
    return nums[0] if nums else None


def pick_xy(df: pd.DataFrame) -> Tuple[np.ndarray, List[Tuple[str, np.ndarray]]]:
    """Return X array and list of (name, Y array)."""
    if df is None or df.empty:
        return np.array([]), []
    nums = _numeric_cols(df)
    if not nums:
        return df.index.to_numpy(), []
    xcol = _guess_x_col(df)
    if xcol is None:
        x = np.arange(len(df))
        ycols = nums
    else:
        x = df[xcol].to_numpy()
        ycols = [c for c in nums if c != xcol]
        if not ycols:
            ycols = [xcol]
            x = np.arange(len(df))
    pairs = [(c, df[c].to_numpy()) for c in ycols]
    return np.asarray(x, dtype=float), [(n, np.asarray(a, dtype=float)) for n, a in pairs]


def pick_xyz(df: pd.DataFrame) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    nums = _numeric_cols(df)
    if len(nums) >= 3:
        a, b, c = nums[:3]
        return df[a].to_numpy(), df[b].to_numpy(), df[c].to_numpy()
    return None


def downsample(arr: np.ndarray, max_n: int = 2000) -> np.ndarray:
    n = arr.shape[0]
    if n <= max_n:
        return arr
    idx = np.linspace(0, n - 1, max_n).astype(int)
    return arr[idx]


# ---------- Floating preview (tooltip-like overlay) ----------
class FloatingPreview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setObjectName("FloatingPreview")
        self.setStyleSheet("#FloatingPreview { border: 1px solid #555; border-radius: 6px; }")
        self.resize(380, 260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.title = QLabel("Preview")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.fig = Figure(figsize=(3.6, 2.2), tight_layout=True)
        self.canvas = FigureCanvas(self.fig)
        lay.addWidget(self.title)
        lay.addWidget(self.canvas)
        self.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_at_cursor(self):
        p = QCursor.pos() + QPoint(16, 16)
        self.move(p)
        self.show()

    def schedule_autohide(self, ms=800):
        self._hide_timer.start(ms)


# ---------- Plotters ----------
def plot_line(ax, df: pd.DataFrame):
    x, ys = pick_xy(df)
    ax.clear()
    for name, y in ys[:8]:
        ax.plot(downsample(x), downsample(y), label=str(name))
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Line")
    if ys:
        ax.legend(loc="best")


def plot_scatter(ax, df: pd.DataFrame):
    x, ys = pick_xy(df)
    ax.clear()
    for name, y in ys[:8]:
        ax.scatter(downsample(x), downsample(y), s=8, label=str(name))
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Scatter")
    if ys:
        ax.legend(loc="best")


def plot_bar(ax, df: pd.DataFrame):
    x, ys = pick_xy(df)
    ax.clear()
    if not ys:
        return
    w = 0.8 / len(ys[:6])
    for i, (name, y) in enumerate(ys[:6]):
        xi = np.arange(len(downsample(y)))
        ax.bar(xi + i * w, downsample(y), width=w, label=str(name))
    ax.set_title("Bar")
    ax.legend(loc="best")


def plot_area(ax, df: pd.DataFrame):
    x, ys = pick_xy(df)
    ax.clear()
    if not ys:
        return
    Y = np.vstack([downsample(y) for _, y in ys[:6]])
    m = min(downsample(x).shape[0], Y.shape[1])
    ax.stackplot(downsample(x)[:m], Y[:, :m], labels=[n for n, _ in ys[:6]])
    ax.set_title("Area")
    ax.legend(loc="best")


def plot_hist(ax, df: pd.DataFrame):
    x, ys = pick_xy(df)
    ax.clear()
    target = ys[0][1] if ys else x
    ax.hist(downsample(np.asarray(target)), bins=20)
    ax.set_title("Histogram")


def plot_box(ax, df: pd.DataFrame):
    x, ys = pick_xy(df)
    ax.clear()
    data = [downsample(y) for _, y in ys[:6]] or [downsample(x)]
    ax.boxplot(data, labels=[n for n, _ in ys[:6]] or ["Values"])
    ax.set_title("Box")


def plot_pie(ax, df: pd.DataFrame):
    nums = _numeric_cols(df)
    ax.clear()
    if not nums:
        return
    vals = np.abs(df[nums[0]].to_numpy()[:8].astype(float))
    if np.all(vals == 0):
        vals = np.ones_like(vals)
    labels = [f"{nums[0]}[{i}]" for i in range(len(vals))]
    ax.pie(vals, labels=labels, autopct="%1.0f%%")
    ax.set_title("Pie")


def plot_3d_scatter(ax3d, df: pd.DataFrame):
    ax3d.clear()
    xyz = pick_xyz(df)
    if xyz is None:
        ax3d.text2D(0.05, 0.9, "Need ≥3 numeric columns", transform=ax3d.transAxes)
        return
    x, y, z = (downsample(np.asarray(a, float)) for a in xyz)
    ax3d.scatter(x, y, z, s=6)
    ax3d.set_xlabel("X")
    ax3d.set_ylabel("Y")
    ax3d.set_zlabel("Z")
    ax3d.set_title("3D Scatter")


# ---------- Spec ----------
@dataclass
class ChartSpec:
    key: str
    title: str
    icon: Optional[str]  # path
    preview_func: Callable[[Any, pd.DataFrame], None]
    apply_func: Callable[[Any, pd.DataFrame], None]
    is3d: bool = False


def _mk_specs() -> List[ChartSpec]:
    return [
        ChartSpec("line", "Line", None, plot_line, plot_line),
        ChartSpec("scatter", "Scatter", None, plot_scatter, plot_scatter),
        ChartSpec("bar", "Bar", None, plot_bar, plot_bar),
        ChartSpec("area", "Area", None, plot_area, plot_area),
        ChartSpec("hist", "Histogram", None, plot_hist, plot_hist),
        ChartSpec("box", "Box", None, plot_box, plot_box),
        ChartSpec("pie", "Pie", None, plot_pie, plot_pie),
        ChartSpec("3d_scatter", "3D Scatter", None, plot_3d_scatter, plot_3d_scatter, is3d=True),
    ]


# ---------- Gallery Menu ----------
class ChartGalleryMenu(QMenu):
    """
    Usage:
        menu = ChartGalleryMenu(get_dataframe=<callable>, get_main_figure=<callable>, parent=self)
        menubar.addMenu(menu)
    """

    def __init__(self,
                 get_dataframe: Callable[[], pd.DataFrame],
                 get_main_figure: Callable[[], Figure] = None,
                 apply_plot: Callable[[Callable, bool], None] = None,
                 parent=None):
        super().__init__("Charts", parent)
        self.get_dataframe = get_dataframe
        self.get_main_figure = get_main_figure
        self.apply_plot = apply_plot
        self.preview = FloatingPreview(self)
        self.specs = _mk_specs()

        w = QWidget(self)
        grid = QGridLayout(w)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # Create grid buttons
        for i, spec in enumerate(self.specs):
            btn = QToolButton(w)
            btn.setText(spec.title)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            if spec.icon:
                btn.setIcon(QIcon(spec.icon))
            btn.setFixedSize(110, 84)
            btn.enterEvent = lambda e, s=spec: self._on_hover(s)  # type: ignore
            btn.clicked.connect(lambda _, s=spec: self._on_apply(s))
            grid.addWidget(btn, i // 4, i % 4)

        wa = QWidgetAction(self)
        wa.setDefaultWidget(w)
        self.addAction(wa)

    # ----- interactions -----
    def _on_hover(self, spec: ChartSpec):
        df = self.get_dataframe()
        self.preview.title.setText(spec.title + " (Preview)")
        self.preview.fig.clear()
        if spec.is3d:
            ax = self.preview.fig.add_subplot(111, projection="3d")
        else:
            ax = self.preview.fig.add_subplot(111)
        try:
            spec.preview_func(ax, df)
        except Exception as e:
            ax.clear()
            ax.text(0.5, 0.5, f"Preview error:\n{e}", ha="center", va="center")
        self.preview.canvas.draw()
        self.preview.show_at_cursor()
        self.preview.schedule_autohide(1200)

    def _on_apply(self, spec: ChartSpec):
        df = self.get_dataframe()
        def drawer(ax):
            spec.apply_func(ax, df)
        if self.apply_plot is not None:
            self.apply_plot(drawer, prefer_3d=spec.is3d)
        else:
            # fallback (legacy)
            fig = self.get_main_figure()
            ax = fig.add_subplot(111, projection="3d" if spec.is3d else None)
            drawer(ax)
            fig.canvas.draw_idle()
        self.hide()
        self.preview.hide()
