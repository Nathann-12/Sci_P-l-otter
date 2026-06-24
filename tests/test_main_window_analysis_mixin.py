from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_analysis_mixin import MainWindowAnalysisMixin


def test_mainwindow_inherits_analysis_mixin():
    assert issubclass(MainWindow, MainWindowAnalysisMixin)


def test_analysis_methods_resolve_to_mixin():
    for name in ("_on_cc_compute", "_on_pk_detect", "_on_pk_annotate", "_on_pk_export",
                 "_collect_pk_params_from_menu"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowAnalysisMixin"), name
