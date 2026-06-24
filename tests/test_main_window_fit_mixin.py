from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


pytest.importorskip("PySide6")
pytest.importorskip("numexpr")

from PySide6.QtWidgets import QApplication, QDialog, QWidget

import dialogs
import dialogs_fit
from main_window_fit_mixin import MainWindowFitMixin
from processors import FitResult
from widgets.plot_tabs import TabManager


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _StatusBar:
    def __init__(self):
        self.messages = []

    def showMessage(self, message: str, *_args) -> None:
        self.messages.append(message)


class DummyFitWindow(QWidget, MainWindowFitMixin):
    def __init__(self):
        super().__init__()
        self.tabs = TabManager(self)
        current_tab = self.tabs.currentWidget()
        self.canvas = current_tab.canvas
        self._status_bar = _StatusBar()
        self._df = pd.DataFrame(
            {
                "time": [0.0, 1.0, 2.0, 3.0],
                "value": [1.0, 2.0, 0.0, 1.0],
            }
        )
        self.current_fit_result = None

    def statusBar(self):
        return self._status_bar

    def get_current_dataframe(self):
        return self._df


def test_open_nonlinear_fit_dialog_passes_current_dataframe(qapp, monkeypatch):
    captured = {}

    class FakeDialog:
        def __init__(self, parent, df):
            captured["parent"] = parent
            captured["df"] = df.copy()

        def exec(self):
            captured["executed"] = True
            return 0

    monkeypatch.setattr(dialogs_fit, "NonlinearFitDialog", FakeDialog)

    window = DummyFitWindow()
    window.open_nonlinear_fit_dialog()

    assert captured["parent"] is window
    assert captured["df"].equals(window._df)
    assert captured["executed"] is True


def test_plot_fit_result_on_active_tab_registers_line_and_band(qapp):
    window = DummyFitWindow()
    tab = window.tabs.currentWidget()
    result = FitResult(
        params={"a": 1.0},
        stderr={},
        cov=np.eye(1),
        success=True,
        message="ok",
        r2=0.9,
        rmse=0.1,
        chi2_red=1.0,
        aic=0.0,
        bic=0.0,
        yfit=np.array([2.0, 3.0, 4.0]),
        ci95_lower=np.array([1.5, 2.5, 3.5]),
        ci95_upper=np.array([2.5, 3.5, 4.5]),
    )

    window.plot_fit_result_on_active_tab(np.array([3.0, 1.0, 2.0]), result)

    ax = tab.get_axes()
    assert len(ax.lines) == 1
    assert list(ax.lines[0].get_xdata()) == [1.0, 2.0, 3.0]
    assert len(ax.collections) == 1
    layer = next(iter(tab.layers.values()))
    assert layer["label"] == "Nonlinear Fit"
    assert layer["meta"] == {"kind": "nonlinear_fit", "success": True, "message": "ok"}


def test_do_curve_fit_sine_model_returns_overlay_points(qapp):
    window = DummyFitWindow()
    x = np.linspace(0.0, 2.0 * np.pi, 32)
    y = 1.5 * np.sin(x + 0.25) + 0.2

    xfit, yfit, params, metrics = window._do_curve_fit(x, y, model="sine")

    assert xfit.shape == (400,)
    assert yfit.shape == (400,)
    assert {"A", "f", "phi", "C"} <= set(params)
    assert "r2" in metrics
    assert "rmse" in metrics


def test_plot_fit_overlay_adds_annotation_and_status(qapp):
    window = DummyFitWindow()

    window._plot_fit_overlay(
        "value vs time",
        np.array([0.0, 1.0, 2.0]),
        np.array([1.0, 1.5, 1.0]),
        {"a": 1.23, "b": 4.56},
        {"r2": 0.875, "rmse": 0.125},
        show_eq=True,
        show_resid=False,
        x_seconds=True,
    )

    ax = window.canvas.ax
    assert len(ax.lines) == 1
    assert len(ax.texts) == 1
    assert "x (seconds from start)" in ax.texts[0].get_text()
    assert window.statusBar().messages[-1] == "Fit สำเร็จ • R²=0.875  RMSE=0.125"


def test_open_fit_dialog_collects_series_and_stores_result(qapp, monkeypatch):
    window = DummyFitWindow()
    window._df = pd.DataFrame({"other": [10.0, 20.0, 30.0]})
    window.canvas.ax.plot([0.0, 1.0, 2.0], [1.0, 2.0, 3.0], label="value vs time")
    captured = {}

    class FakeFitDialog:
        def __init__(self, parent, labels, series_data):
            captured["parent"] = parent
            captured["labels"] = list(labels)
            captured["series_data"] = {key: value for key, value in series_data.items()}

        def exec(self):
            return QDialog.Accepted

        def get_params(self):
            return {
                "series_label": "value vs time",
                "model": "sine",
                "degree": None,
                "show_eq": True,
                "show_resid": False,
            }

    def fake_do_curve_fit(x, y, *, model, degree=None):
        captured["fit_args"] = (x.copy(), y.copy(), model, degree)
        return (
            np.array([0.0, 1.0, 2.0]),
            np.array([1.1, 1.9, 3.1]),
            {"A": 1.0},
            {"r2": 0.99, "rmse": 0.05},
        )

    def fake_plot_fit_overlay(series_label, xfit, yfit, params, metrics, **kwargs):
        captured["overlay"] = {
            "series_label": series_label,
            "xfit": xfit.copy(),
            "yfit": yfit.copy(),
            "params": dict(params),
            "metrics": dict(metrics),
            "kwargs": dict(kwargs),
        }

    monkeypatch.setattr(dialogs, "FitDialog", FakeFitDialog)
    monkeypatch.setattr(window, "_do_curve_fit", fake_do_curve_fit)
    monkeypatch.setattr(window, "_plot_fit_overlay", fake_plot_fit_overlay)

    window._open_fit_dialog()

    assert captured["parent"] is window
    assert captured["labels"] == ["value vs time"]
    np.testing.assert_allclose(captured["series_data"]["value vs time"][0], np.array([0.0, 1.0, 2.0]))
    np.testing.assert_allclose(captured["series_data"]["value vs time"][1], np.array([1.0, 2.0, 3.0]))
    fit_x, fit_y, fit_model, fit_degree = captured["fit_args"]
    np.testing.assert_allclose(fit_x, np.array([0.0, 1.0, 2.0]))
    np.testing.assert_allclose(fit_y, np.array([1.0, 2.0, 3.0]))
    assert fit_model == "sine"
    assert fit_degree is None
    assert captured["overlay"]["series_label"] == "value vs time"
    assert captured["overlay"]["kwargs"] == {"show_eq": True, "show_resid": False, "x_seconds": False}
    assert window.current_fit_result["series"] == "value vs time"
    assert window.current_fit_result["model"] == "sine"
    assert window.current_fit_result["params"] == {"A": 1.0}
    assert window.current_fit_result["metrics"] == {"r2": 0.99, "rmse": 0.05}
    np.testing.assert_allclose(window.current_fit_result["xfit"], np.array([0.0, 1.0, 2.0]))
    np.testing.assert_allclose(window.current_fit_result["yfit"], np.array([1.1, 1.9, 3.1]))
