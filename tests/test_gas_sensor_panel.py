from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from analysis.gas_flow import GasFlowConfig
from UI.gas_sensor_panel import GasSensorPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_live_panel_connection_controls_and_port_payload(qapp):
    panel = GasSensorPanel()
    events = []
    panel.connect_requested.connect(lambda port, baud: events.append((port, baud)))
    panel.set_ports([
        {"name": "COM7", "description": "ESP32", "manufacturer": "", "serial_number": ""}
    ])
    panel.set_baud(115200)
    panel.connect_button.click()
    panel.set_connection_state(True, "Connected")
    assert events == [("COM7", 115200)]
    assert not panel.connect_button.isEnabled()
    assert panel.disconnect_button.isEnabled()
    assert panel.connection_status.text() == "Connected"


def test_live_panel_signal_status_values_and_raw_monitor_limit(qapp):
    panel = GasSensorPanel()
    panel.set_signal_columns(["resistance", "temperature"], "temperature")
    panel.update_status(
        {"samples": 42, "sample_rate_hz": 10.25, "parse_errors": 2},
        {"r": 123.4, "voltage": 1.2, "temp": 31.5, "rh": 55},
    )
    panel.append_raw_lines([f"line {index}" for index in range(250)])
    assert panel.signal_combo.currentText() == "temperature"
    assert "42 samples" in panel.stats_label.text()
    assert panel.value_labels["resistance"].text() == "123.4"
    assert panel.value_labels["humidity"].text() == "55"
    assert panel.raw_monitor.document().blockCount() <= 200


def test_live_panel_selects_multiple_plot_signals(qapp):
    panel = GasSensorPanel()
    changes = []
    panel.signal_selection_changed.connect(changes.append)
    panel.set_signal_columns(
        ["Sensor A", "Sensor B", "temperature"], ["Sensor A", "Sensor B"]
    )
    assert panel.selected_signal_columns() == ["Sensor A", "Sensor B"]
    panel.signal_list.item(0).setSelected(False)
    assert changes[-1] == ["Sensor B"]
    columns = [f"sensor_{index}" for index in range(10)]
    panel.set_signal_columns(columns, columns)
    assert len(panel.selected_signal_columns()) == 8


def test_live_panel_marker_buttons_emit_receive_only_events(qapp):
    panel = GasSensorPanel()
    markers = []
    panel.marker_requested.connect(markers.append)
    panel.set_connection_state(True, "Connected")
    panel.gas_on_button.click()
    panel.gas_off_button.click()
    assert markers == ["on", "off"]


def test_live_panel_emits_ni_daq_configuration(qapp):
    panel = GasSensorPanel()
    events = []
    panel.daq_connect_requested.connect(lambda *args: events.append(args))
    panel.set_daq_devices([
        {"name": "Dev1", "product_type": "USB-6008", "serial_number": "42"}
    ])
    panel.set_daq_channels(["Dev1/ai0", "Dev1/ai1"], "Dev1/ai0")
    panel.set_daq_options(
        rate=20.0, min_voltage=-10.0, max_voltage=10.0, terminal="DIFFERENTIAL"
    )
    panel.set_transport("ni_daq")
    panel.connect_button.click()

    assert panel.connection_stack.currentWidget() is panel.daq_page
    assert events == [("Dev1", "Dev1/ai0", 20.0, -10.0, 10.0, "DIFFERENTIAL")]
    panel.set_connection_state(True, "Connected")
    assert not panel.transport_combo.isEnabled()
    assert not panel.daq_channel_combo.isEnabled()


def test_live_panel_emits_multiple_ni_daq_channels(qapp):
    panel = GasSensorPanel()
    events = []
    panel.daq_connect_requested.connect(lambda *args: events.append(args))
    panel.set_daq_devices([{"name": "Dev1", "product_type": "USB-6008"}])
    panel.set_daq_channels(
        ["Dev1/ai0", "Dev1/ai1", "Dev1/ai2"],
        "Dev1/ai0,Dev1/ai2",
    )
    panel.set_transport("ni_daq")
    panel.connect_button.click()
    assert panel.selected_daq_channels() == ["Dev1/ai0", "Dev1/ai2"]
    assert events[0][1] == "Dev1/ai0,Dev1/ai2"


def test_flow_tab_opens_designer_and_summarizes_pipeline(qapp):
    panel = GasSensorPanel()
    opened = []
    panel.flow_designer_requested.connect(lambda: opened.append(True))
    panel.tabs.setCurrentWidget(panel.flow_tab)
    panel.set_flow_summary(GasFlowConfig(
        voltage_to_resistance=True,
        smoothing=True,
        smoothing_window=7,
    ), running=True)
    panel.open_flow_button.click()
    assert opened == [True]
    assert "Voltage → resistance" in panel.flow_summary_label.text()
    assert "Moving average (7)" in panel.flow_summary_label.text()
    assert panel.open_flow_button.text() == "View Running Flow"
