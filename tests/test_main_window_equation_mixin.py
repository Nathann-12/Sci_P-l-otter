from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_equation_mixin import MainWindowEquationMixin


def test_mainwindow_inherits_equation_mixin():
    assert issubclass(MainWindow, MainWindowEquationMixin)


def test_equation_methods_resolve_to_mixin():
    for name in ("on_plot_from_equation", "_warn_equation_failure"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowEquationMixin"), name
