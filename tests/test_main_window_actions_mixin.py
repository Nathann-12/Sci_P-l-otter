from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_actions_mixin import MainWindowActionsMixin


def test_mainwindow_inherits_actions_mixin():
    assert issubclass(MainWindow, MainWindowActionsMixin)


def test_action_methods_resolve_to_mixin():
    for name in ("on_action_plot", "on_action_spectrogram", "on_action_export_figure",
                 "get_current_dataframe", "_resolve_active_dataframe", "get_current_xy",
                 "show_histogram_dialog", "dragEnterEvent", "dropEvent"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowActionsMixin"), name
