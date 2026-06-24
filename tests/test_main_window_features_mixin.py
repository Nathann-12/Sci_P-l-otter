from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_features_mixin import MainWindowFeaturesMixin


def test_mainwindow_inherits_features_mixin():
    assert issubclass(MainWindow, MainWindowFeaturesMixin)


def test_feature_methods_resolve_to_mixin():
    for name in ("run_aggregate_dialog", "feature_add_bkk_time", "feature_add_magnitude",
                 "feature_add_moving_average", "feature_set_column_types", "run_fft_dialog",
                 "on_export_report", "open_units_dialog", "open_derived_column_dialog"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowFeaturesMixin"), name
