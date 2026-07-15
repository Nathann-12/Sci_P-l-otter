"""EquationPlotDialog usability contract: Plot is gated on a non-empty
expression, quick-insert chips append lines, the mode switch toggles the 3D
domain/wireframe, and get_values() keeps its stable key contract."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from dialogs_equation import EquationPlotDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_plot_button_disabled_until_an_expression_is_entered(qapp):
    d = EquationPlotDialog()
    assert d.btn_ok.isEnabled() is False
    d.expr_edit.setPlainText("   \n  ")  # only whitespace
    assert d.btn_ok.isEnabled() is False
    d.expr_edit.setPlainText("sin(x)")
    assert d.btn_ok.isEnabled() is True
    assert d.btn_ok.isDefault()


def test_quick_insert_chip_appends_expression_on_a_new_line(qapp):
    d = EquationPlotDialog()
    d._insert_example("sin(x)")
    d._insert_example("x**2")
    assert d.expr_edit.toPlainText() == "sin(x)\nx**2"
    assert d.get_values()["expressions"] == ["sin(x)", "x**2"]


def test_mode_switch_toggles_3d_domain_and_wireframe(qapp):
    d = EquationPlotDialog()
    # 2D hides the Y-domain and wireframe controls
    assert d.ymin.isHidden() and d.wireframe_chk.isHidden()
    d.mode_combo.setCurrentIndex(1)  # 3D
    assert not d.ymin.isHidden() and not d.wireframe_chk.isHidden()
    assert d.y_scale.isEnabled() is False
    d.mode_combo.setCurrentIndex(0)  # back to 2D
    assert d.ymin.isHidden()
    assert d.y_scale.isEnabled() is True


def test_get_values_key_contract_is_stable(qapp):
    d = EquationPlotDialog()
    d.expr_edit.setPlainText("a*sin(b*x)")
    d.params_edit.setText("a=2, b=0.5")
    v = d.get_values()
    assert v["mode"] == "2d"
    assert v["expressions"] == ["a*sin(b*x)"]
    assert v["params"] == "a=2, b=0.5"
    assert v["overlay"] is True
    assert v["y_min"] is None and v["n_y_points"] is None
    assert v["wireframe"] is False

    d.mode_combo.setCurrentIndex(1)
    d.wireframe_chk.setChecked(True)
    v3 = d.get_values()
    assert v3["mode"] == "3d_surface"
    assert v3["wireframe"] is True
    assert v3["y_min"] == -10.0 and v3["y_max"] == 10.0 and v3["n_y_points"] == 200


def test_accept_shortcut_only_fires_when_ready(qapp):
    d = EquationPlotDialog()
    accepted = []
    d.accept = lambda: accepted.append(True)  # type: ignore[method-assign]
    d._accept_if_ready()          # empty -> no-op
    assert accepted == []
    d.expr_edit.setPlainText("cos(x)")
    d._accept_if_ready()
    assert accepted == [True]
