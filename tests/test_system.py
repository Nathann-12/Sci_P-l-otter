import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_matplotlib_backend_available():
    matplotlib = pytest.importorskip("matplotlib")

    assert matplotlib.__version__
    matplotlib.use("Qt5Agg", force=True)
    assert "agg" in matplotlib.get_backend().lower()


def test_pyside6_qapplication_can_start():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    assert app is not None


def test_matplotlib_canvas_draws_with_qt_backend():
    pytest.importorskip("PySide6")
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Qt5Agg", force=True)

    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    fig = Figure(figsize=(4, 3), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvas(fig)

    ax.plot([1, 2, 3], [2, 4, 6])
    canvas.draw()

    assert len(ax.lines) == 1


def test_sciplotter_main_components_import():
    pytest.importorskip("numexpr")

    from main import GraphTab, MainWindow, PlotCanvas, TabManager

    assert PlotCanvas is not None
    assert GraphTab is not None
    assert TabManager is not None
    assert MainWindow is not None
