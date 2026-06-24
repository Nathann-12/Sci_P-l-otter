from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_plotcore_mixin import MainWindowPlotCoreMixin


def test_mainwindow_inherits_plotcore_mixin():
    assert issubclass(MainWindow, MainWindowPlotCoreMixin)


def test_plotcore_methods_resolve_to_mixin():
    for name in ("apply_plot", "get_main_axes", "refresh_plot", "change_plot_style",
                 "_aggregate_and_plot", "apply_current_mpl_theme_to_canvas"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowPlotCoreMixin"), name
