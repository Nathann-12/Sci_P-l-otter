from pathlib import Path
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("numexpr")

from main import MainWindow
from main_window_actions_mixin import MainWindowActionsMixin


class _ListItemStub:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _ListWidgetStub:
    def __init__(self, selected=None):
        self.selected = selected

    def currentItem(self):
        return _ListItemStub(self.selected) if self.selected is not None else None


class _WindowStub(MainWindowActionsMixin):
    def __init__(self):
        self._df = None
        self._current_path = None
        self._datasets = {}
        self.lstFiles = _ListWidgetStub()


def test_mainwindow_inherits_actions_mixin():
    assert issubclass(MainWindow, MainWindowActionsMixin)


def test_action_methods_resolve_to_mixin():
    for name in ("on_action_plot", "on_action_spectrogram", "on_action_export_figure",
                 "get_current_dataframe", "_resolve_active_dataframe", "get_current_xy",
                 "show_histogram_dialog", "dragEnterEvent", "dropEvent"):
        assert getattr(MainWindow, name).__qualname__.startswith("MainWindowActionsMixin"), name


def test_active_dataframe_prefers_cached_dataframe():
    window = _WindowStub()
    cached = pd.DataFrame({"source": ["cached"]})
    window._df = cached
    window.current_df = pd.DataFrame({"source": ["compat"]})
    window._datasets["selected"] = {
        "df": pd.DataFrame({"source": ["dataset"]}),
        "path": "selected.csv",
    }
    window.lstFiles.selected = "selected"

    assert window._resolve_active_dataframe() is cached


def test_active_dataframe_uses_selected_dataset_and_syncs_path():
    window = _WindowStub()
    first = pd.DataFrame({"source": ["first"]})
    selected = pd.DataFrame({"source": ["selected"]})
    window._datasets = {
        "first": {"df": first, "path": "first.csv"},
        "selected": {"df": selected, "path": "selected.csv"},
    }
    window.lstFiles.selected = "selected"

    resolved = window._resolve_active_dataframe()

    assert resolved.equals(selected)
    assert resolved is window._df
    assert resolved is not selected
    assert window._current_path == "selected.csv"


def test_get_current_dataframe_returns_empty_frame_without_active_data():
    window = _WindowStub()

    resolved = window.get_current_dataframe()

    assert isinstance(resolved, pd.DataFrame)
    assert resolved.empty


def test_dataset_without_path_clears_stale_active_path():
    window = _WindowStub()
    window._current_path = "stale.csv"
    window._datasets["typed"] = {"df": pd.DataFrame({"x": [1]})}

    window._resolve_active_dataframe()

    assert window._current_path is None
