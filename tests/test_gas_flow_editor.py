from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from analysis.gas_flow import GasFlowConfig, GasSensorChannelConfig
from UI.gas_flow_editor import GasFlowDesigner


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_flow_designer_builds_draggable_nodes_and_live_edges(qapp):
    designer = GasFlowDesigner()
    assert set(designer.nodes) == {"source", "divider", "smooth", "book", "graph"}
    assert len(designer.edges) == 4
    before = designer.edges[0].path().controlPointRect()
    designer.nodes["divider"].setPos(QPointF(480, 120))
    qapp.processEvents()
    after = designer.edges[0].path().controlPointRect()
    assert after != before
    designer.close()


def test_flow_designer_presets_emit_executable_configuration(qapp):
    designer = GasFlowDesigner()
    changes = []
    designer.config_changed.connect(changes.append)
    designer.preset_combo.setCurrentText("Resistance + smoothing")
    qapp.processEvents()
    config = designer.config()
    assert config.voltage_to_resistance and config.smoothing
    assert config.smoothing_field == "resistance_ohm"
    assert changes and changes[-1] == config
    assert designer.nodes["divider"].enabled
    assert designer.nodes["smooth"].enabled
    designer.close()


def test_flow_designer_fields_source_and_running_lock(qapp):
    designer = GasFlowDesigner()
    designer.set_available_fields(["ai0_voltage_v", "temperature"])
    designer.set_source("ni_daq", "Dev1/ai0 @ 20 Hz")
    designer.set_config(GasFlowConfig(
        voltage_to_resistance=True,
        voltage_field="ai0_voltage_v",
    ))
    assert designer.voltage_field_combo.currentText() == "ai0_voltage_v"
    assert designer.nodes["source"].title == "NI-DAQmx Input"
    designer.set_running(True)
    assert not designer.settings_body.isEnabled()
    assert "RUNNING" in designer.status_label.text()
    designer.set_running(False)
    assert designer.settings_body.isEnabled()
    designer.close()


def test_flow_designer_rewires_bypasses_and_rejects_invalid_graph(qapp):
    designer = GasFlowDesigner()
    changes = []
    designer.wiring_changed.connect(changes.append)
    source = designer.nodes["source"]
    target = designer.nodes["book"]
    designer._wire_start(source, source.mapToScene(source.output_port()))
    designer._wire_finish(source, target.mapToScene(target.input_port()))
    assert ("source", "book") in designer.wiring()
    assert changes

    bypass = (("source", "book"), ("book", "graph"))
    designer.set_wiring(bypass, emit=True)
    assert designer.wiring() == bypass
    assert designer.wiring_valid() and changes[-1] == bypass

    designer.clear_wires()
    assert not designer.wiring_valid()
    designer.auto_wire()
    assert designer.wiring_valid()
    assert designer.wiring() == (("source", "book"), ("book", "graph"))
    designer.close()


def test_flow_designer_palette_adds_processing_nodes_and_auto_wires(qapp):
    designer = GasFlowDesigner()
    designer.add_divider_button.click()
    designer.add_smooth_button.click()
    assert designer.config().voltage_to_resistance
    assert designer.config().smoothing
    assert designer.wiring() == (
        ("source", "divider"),
        ("divider", "smooth"),
        ("smooth", "book"),
        ("book", "graph"),
    )
    designer.nodes["smooth"].setSelected(True)
    designer._node_selected("smooth")
    designer.remove_node_button.click()
    assert not designer.config().smoothing
    assert designer.wiring() == (
        ("source", "divider"), ("divider", "book"), ("book", "graph")
    )
    designer.close()


def test_flow_designer_configures_independent_sensor_channels(qapp):
    designer = GasFlowDesigner()
    changes = []
    designer.config_changed.connect(changes.append)
    designer.set_available_fields(["ai0_voltage_v", "ai1_voltage_v"])
    designer.sensor_source_combo.setCurrentText("ai0_voltage_v")
    designer.sensor_alias_edit.setText("MQ-2 A")
    designer.sensor_divider_check.setChecked(True)
    designer.sensor_smoothing_check.setChecked(True)
    designer.sensor_window_spin.setValue(7)
    designer.sensor_save_button.click()
    config = designer.config()
    assert config.sensor_channels == (
        GasSensorChannelConfig(
            "ai0_voltage_v", "MQ-2 A", True, 5.0, 10_000.0,
            "sensor_high", True, 7,
        ),
    )
    assert designer.nodes["divider"].enabled and designer.nodes["smooth"].enabled
    assert changes[-1] == config
    designer.sensor_remove_button.click()
    assert not designer.config().sensor_channels
    designer.close()
