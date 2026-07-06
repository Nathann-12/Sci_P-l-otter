"""Regression guards for the plotting-performance fixes (no timing — structural
assertions so the double-render / heavy-fill can't silently come back)."""
from __future__ import annotations

import os
from pathlib import Path
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import pytest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def test_beautify_axes_does_not_draw_or_tight_layout():
    """beautify_axes must not render — the caller draws once (drawing here too
    meant every plot rendered 2-3×)."""
    from processors import beautify_axes
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 3])
    draws = {"n": 0}
    fig.canvas.draw = lambda *a, **k: draws.__setitem__("n", draws["n"] + 1)
    fig.tight_layout = lambda *a, **k: (_ for _ in ()).throw(AssertionError("tight_layout called"))
    beautify_axes(ax, title="t")
    assert draws["n"] == 0
    plt.close(fig)


# ---------------- workbook fill ----------------

@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_plotcanvas_applies_tight_layout_without_live_engine(qapp):
    """__init__ tight-lays out the figure once. It must NOT leave a live
    TightLayoutEngine (that re-runs a full layout on every draw); tight_layout()
    leaves a harmless PlaceHolderLayoutEngine instead."""
    from matplotlib.layout_engine import TightLayoutEngine
    from widgets.plot_tabs import PlotCanvas
    c = PlotCanvas()
    engine = c.fig.get_layout_engine()
    assert engine is not None
    assert not isinstance(engine, TightLayoutEngine)


def test_plotcanvas_draw_does_not_recurse_on_failure(qapp, monkeypatch):
    """A failing render must attempt the real draw exactly once and swallow the
    error. The old fallback called self.fig.canvas.draw() (== self.draw()) and
    recursed ~1000×, turning one bad axis into a multi-second hang."""
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from widgets.plot_tabs import PlotCanvas

    c = PlotCanvas()
    calls = {"n": 0}

    def boom(self, *a, **k):
        calls["n"] += 1
        raise ValueError("simulated bad axis (date locator on numeric data)")

    monkeypatch.setattr(FigureCanvasQTAgg, "draw", boom)
    # must not raise and must not recurse
    c.draw()
    assert calls["n"] == 1


def test_workbook_data_cells_have_no_per_cell_brush(qapp):
    """Data cells rely on the stylesheet for their background (setting a brush
    per cell allocated thousands of objects on big sheets)."""
    from widgets.workbook import WorkbookWidget, META_ROW_COUNT
    wb = WorkbookWidget()
    wb.set_dataframe(pd.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]}))
    data_item = wb.table.item(META_ROW_COUNT, 0)
    # default (unset) brush has NoBrush style
    from PySide6.QtCore import Qt
    assert data_item.background().style() == Qt.NoBrush


def test_large_set_dataframe_is_correct_and_clean(qapp):
    """Correctness after the bulk-fill optimization: values land in the right
    cells and the sheet is marked clean (not dirtied by the fill)."""
    from widgets.workbook import WorkbookWidget, META_ROW_COUNT
    wb = WorkbookWidget()
    n = 3000
    df = pd.DataFrame({"t": np.arange(n, dtype=float), "y": np.arange(n, dtype=float) * 2})
    wb.set_dataframe(df)
    assert wb.is_dirty is False
    assert wb.table.rowCount() == META_ROW_COUNT + n
    assert wb.table.item(META_ROW_COUNT, 0).text() == "0.0"
    assert wb.table.item(META_ROW_COUNT + n - 1, 1).text() == str(float((n - 1) * 2))
    # round-trips back to a DataFrame with the same values
    back = wb.dataframe()
    assert len(back) == n
    assert back["t"].iloc[-1] == float(n - 1)
