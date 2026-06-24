from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_settings_mixin import MainWindowSettingsMixin


def test_mainwindow_inherits_settings_mixin():
    assert issubclass(MainWindow, MainWindowSettingsMixin)


def test_settings_methods_resolve_to_mixin():
    for name in ("_get_config_path", "_load_plot_style_config", "_save_plot_style_config",
                 "_load_and_apply_settings", "show_settings", "_on_settings_applied"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowSettingsMixin"), name
