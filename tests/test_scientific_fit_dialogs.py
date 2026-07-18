from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from dialogs.global_fit_dialog import GlobalFitDialog
from dialogs.peak_analyzer_dialog import PeakAnalyzerDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_global_fit_dialog_maps_multiple_y_and_shared_shape(qapp):
    dialog = GlobalFitDialog(["x", "run 1", "run 2"])
    values = dialog.values()
    assert values["x"] == "x"
    assert values["ys"] == ["run 1", "run 2"]
    assert values["model"] == "gaussian"
    assert values["shared"] == ["center", "sigma"]
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()

    dialog.model_combo.setCurrentIndex(dialog.model_combo.findData("exponential_decay"))
    assert dialog.values()["shared"] == ["tau"]


def test_global_fit_dialog_requires_two_distinct_y_columns(qapp):
    dialog = GlobalFitDialog(["x", "y"])
    dialog.y_list.clearSelection()
    dialog.y_list.item(0).setSelected(True)
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_global_fit_dialog_maps_initial_bounds_and_fixed_parameters(qapp):
    dialog = GlobalFitDialog(["x", "run 1", "run 2"])
    amplitude = dialog._constraint_widgets["amplitude"]
    amplitude["initial"].setText("3.5")
    amplitude["lower"].setText("0")
    amplitude["upper"].setText("10")
    offset = dialog._constraint_widgets["offset"]
    offset["fixed"].setChecked(True)
    offset["fixed_value"].setText("1.25")
    values = dialog.values()
    assert values["initial"] == {"amplitude": 3.5}
    assert values["bounds"] == {"amplitude": (0.0, 10.0)}
    assert values["fixed"] == {"offset": 1.25}


def test_global_fit_dialog_rejects_half_or_reversed_bounds(qapp):
    dialog = GlobalFitDialog(["x", "run 1", "run 2"])
    width = dialog._constraint_widgets["sigma"]
    width["lower"].setText("1")
    assert "both lower and upper" in dialog.validation.text()
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    width["upper"].setText("0.5")
    assert "lower bound" in dialog.validation.text()


def test_peak_analyzer_dialog_returns_explicit_workflow(qapp):
    dialog = PeakAnalyzerDialog(["time", "signal"])
    values = dialog.values()
    assert values["x"] == "time"
    assert values["y"] == "signal"
    assert values["model"] == "gaussian"
    assert values["baseline"] == "linear"
    assert values["prominence"] is None
    assert values["height"] is None and values["width"] is None
    assert values["sigma"] is None
    assert dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()


def test_peak_analyzer_shows_only_relevant_baseline_controls(qapp):
    dialog = PeakAnalyzerDialog(["time", "signal", "sigma"])
    assert not dialog.als_lambda.isVisibleTo(dialog)
    dialog.baseline_combo.setCurrentIndex(dialog.baseline_combo.findData("als"))
    assert dialog.als_lambda.isVisibleTo(dialog)
    assert not dialog.constant_quantile.isVisibleTo(dialog)
    dialog.sigma_combo.setCurrentIndex(dialog.sigma_combo.findData("sigma"))
    assert dialog.values()["absolute_sigma"] is True
