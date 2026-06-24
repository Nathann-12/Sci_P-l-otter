from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("numexpr")

from main import MainWindow
from main_window_data_mixin import MainWindowDataMixin
from main_window_export_mixin import MainWindowExportMixin
from main_window_fit_mixin import MainWindowFitMixin
from main_window_plot_mixin import MainWindowPlotMixin
from main_window_session_mixin import MainWindowSessionMixin
from main_window_spectrogram_mixin import MainWindowSpectrogramMixin
from main_window_view_mixin import MainWindowViewMixin


def test_mainwindow_inherits_extracted_mixins():
    assert issubclass(MainWindow, MainWindowDataMixin)
    assert issubclass(MainWindow, MainWindowPlotMixin)
    assert issubclass(MainWindow, MainWindowFitMixin)
    assert issubclass(MainWindow, MainWindowExportMixin)
    assert issubclass(MainWindow, MainWindowSessionMixin)
    assert issubclass(MainWindow, MainWindowSpectrogramMixin)
    assert issubclass(MainWindow, MainWindowViewMixin)
