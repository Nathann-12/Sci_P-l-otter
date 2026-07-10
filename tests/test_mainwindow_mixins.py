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
from main_window_menu_mixin import MainWindowMenuMixin
from main_window_toolbar_mixin import MainWindowToolbarMixin
from main_window_panels_mixin import MainWindowPanelsMixin
from main_window_plotcore_mixin import MainWindowPlotCoreMixin
from main_window_analysis_mixin import MainWindowAnalysisMixin
from main_window_equation_mixin import MainWindowEquationMixin
from main_window_settings_mixin import MainWindowSettingsMixin
from main_window_features_mixin import MainWindowFeaturesMixin
from main_window_actions_mixin import MainWindowActionsMixin
from main_window_spectroscopy_mixin import MainWindowSpectroscopyMixin
from main_window_materials_mixin import MainWindowMaterialsMixin
from main_window_physics_mixin import MainWindowPhysicsMixin


def test_mainwindow_inherits_extracted_mixins():
    assert issubclass(MainWindow, MainWindowDataMixin)
    assert issubclass(MainWindow, MainWindowPlotMixin)
    assert issubclass(MainWindow, MainWindowFitMixin)
    assert issubclass(MainWindow, MainWindowExportMixin)
    assert issubclass(MainWindow, MainWindowSessionMixin)
    assert issubclass(MainWindow, MainWindowSpectrogramMixin)
    assert issubclass(MainWindow, MainWindowViewMixin)


def test_mainwindow_inherits_phase2_mixins():
    for mixin in (
        MainWindowMenuMixin,
        MainWindowToolbarMixin,
        MainWindowPanelsMixin,
        MainWindowPlotCoreMixin,
        MainWindowAnalysisMixin,
        MainWindowEquationMixin,
        MainWindowSettingsMixin,
        MainWindowFeaturesMixin,
        MainWindowActionsMixin,
        MainWindowSpectroscopyMixin,
        MainWindowMaterialsMixin,
        MainWindowPhysicsMixin,
    ):
        assert issubclass(MainWindow, mixin), mixin.__name__
