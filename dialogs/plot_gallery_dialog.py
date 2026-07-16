# dialogs/plot_gallery_dialog.py
"""OriginPro-style plot gallery.

A left-hand category list + a right-hand grid of plot buttons, each showing a
tiny live thumbnail rendered from the *actual* active DataFrame so the user
previews their own data. Selecting a plot invokes ``on_pick(entry)`` (the plot
spec dict from :mod:`plots.registry`) and closes.

Pure Qt/Matplotlib presentation — it never mutates project state; the caller's
callback does the real plotting.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from plots.registry import plots_by_category

logger = logging.getLogger(__name__)


class _Thumb(FigureCanvas):
    """A small self-contained thumbnail canvas rendering one plot from *df*."""

    def __init__(self, entry: Dict[str, Any], df: pd.DataFrame):
        fig = Figure(figsize=(1.5, 1.1), dpi=72)
        super().__init__(fig)
        self.setFixedSize(112, 82)
        ax = fig.add_subplot(111)
        try:
            preview_df = df if df is not None else pd.DataFrame()
            if len(preview_df) > 2_000:
                import numpy as np

                indexes = np.linspace(0, len(preview_df) - 1, 2_000, dtype=int)
                preview_df = preview_df.iloc[indexes]
            entry["func"](ax, preview_df)
        except Exception:
            logger.debug("thumbnail render failed for %s", entry.get("key"), exc_info=True)
            ax.clear()
            ax.text(0.5, 0.5, "—", ha="center", va="center")
        ax.set_title("")
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.tick_params(labelsize=0, length=0)
        for lbl in (*ax.get_xticklabels(), *ax.get_yticklabels()):
            lbl.set_visible(False)
        try:
            fig.tight_layout(pad=0.2)
        except Exception:
            pass


class PlotGalleryDialog(QDialog):
    """Origin-style categorized plot picker."""

    def __init__(
        self,
        get_dataframe: Callable[[], pd.DataFrame],
        on_pick: Callable[[Dict[str, Any]], None],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Plot Gallery")
        self.resize(720, 520)
        self._get_df = get_dataframe
        self._on_pick = on_pick
        try:
            self._df = get_dataframe()
        except Exception:
            self._df = pd.DataFrame()
        if not isinstance(self._df, pd.DataFrame):
            self._df = pd.DataFrame()

        self._by_cat = plots_by_category()

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        # Left: category list
        self.catList = QListWidget()
        self.catList.setMaximumWidth(190)
        for cat in self._by_cat:
            QListWidgetItem(cat, self.catList)
        self.catList.currentRowChanged.connect(self._show_category)
        body.addWidget(self.catList)

        # Right: scrollable grid of plot buttons
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.gridHost = QWidget()
        self.grid = QGridLayout(self.gridHost)
        self.grid.setContentsMargins(10, 10, 10, 10)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.gridHost)
        body.addWidget(self.scroll, 1)

        hint = QLabel(
            "Thumbnails preview your active data. Click a plot, choose data columns, "
            "then draw it in a new graph."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if self.catList.count():
            self.catList.setCurrentRow(0)
        elif not self._by_cat:
            hint.setText("No plots are registered. (plots/ package failed to load.)")

    # ----- interactions -----
    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _show_category(self, row: int) -> None:
        self._clear_grid()
        if row < 0:
            return
        cats: List[str] = list(self._by_cat.keys())
        if row >= len(cats):
            return
        entries = self._by_cat[cats[row]]
        for i, entry in enumerate(entries):
            self.grid.addWidget(self._make_button(entry), i // 4, i % 4)

    def _make_button(self, entry: Dict[str, Any]) -> QWidget:
        cell = QWidget()
        v = QVBoxLayout(cell)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        btn = QToolButton()
        btn.setToolTip(entry.get("desc", ""))
        btn.setAutoRaise(True)
        try:
            btn.setIconSize(self._thumb_size())
        except Exception:
            pass
        # embed a live thumbnail
        thumb = _Thumb(entry, self._df)
        v.addWidget(thumb, 0, Qt.AlignHCenter)
        caption = QLabel(entry.get("title", entry.get("key", "")))
        caption.setAlignment(Qt.AlignHCenter)
        caption.setWordWrap(True)
        caption.setMaximumWidth(120)
        v.addWidget(caption)
        # make the whole cell clickable via the thumbnail
        thumb.mousePressEvent = lambda _e, en=entry: self._pick(en)  # type: ignore
        caption.mousePressEvent = lambda _e, en=entry: self._pick(en)  # type: ignore
        btn.deleteLater()
        return cell

    def _thumb_size(self):
        from PySide6.QtCore import QSize
        return QSize(112, 82)

    def _pick(self, entry: Dict[str, Any]) -> None:
        try:
            self._on_pick(entry)
        except Exception:
            logger.debug("on_pick failed for %s", entry.get("key"), exc_info=True)
        self.accept()
