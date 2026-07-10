from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel

from UI.modules_panel import ModulesPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _panel() -> ModulesPanel:
    panel = ModulesPanel()
    panel.add_module(
        "gas_sensor",
        "Gas Sensor",
        "Response, cycles, calibration, dilution",
        QLabel("gas"),
        search_terms=["Response Analysis (t90)", "Calibration Curve + LOD"],
    )
    panel.add_module(
        "electrochemistry",
        "Electrochemistry",
        "CV, Randles-Sevcik, Tafel, GCD, EIS",
        QLabel("ec"),
        search_terms=["CV Peak Metrics", "Tafel Analysis", "EIS Nyquist"],
    )
    return panel


def test_modules_panel_search_filters_cards_and_selects_visible_module(qapp):
    panel = _panel()

    panel.set_search_text("tafel")

    assert panel.visible_module_ids() == ["electrochemistry"]
    assert panel.current_module_id() == "electrochemistry"


def test_modules_panel_search_matches_tool_action_labels(qapp):
    panel = _panel()

    panel.set_search_text("lod")
    assert panel.visible_module_ids() == ["gas_sensor"]

    panel.set_search_text("nyquist")
    assert panel.visible_module_ids() == ["electrochemistry"]


def test_modules_panel_empty_state_when_search_has_no_match(qapp):
    panel = _panel()

    panel.set_search_text("spectroscopy")

    assert panel.visible_module_ids() == []
    assert not panel._empty_label.isHidden()
    assert panel._stack.isHidden()


def test_modules_panel_pin_and_pinned_filter(qapp):
    panel = _panel()
    pin_events = []
    panel.pin_changed.connect(lambda module_id, pinned: pin_events.append((module_id, pinned)))

    panel.show_module("gas_sensor")
    panel.toggle_current_pin()
    panel.pin_filter_button.setChecked(True)

    assert panel.pinned_module_ids() == ["gas_sensor"]
    assert panel.visible_module_ids() == ["gas_sensor"]
    assert panel.current_module_id() == "gas_sensor"

    panel.toggle_current_pin()
    assert panel.pinned_module_ids() == []
    assert panel.visible_module_ids() == []
    assert pin_events == [("gas_sensor", True), ("gas_sensor", False)]


def test_modules_panel_close_button_emits_request(qapp):
    panel = _panel()
    close_events = []
    panel.close_requested.connect(lambda: close_events.append(True))

    panel.close_button.click()

    assert close_events == [True]
