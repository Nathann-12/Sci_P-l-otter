from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_menu_mixin import MainWindowMenuMixin
from main_window_toolbar_mixin import MainWindowToolbarMixin
from main_window_panels_mixin import MainWindowPanelsMixin


def test_mainwindow_inherits_ui_mixins():
    assert issubclass(MainWindow, MainWindowMenuMixin)
    assert issubclass(MainWindow, MainWindowToolbarMixin)
    assert issubclass(MainWindow, MainWindowPanelsMixin)


def test_ui_methods_resolve_to_mixins():
    # The construction methods should now live on the extracted mixins, not main.MainWindow body.
    assert MainWindow._init_menu.__qualname__.startswith("MainWindowMenuMixin")
    assert MainWindow.build_toolbar.__qualname__.startswith("MainWindowToolbarMixin")
    assert MainWindow._build_inspector_tabs.__qualname__.startswith("MainWindowPanelsMixin")
